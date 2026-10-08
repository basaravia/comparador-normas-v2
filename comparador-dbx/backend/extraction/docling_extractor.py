"""Extracción de texto con Docling (docs/07 §1).

- Cola de **1 worker** a nivel de módulo: Docling nunca corre en paralelo (CLAUDE.md, regla 7).
- Docling corre en un **subproceso** (`docling_worker`) que se mata con `killpg` al vencer
  `DOCLING_TIMEOUT_S`: un hilo no se puede cortar y seguiría gastando CPU y RAM.
- Antes de extraer se llama a `validar_pdf` (límites, escaneo, cabecera).
- **Caché por SHA-256** en memoria: el mismo PDF no vuelve a pasar por Docling.
- Sin extractor de respaldo: si Docling falla, error claro (CLAUDE.md, regla 4).
"""
import json
import logging
import os
import re
import signal
import subprocess  # nosec B404
import sys
import tempfile
import threading
import unicodedata
from collections import Counter
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
ENTORNO_HIJO = {"PATH", "HOME", "LANG", "TMPDIR", "CONDA_PREFIX", "VIRTUAL_ENV", "PYTHONPATH", "LD_LIBRARY_PATH",
                # Red corporativa: proxy y certificados propios, para que el hijo pueda descargar los modelos de Docling.
                "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
                "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"}
_RED_BLOQUEADA = ("SSLError", "MaxRetryError", "ConnectionError", "LocalEntryNotFoundError", "offline mode")  # fallo al bajar modelos
DISPOSITIVOS = {"auto", "cpu", "cuda", "mps"}                    # `auto`: GPU si hay (CUDA, Metal, ROCm); si no, CPU
MAX_CACHE = 8                                                   # PDFs en memoria (RAM acotada)
_CACHE: dict[str, list[dict]] = {}                              # sha256 → bloques
_COMANDO = [sys.executable, "-m", "backend.extraction.docling_worker"]  # reemplazable en pruebas del control


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


def _columnas(tabla: str) -> int:
    return len(tabla.split("\n", 1)[0].strip().strip("|").split("|"))


def _es_continuacion(previa: dict, b: dict) -> bool:
    """Una tabla que sigue en la página siguiente: misma cantidad de columnas y su "cabecera" es en realidad un dato (empieza por número).

    Docling no une las tablas partidas por una página (issue #2976) y toma la primera fila de la continuación como cabecera."""
    if previa["tipo"] != "tabla" or b["tipo"] != "tabla" or b["pagina"] != previa.get("pagina_fin", previa["pagina"]) + 1:
        return False
    primera = b["texto"].split("\n", 1)[0].strip().strip("|").split("|")[0].strip()
    return _columnas(previa["texto"]) == _columnas(b["texto"]) and bool(re.fullmatch(r"[\d.,%\s-]+", primera))


def _unir_tablas(bloques: list[dict]) -> list[dict]:
    salida = []
    for b in bloques:
        if salida and _es_continuacion(salida[-1], b):
            filas = b["texto"].split("\n")
            datos = filas[2:] if len(filas) > 1 and re.fullmatch(r"\|[\s:|-]+\|", filas[1].strip()) else filas[1:]
            salida[-1] = {**salida[-1], "texto": "\n".join([salida[-1]["texto"], filas[0], *datos]), "pagina_fin": b["pagina"]}
            continue
        salida.append(b)
    return salida


def limpiar_bloques(bloques: list[dict]) -> list[dict]:
    """Texto en NFC (cada tilde en una sola forma) y sin encabezados o pies de página repetidos.

    Docling a veces deja como texto corriente la línea que se repite en cada página ("Codificación de las Normas…"),
    y quedaría en medio de un artículo. Se descarta un párrafo corto idéntico que aparece en la mitad de las páginas
    (y al menos en 3). El resto del texto no se toca."""
    paginas = {b["pagina"] for b in bloques}
    veces = Counter(texto for _, texto in {(b["pagina"], b["texto"]) for b in bloques
                                           if b["tipo"] == "parrafo" and len(b["texto"]) <= 150})
    repetidos = {t for t, n in veces.items() if n >= max(3, len(paginas) // 2)}
    limpios = [{**b, "texto": unicodedata.normalize("NFC", b["texto"])} for b in bloques
               if not (b["tipo"] == "parrafo" and b["texto"] in repetidos)]
    return _unir_tablas(limpios) if settings.TABLAS_ATOMICAS else limpios


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
    if s.DOCLING_DEVICE not in DISPOSITIVOS:
        raise ExtraccionError(f"DOCLING_DEVICE={s.DOCLING_DEVICE!r} no es válido; usa uno de {sorted(DISPOSITIVOS)}")
    entorno.update(DOCLING_DEVICE=s.DOCLING_DEVICE, OMP_NUM_THREADS=str(s.DOCLING_THREADS), HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1")

    bloques, figuras, vencio = None, [], threading.Event()
    with tempfile.TemporaryFile() as errores:
        # cwd=RAIZ: `python -m backend...` debe encontrar el paquete aunque quien llama esté en otra carpeta.
        # Lista fija con sys.executable, sin shell, y la ruta ya validada: por eso B404/B603 son aceptables.
        # start_new_session: el subproceso tiene su propia sesión y se mata con sus procesos hijos.
        proc = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=errores, text=True,  # nosec B603
                                env=entorno, cwd=RAIZ, start_new_session=True)

        def cortar():
            vencio.set()
            _matar(proc, signal.SIGTERM)
            # Si el hijo ignora SIGTERM, a los 5 s se le mata sin más (cierra stdout y libera el bucle de lectura).
            threading.Timer(5, _matar, (proc, signal.SIGKILL)).start()

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
                elif "figuras" in evento:
                    figuras = evento["figuras"]
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
            texto_error = errores.read().decode("utf-8", "replace")
            cola = texto_error[-500:]
            if any(marca in texto_error for marca in _RED_BLOQUEADA):
                raise ExtraccionError(f"Docling no pudo descargar sus modelos: {redact(cola)}", "ERR-EXT-004",
                                      "No pudimos preparar el lector de documentos porque la red bloquea la descarga de sus modelos. "
                                      "Pide a TI que los habilite o copia los modelos al equipo (ver documentos/LEEME.md).")
            raise ExtraccionError(f"Docling terminó con código {proc.returncode}: {redact(cola)}")
    if not bloques:
        raise ExtraccionError("Docling no encontró texto en el documento.", "ERR-EXT-003",
                              "No encontramos texto en este documento.")
    figuras = [{"texto": f"Figura en la página {f['pagina']} (su contenido no se analiza)", "pagina": f["pagina"], "tipo": "figura"} for f in figuras]
    return limpiar_bloques(bloques) + figuras
