"""Trabajador de Docling: corre en un SUBPROCESO que `docling_extractor` puede matar al vencer el timeout.

Uso: python -m backend.extraction.docling_worker <pdf> <tablas> <hilos> <paginas_por_tanda> [artefactos]
Salida por stdout, una línea JSON por evento:
  {"progreso": [paginas_hechas, total]}   tras cada tanda
  {"bloques": [...]}                      al final
Cada bloque (docs/07 §1): {"texto", "pagina", "tipo": encabezado|parrafo|tabla|lista, "nivel"?}.
`nivel` solo en encabezados (0 = título del documento, 1.. = nivel de sección de Docling). Las tablas se exportan como texto (markdown) para no
perder contenido, y se descartan encabezados y pies de página.
"""
import json
import os
import sys

OMITIR = {"page_header", "page_footer"}


def _tipo(item, es_tabla: bool) -> str:
    """Etiqueta de Docling → tipo de docs/07 §1."""
    if es_tabla:
        return "tabla"
    return {"title": "encabezado", "section_header": "encabezado", "list_item": "lista"}.get(item.label.value, "parrafo")


def _imagen(item, doc) -> dict:
    """Posición y tamaño de una imagen, relativos a su página (sin generar la imagen: no cuesta RAM)."""
    prov = item.prov[0]
    pagina = doc.pages[prov.page_no].size
    b = prov.bbox.to_top_left_origin(pagina.height)
    ancho, alto = max(b.r - b.l, 1.0), max(b.b - b.t, 1.0)
    return {"pagina": prov.page_no, "fraccion": ancho * alto / (pagina.width * pagina.height), "forma": round(ancho / alto, 1),
            "tamano": (round(ancho), round(alto)), "arriba": b.t / pagina.height}


def _figuras(imagenes: list[dict], paginas: int) -> list[dict]:
    """Imágenes que parecen figuras con contenido: se descartan logos y sellos (se repiten con el mismo tamaño en varias páginas),
    banners de encabezado (muy anchos o pegados al borde superior) y códigos QR o iconos (menos del 5 % de la página)."""
    veces = {}
    for i in imagenes:
        veces[i["tamano"]] = veces.get(i["tamano"], 0) + 1
    logo = {t for t, n in veces.items() if n >= max(3, paginas // 2)}
    return [{"pagina": i["pagina"], "fraccion": round(i["fraccion"], 3)} for i in imagenes
            if i["tamano"] not in logo and i["fraccion"] >= 0.05 and i["forma"] <= 4 and i["arriba"] > 0.12]


def main(pdf: str, tablas: str, hilos: int, por_tanda: int, artefactos: str = "") -> None:
    import pymupdf
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import AcceleratorOptions, PdfPipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.doc import PictureItem, TableItem

    with pymupdf.open(pdf) as d:
        total = d.page_count

    o = PdfPipelineOptions()
    o.do_ocr = False                       # docs/07: sin OCR
    o.generate_page_images = False
    o.do_table_structure = tablas != "off"
    if o.do_table_structure:
        o.table_structure_options.mode = TableFormerMode.ACCURATE if tablas == "accurate" else TableFormerMode.FAST
    o.accelerator_options = AcceleratorOptions(num_threads=hilos, device=os.environ["DOCLING_DEVICE"])   # auto | cpu | cuda | mps
    if artefactos:
        o.artifacts_path = artefactos
    conversor = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=o)})

    bloques, imagenes = [], []
    for inicio in range(1, total + 1, por_tanda):
        fin = min(inicio + por_tanda - 1, total)
        doc = conversor.convert(pdf, page_range=(inicio, fin)).document
        for item, _ in doc.iterate_items():
            if isinstance(item, PictureItem) and getattr(item, "prov", None):
                imagenes.append(_imagen(item, doc))
                continue
            if not getattr(item, "prov", None) or getattr(item.label, "value", "") in OMITIR:
                continue
            texto = item.export_to_markdown(doc) if isinstance(item, TableItem) else getattr(item, "text", "")
            if texto and texto.strip():
                tipo = _tipo(item, isinstance(item, TableItem))
                bloque = {"texto": texto.strip(), "pagina": item.prov[0].page_no, "tipo": tipo}
                if tipo == "encabezado":
                    bloque["nivel"] = 0 if item.label.value == "title" else getattr(item, "level", 1)
                if tipo == "lista" and getattr(item, "enumerated", False) and getattr(item, "marker", ""):
                    bloque["marcador"] = item.marker.strip()      # Docling quita la numeración del texto: 1., 2., a), b)
                bloques.append(bloque)
        print(json.dumps({"progreso": [fin, total]}), flush=True)
    print(json.dumps({"figuras": _figuras(imagenes, total)}), flush=True)
    print(json.dumps({"bloques": bloques}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), *(sys.argv[5:6]))
