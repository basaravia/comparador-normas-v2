"""Extracción de texto con Docling (docs/07 §1).

- Cola de **1 worker** a nivel de módulo: Docling nunca corre en paralelo (CLAUDE.md, regla 7).
- Docling corre en un **subproceso** (`docling_worker`) que se mata con `terminate()` al vencer
  `DOCLING_TIMEOUT_S`: un hilo no se puede cortar y seguiría gastando CPU y RAM.
- Antes de extraer se llama a `validar_pdf` (límites, escaneo, cabecera).
- **Caché por SHA-256** en memoria: el mismo PDF no vuelve a pasar por Docling.
- Sin extractor de respaldo: si Docling falla, error claro (CLAUDE.md, regla 4).
"""
import json
import logging
import os
import signal
import subprocess  # nosec B404
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from backend.config import RAIZ, redact, settings
from backend.core.errors import ComparadorError
from backend.ingest.validation import validar_pdf

log = logging.getLogger(__name__)


class ExtraccionError(ComparadorError):
    """No se pudo extraer el texto. Lleva su propio código y mensaje de negocio."""

    def __init__(self, detalle: str, codigo: str = "ERR-EXT-001",
                 mensaje: str = "No pudimos leer el texto de este documento. Intenta con otro archivo."):
        super().__init__(detalle)
        self.codigo = codigo
        self.mensaje_negocio = mensaje


_COLA = ThreadPoolExecutor(max_workers=1)                       # Docling nunca en paralelo
ENTORNO_HIJO = {"PATH", "HOME", "LANG", "TMPDIR", "CONDA_PREFIX", "VIRTUAL_ENV", "PYTHONPATH", "LD_LIBRARY_PATH"}
MAX_CACHE = 8                                                   # PDFs en memoria (RAM acotada)
_CACHE: dict[str, list[dict]] = {}                              # sha256 → bloques
_COMANDO = [sys.executable, "-m", "backend.ingest.docling_worker"]  # reemplazable en pruebas del control


def limpiar_cache() -> None:
    _CACHE.clear()


def extraer(ruta: Path, progreso: Callable[[int, int], None] | None = None) -> list[dict]:
    """Bloques `{"texto", "pagina", "tipo"}` de un PDF. Bloquea hasta terminar.

    `progreso(paginas_hechas, total)` se llama tras cada tanda de páginas. Lanza `ExtraccionError`
    si el PDF no es válido, si Docling falla, si no hay texto o si vence el timeout.
    """
    ruta = Path(ruta)
    v = validar_pdf(ruta)
    if not v.ok:
        raise ExtraccionError(v.mensaje, v.codigo, v.mensaje)
    return list(_COLA.submit(_trabajo, ruta, v.sha256, progreso).result())


def _trabajo(ruta: Path, sha256: str, progreso) -> list[dict]:
    if sha256 in _CACHE:  # otro trabajo encolado antes pudo extraer el mismo PDF
        log.info("Caché de extracción: %s", sha256[:12])
        return _CACHE[sha256]
    bloques = _ejecutar(ruta, progreso)
    while len(_CACHE) >= MAX_CACHE:
        _CACHE.pop(next(iter(_CACHE)))  # descarta el más antiguo
    _CACHE[sha256] = bloques
    return bloques


def _matar(proc, senal) -> None:
    """Envía la señal a todo el grupo del subproceso (Docling y cualquier proceso hijo)."""
    try:
        os.killpg(proc.pid, senal)
    except ProcessLookupError:
        pass


def _ejecutar(ruta: Path, progreso) -> list[dict]:
    s = settings
    comando = [*_COMANDO, str(ruta), s.DOCLING_TABLES, str(s.DOCLING_THREADS), str(s.DOCLING_CHUNK_PAGES)]
    if s.DOCLING_ARTIFACTS:
        comando.append(s.DOCLING_ARTIFACTS)
    # Entorno mínimo: Docling no necesita las claves de los modelos (GROQ_API_KEY, FOUNDRY_AI_TOKEN…).
    entorno = {k: v for k, v in os.environ.items() if k in ENTORNO_HIJO or k.startswith(("HF_", "LC_"))}
    entorno.update(OMP_NUM_THREADS=str(s.DOCLING_THREADS), HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1")

    bloques, vencio = None, threading.Event()
    with tempfile.TemporaryFile() as errores:
        # cwd=RAIZ: `python -m backend...` debe encontrar el paquete aunque quien llama esté en otra carpeta.
        # Lista fija con sys.executable, sin shell, y la ruta ya validada: por eso B404/B603 son aceptables.
        # start_new_session: el subproceso tiene su propia sesión y se mata con sus procesos hijos.
        proc = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=errores, text=True,  # nosec B603
                                env=entorno, cwd=RAIZ, start_new_session=True)

        def cortar():
            vencio.set()
            _matar(proc, signal.SIGTERM)

        reloj = threading.Timer(s.DOCLING_TIMEOUT_S, cortar)
        reloj.start()
        try:
            for linea in proc.stdout:
                try:
                    evento = json.loads(linea)
                except ValueError:
                    continue  # ruido que Docling imprima en stdout
                if "progreso" in evento and progreso:
                    progreso(*evento["progreso"])
                elif "bloques" in evento:
                    bloques = evento["bloques"]
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _matar(proc, signal.SIGKILL)
                proc.wait()
        finally:
            reloj.cancel()
            if proc.poll() is None:
                _matar(proc, signal.SIGKILL)
                proc.wait()

        if vencio.is_set():
            raise ExtraccionError(f"Docling superó {s.DOCLING_TIMEOUT_S} s y se terminó el proceso.", "ERR-EXT-002",
                                  "El documento es demasiado largo o complejo y tardó más de lo permitido. "
                                  "Divídelo en partes.")
        if proc.returncode != 0 or bloques is None:
            errores.seek(0)
            cola = errores.read().decode("utf-8", "replace")[-500:]
            raise ExtraccionError(f"Docling terminó con código {proc.returncode}: {redact(cola)}")
    if not bloques:
        raise ExtraccionError("Docling no encontró texto en el documento.", "ERR-EXT-003",
                              "No encontramos texto en este documento.")
    return bloques
