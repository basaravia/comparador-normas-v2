"""Estado de sesión en memoria (docs/11 §Sesión y jobs). Sin persistencia: el Excel descargado es la persistencia (CLAUDE.md regla 8).

Una sesión por cookie `session_id`; expira por inactividad (`SESSION_TTL_HOURS`). Los PDF subidos viven en un directorio temporal de la sesión
y se borran al expirar o al reiniciar.
"""
import logging
import secrets
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from backend.api.schemas import ComparacionOut, DocumentoOut, ErrorNegocio, JobOut
from backend.config import Settings, settings
from backend.models import Seccion
from backend.retrieval.index import Indice

log = logging.getLogger(__name__)


class SesionPerdida(Exception):
    """La cookie no corresponde a ninguna sesión viva (contenedor reiniciado o sesión expirada): 410 Gone."""


@dataclass
class Doc:
    out: DocumentoOut
    ruta: Optional[Path] = None
    sha256: str = ""
    secciones: list[Seccion] = field(default_factory=list)
    clasificacion: dict[str, tuple[bool, str]] = field(default_factory=dict)     # id -> (incluir, motivo)
    avisos_arbol: list[str] = field(default_factory=list)


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
    docs: dict[str, Doc] = field(default_factory=dict)
    jobs: dict[str, JobOut] = field(default_factory=dict)
    comparaciones: dict[str, Comparacion] = field(default_factory=dict)
    indice_norma: Optional[Indice] = None
    indice_manual: Optional[Indice] = None
    indexados: set[str] = field(default_factory=set)          # ids de los documentos ya incluidos en los índices
    lock: threading.RLock = field(default_factory=threading.RLock)
    contador: int = 0

    def nuevo_id(self, prefijo: str) -> str:
        with self.lock:
            self.contador += 1
            return f"{prefijo}{self.contador}"

    def secciones(self) -> dict[str, Seccion]:
        return {s.id: s for d in self.docs.values() for s in d.secciones}


_SESIONES: dict[str, Sesion] = {}
_LOCK = threading.Lock()


def _borrar(s: Sesion) -> None:
    shutil.rmtree(s.dir, ignore_errors=True)


def limpiar_expiradas(cfg: Settings = settings) -> None:
    limite = time.time() - cfg.SESSION_TTL_HOURS * 3600
    with _LOCK:
        for sid in [k for k, s in _SESIONES.items() if s.ultimo_uso < limite]:
            log.info("Sesión expirada por inactividad")
            _borrar(_SESIONES.pop(sid))


def crear() -> Sesion:
    limpiar_expiradas()
    sid = secrets.token_urlsafe(32)
    s = Sesion(id=sid, dir=Path(tempfile.mkdtemp(prefix="comparador_")))
    with _LOCK:
        _SESIONES[sid] = s
    return s


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
        s = _SESIONES.pop(sid or "", None)
    if s:
        _borrar(s)


def error_negocio(e: Exception) -> ErrorNegocio:
    """Mensaje para el auditor: los errores del dominio traen el suyo; el resto es genérico (el detalle va solo al log)."""
    from backend.core.errors import ComparadorError
    if isinstance(e, ComparadorError):
        return ErrorNegocio(**e.para_usuario())
    log.exception("Error inesperado")
    return ErrorNegocio(codigo=ComparadorError.codigo, mensaje=ComparadorError.mensaje_negocio)
