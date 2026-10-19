"""Genera `samples/ejemplo.json` (docs/13 D2): secciones ya extraídas de una norma y un manual, para "Cargar ejemplo" sin ejecutar Docling.

    python scripts/precompute_samples.py NORMA.pdf MANUAL.pdf [--articulos 31-48] [--cache DIR_BLOQUES]

Solo texto de la norma y del manual indicados (los MOCK son ficticios y la norma es una ley pública). Los embeddings NO se guardan: dependen del
modelo del stage y se calculan al comparar.
"""
import argparse
import json
import re
from pathlib import Path

from backend.extraction.lector import leer_documento
from backend.ingest.validation import validar_pdf

RAIZ = Path(__file__).resolve().parent.parent


def _articulo(s) -> int | None:
    m = re.match(r"art[ií]culo\s+(\d+)", s.identificador, re.I) if s.es_hoja else None
    return int(m.group(1)) if m else None


def _documento(pdf: Path, doc_id: str, tipo: str, cache: Path | None, rango: tuple[int, int] | None) -> dict:
    v = validar_pdf(pdf)
    secs = leer_documento(pdf, doc_id, tipo, cache=cache)
    if rango:
        hojas = [s for s in secs if (n := _articulo(s)) is not None and rango[0] <= n <= rango[1]]
        quedan = {s.id for s in hojas}
        secs = [s for s in secs if s.id in quedan or (not s.es_hoja and any(h.ruta[:len(s.ruta)] == s.ruta for h in hojas))]
    return {"doc_id": doc_id, "nombre": pdf.name, "tipo": tipo, "paginas": v.paginas, "sha256": v.sha256, "metadatos": {},
            "secciones": [s.model_dump(mode="json") for s in secs]}


def main(a) -> None:
    ini, fin = (int(x) for x in a.articulos.split("-"))
    cache = Path(a.cache) if a.cache else None
    docs = [_documento(Path(a.norma), "N", "normativa", cache, (ini, fin)), _documento(Path(a.manual), "M", "manual_control", cache, None)]
    salida = RAIZ / "samples" / "ejemplo.json"
    salida.parent.mkdir(exist_ok=True)
    salida.write_text(json.dumps({"documentos": docs}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{salida}: " + " · ".join(f"{d['nombre']} {sum(s['es_hoja'] for s in d['secciones'])} hojas" for d in docs))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("norma"); p.add_argument("manual")
    p.add_argument("--articulos", default="31-48"); p.add_argument("--cache", default="")
    main(p.parse_args())
