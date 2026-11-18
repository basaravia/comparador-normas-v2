"""Estado de sesión en memoria (docs/11 §Sesión y jobs). Sin persistencia: el Excel descargado es la persistencia (CLAUDE.md regla 8).

Una sesión por cookie `session_id` o, con `TRUST_PROXY_IDENTITY`, una por usuario (SHA-256 del correo que entrega el proxy de Databricks); expira por
inactividad (`SESSION_TTL_HOURS`). Los PDF subidos viven en un directorio temporal de la sesión y se borran al terminar de procesarlos, al expirar o al
reiniciar. El correo y su hash no se registran en ningún log.
"""
import hashlib
import logging
import os
import re
import secrets
import shutil
import stat
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.api.schemas import ComparacionOut, DocumentoOut, ErrorNegocio, JobOut
from backend.config import settings
from backend.core.errors import ComparadorError
from backend.models import Seccion
from backend.retrieval.index import Indice

log = logging.getLogger(__name__)


class SesionesLlenas(ComparadorError):
    """Hay `MAX_SESIONES` sesiones vivas: se pide reintentar en un momento (503)."""
    codigo = "ERR-SES-002"
    mensaje_negocio = "El servicio está atendiendo a otras personas en este momento. Intenta de nuevo en unos minutos."


class SesionPerdida(Exception):
    """La cookie no corresponde a ninguna sesión viva (contenedor reiniciado o sesión expirada): 410 Gone."""


class IdentidadInvalida(ComparadorError):
    """Con `TRUST_PROXY_IDENTITY` la cabecera `x-forwarded-email` falta o no es válida: 401. Nunca repite el valor recibido."""
    codigo = "ERR-SES-003"
    mensaje_negocio = "No pudimos identificar tu cuenta. Vuelve a abrir la aplicación desde Databricks."


@dataclass
class Doc:
    out: DocumentoOut
    ruta: Optional[Path] = None
    sha256: str = ""
    secciones: list[Seccion] = field(default_factory=list)
    clasificacion: dict[str, tuple[bool, str]] = field(default_factory=dict)     # id -> (incluir, motivo)
    avisos_arbol: list[str] = field(default_factory=list)
    ingesta: bool = False                          # True mientras se valida y clasifica el PDF recién subido


@dataclass
class Comparacion:
    out: ComparacionOut
    entrada: object = None                         # EntradaPapel (se arma al terminar)
    archivo: Optional[Path] = None


@dataclass
class Sesion:
    id: str
    dir: Path
    ultimo_uso: float = field(default_factory=time.time)
    iniciada_ts: float = field(default_factory=time.time)          # cuándo se creó en el servidor: cambia si la sesión se recrea
    huella: str = ""                                               # SHA-256 del correo (solo con TRUST_PROXY_IDENTITY); nunca se registra
    cerrada: bool = False                                          # "Borrar todo" en marcha: no se aceptan trabajos ni subidas nuevas
    docs: dict[str, Doc] = field(default_factory=dict)
    jobs: dict[str, JobOut] = field(default_factory=dict)
    comparaciones: dict[str, Comparacion] = field(default_factory=dict)
    indice_norma: Optional[Indice] = None
    indice_manual: Optional[Indice] = None
    cancelados: set[str] = field(default_factory=set)         # ids de jobs que el auditor canceló
    indexados: set[str] = field(default_factory=set)          # ids de los documentos ya incluidos en los índices
    lock: threading.RLock = field(default_factory=threading.RLock)
    contador: int = 0
    ajustes: dict[str, float] = field(default_factory=dict)        # RF-19: cambios de la sesión sobre los valores por defecto

    def nuevo_id(self, prefijo: str) -> str:
        with self.lock:
            self.contador += 1
            return f"{prefijo}{self.contador}"

    def secciones(self) -> dict[str, Seccion]:
        return {s.id: s for d in self.docs.values() for s in d.secciones}


PREFIJO = "comparador_sesion_"                       # prefijo del mkdtemp de cada sesión: lo usa también la limpieza de arranque
_SESIONES: dict[str, Sesion] = {}
_POR_HUELLA: dict[str, str] = {}                      # huella del correo -> id de sesión
_LOCK = threading.Lock()                              # orden de bloqueos: _LOCK primero, luego sesion.lock (nunca al revés)
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+$")


def trabajo_activo(s: Sesion) -> Optional[dict]:
    """El job en cola o en curso de la sesión: `{id (siempre el job_id), tipo, comparacion_id (solo comparación)}` o None."""
    with s.lock:
        for j in s.jobs.values():
            if j.estado in ("en_cola", "en_curso"):
                return {"id": j.job_id, "tipo": j.tipo, "comparacion_id": j.comparacion_id if j.tipo == "comparacion" else None}
    return None


def exigir_abierta(s: Sesion) -> None:
    """Llamar con `s.lock` tomado antes de registrar un trabajo o una subida: una sesión que se está borrando responde 410."""
    if s.cerrada:
        raise SesionPerdida()


def hay_trabajo(s: Sesion) -> bool:
    """Job activo o ingesta en curso: esa sesión no se expira ni se expulsa."""
    with s.lock:
        return trabajo_activo(s) is not None or any(d.ingesta for d in s.docs.values())


