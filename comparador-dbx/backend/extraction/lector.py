"""Lee un PDF y devuelve sus secciones: Docling (extracción) + cascada de seccionado, en un solo paso.

Lo usan los notebooks y, después, la API. `cache` (opcional) es una carpeta donde se guardan los bloques de Docling por SHA-256 del PDF:
la extracción de un manual largo tarda 6-10 minutos y así no se repite entre notebooks. Es solo de desarrollo; la app no persiste nada.
"""
import json
import os
from pathlib import Path
from typing import Callable, Literal

from backend.extraction import docling_extractor
from backend.extraction.docling_extractor import ExtraccionError
from backend.extraction.sectioner import parsear_bloques
from backend.ingest.validation import validar_pdf
from backend.models import Seccion


def _valido(bloques) -> bool:
    """La caché es un archivo local editable: solo se acepta una lista de bloques con la forma que produce Docling."""
    return isinstance(bloques, list) and all(isinstance(b, dict) and isinstance(b.get("texto"), str) and isinstance(b.get("pagina"), int)
                                             and isinstance(b.get("tipo"), str) for b in bloques)


def _bloques(ruta: Path, progreso: Callable[[int, int], None] | None, cache: Path | None) -> list[dict]:
    if cache is None:
        return docling_extractor.extraer(ruta, progreso)
    v = validar_pdf(ruta)                                    # un acierto de caché no se salta la validación (tipo, tamaño, páginas)
    if not v.ok:
        raise ExtraccionError(v.mensaje, v.codigo, v.mensaje)
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    archivo = cache / f"{v.sha256[:16]}.json"
    if archivo.exists():
        try:
            bloques = json.loads(archivo.read_text(encoding="utf-8"))
            if _valido(bloques):
                return bloques
        except ValueError:
            pass                                             # caché dañada o manipulada: se vuelve a extraer
    bloques = docling_extractor.extraer(ruta, progreso)
    descriptor = os.open(archivo, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # el texto de un manual real no debe quedar legible por otros
    with os.fdopen(descriptor, "w", encoding="utf-8") as f:
        json.dump(bloques, f, ensure_ascii=False)
    return bloques


def leer_documento(ruta: Path, doc_id: str, tipo_doc: Literal["normativa", "manual_control"], avisos: list[str] | None = None,
                   progreso: Callable[[int, int], None] | None = None, cache: Path | None = None) -> list[Seccion]:
    """Secciones de un PDF. `avisos` recibe las advertencias del seccionado (incertidumbre, figuras, duplicados)."""
    return parsear_bloques(_bloques(Path(ruta), progreso, cache), doc_id, tipo_doc, pdf=Path(ruta), avisos=avisos)
