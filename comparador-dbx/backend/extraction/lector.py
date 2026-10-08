"""Lee un PDF y devuelve sus secciones: Docling (extracción) + cascada de seccionado, en un solo paso.

Lo usan los notebooks y, después, la API. `cache` (opcional) es una carpeta donde se guardan los bloques de Docling por SHA-256 del PDF:
la extracción de un manual largo tarda 6-10 minutos y así no se repite entre notebooks. Es solo de desarrollo; la app no persiste nada.
"""
import hashlib
import json
from pathlib import Path
from typing import Callable, Literal

from backend.extraction import docling_extractor
from backend.extraction.sectioner import parsear_bloques
from backend.models import Seccion


def _bloques(ruta: Path, progreso: Callable[[int, int], None] | None, cache: Path | None) -> list[dict]:
    if cache is None:
        return docling_extractor.extraer(ruta, progreso)
    cache.mkdir(parents=True, exist_ok=True)
    archivo = cache / f"{hashlib.sha256(Path(ruta).read_bytes()).hexdigest()[:16]}.json"
    if archivo.exists():
        return json.loads(archivo.read_text(encoding="utf-8"))
    bloques = docling_extractor.extraer(ruta, progreso)
    archivo.write_text(json.dumps(bloques, ensure_ascii=False), encoding="utf-8")
    return bloques


def leer_documento(ruta: Path, doc_id: str, tipo_doc: Literal["normativa", "manual_control"], avisos: list[str] | None = None,
                   progreso: Callable[[int, int], None] | None = None, cache: Path | None = None) -> list[Seccion]:
    """Secciones de un PDF. `avisos` recibe las advertencias del seccionado (incertidumbre, figuras, duplicados)."""
    return parsear_bloques(_bloques(Path(ruta), progreso, cache), doc_id, tipo_doc, pdf=Path(ruta), avisos=avisos)