def _borrar(s: Sesion) -> None:
    shutil.rmtree(s.dir, ignore_errors=True)


def _quitar(s: Sesion) -> None:
    """Saca la sesión de los índices (con `_LOCK` tomado); el borrado de disco lo hace quien llama, fuera del lock."""
    _SESIONES.pop(s.id, None)
    if s.huella:
        _POR_HUELLA.pop(s.huella, None)


def _expiradas() -> list[Sesion]:
    limite = time.time() - settings.SESSION_TTL_HOURS * 3600
    caidas = [s for s in _SESIONES.values() if s.ultimo_uso < limite and not hay_trabajo(s)]
    for s in caidas:
        _quitar(s)
    return caidas


def limpiar_expiradas() -> None:
    with _LOCK:
        caidas = _expiradas()
    for s in caidas:
        log.info("Sesión expirada por inactividad")
        _borrar(s)


def _expulsar() -> list[Sesion]:
    """Servidor lleno: sale la sesión más inactiva, solo si lleva sin uso al menos `SESION_EXPULSABLE_MIN` y no tiene trabajo activo."""
    minimo = time.time() - settings.SESION_EXPULSABLE_MIN * 60
    candidatas = [s for s in _SESIONES.values() if s.ultimo_uso <= minimo and not hay_trabajo(s)]
    if not candidatas:
        raise SesionesLlenas()
    s = min(candidatas, key=lambda x: x.ultimo_uso)
    _quitar(s)
    log.info("Sesión expulsada por falta de cupo")
    return [s]


def crear(huella: str = "") -> Sesion:
    """Sesión nueva. Con `huella`, devuelve la de ese usuario si ya existe (la búsqueda y la creación van bajo el mismo lock)."""
    caidas: list[Sesion] = []
    try:
        with _LOCK:
            caidas = _expiradas()
            existente = _SESIONES.get(_POR_HUELLA.get(huella, "")) if huella else None
            if existente is not None:
                existente.ultimo_uso = time.time()
                return existente
            if len(_SESIONES) >= settings.MAX_SESIONES:
                caidas += _expulsar()
            s = Sesion(id=secrets.token_urlsafe(32), dir=Path(tempfile.mkdtemp(prefix=PREFIJO)), huella=huella)
            _SESIONES[s.id] = s
            if huella:
                _POR_HUELLA[huella] = s.id
        return s
    finally:
        for c in caidas:
            _borrar(c)


def obtener(sid: Optional[str]) -> Sesion:
    """La sesión viva de esa cookie. `SesionPerdida` si no existe."""
    limpiar_expiradas()
    with _LOCK:
        s = _SESIONES.get(sid or "")
    if s is None:
        raise SesionPerdida()
    s.ultimo_uso = time.time()
    return s


def reiniciar(sid: Optional[str]) -> None:
    with _LOCK:
        s = _SESIONES.get(sid or "")
        if s:
            _quitar(s)
    if s:
        _borrar(s)


def reiniciar_usuario(huella: str) -> None:
    with _LOCK:
        sid = _POR_HUELLA.get(huella)
    reiniciar(sid)


def existente(sid: Optional[str] = None, huella: str = "") -> Optional[Sesion]:
    """La sesión viva de esa cookie o de ese usuario, sin crear ninguna ni renovar su uso. None si no hay."""
    with _LOCK:
        return _SESIONES.get(_POR_HUELLA.get(huella, "") if huella else (sid or ""))


def leer_correo(valores: list[str]) -> str:
    """El correo de `x-forwarded-email`, normalizado. Exactamente un valor de ≤ 254 caracteres con forma `a@b`, sin espacios ni caracteres de control."""
    if len(valores) != 1:
        raise IdentidadInvalida()
    correo = valores[0].strip().lower()
    if len(correo) > 254 or not _CORREO.match(correo) or any(ord(c) < 32 or ord(c) == 127 for c in correo):
        raise IdentidadInvalida()
    return correo


def huella_de(correo: str) -> str:
    return hashlib.sha256(correo.encode("utf-8")).hexdigest()


def limpiar_tmp_huerfanos() -> int:
    """Al arrancar: borra las carpetas de sesión que dejó un proceso anterior en el directorio temporal. Solo hijos directos con nuestro prefijo,
    que sean directorios reales (no enlaces) del mismo usuario del proceso."""
    base, n = Path(tempfile.gettempdir()), 0
    for p in base.glob(PREFIJO + "*"):
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid():
            shutil.rmtree(p, ignore_errors=True)
            n += 1
    return n


def error_negocio(e: Exception) -> ErrorNegocio:
    """Mensaje para el auditor: los errores del dominio traen el suyo; el resto es genérico (el detalle va solo al log)."""
    from backend.core.errors import ComparadorError
    if isinstance(e, ComparadorError):
        return ErrorNegocio(**e.para_usuario())
    log.exception("Error inesperado")
    return ErrorNegocio(codigo=ComparadorError.codigo, mensaje=ComparadorError.mensaje_negocio)
