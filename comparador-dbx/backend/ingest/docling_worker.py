"""Trabajador de Docling: corre en un SUBPROCESO que `docling_parser` puede matar al vencer el timeout.

Uso: python -m backend.ingest.docling_worker <pdf> <tablas> <hilos> <paginas_por_tanda> [artefactos]
Salida por stdout, una línea JSON por evento:
  {"progreso": [paginas_hechas, total]}   tras cada tanda
  {"bloques": [...]}                      al final
Cada bloque: {"texto", "pagina", "tipo"}. Las tablas se exportan como texto (markdown) para no
perder contenido, y se descartan encabezados y pies de página.
"""
import json
import sys

OMITIR = {"page_header", "page_footer"}


def main(pdf: str, tablas: str, hilos: int, por_tanda: int, artefactos: str = "") -> None:
    import pymupdf
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import AcceleratorOptions, PdfPipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.doc import TableItem

    with pymupdf.open(pdf) as d:
        total = d.page_count

    o = PdfPipelineOptions()
    o.do_ocr = False                       # docs/07: sin OCR
    o.generate_page_images = False
    o.do_table_structure = tablas != "off"
    if o.do_table_structure:
        o.table_structure_options.mode = TableFormerMode.ACCURATE if tablas == "accurate" else TableFormerMode.FAST
    o.accelerator_options = AcceleratorOptions(num_threads=hilos, device="cpu")
    if artefactos:
        o.artifacts_path = artefactos
    conversor = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=o)})

    bloques = []
    for inicio in range(1, total + 1, por_tanda):
        fin = min(inicio + por_tanda - 1, total)
        doc = conversor.convert(pdf, page_range=(inicio, fin)).document
        for item, _ in doc.iterate_items():
            if not getattr(item, "prov", None) or getattr(item.label, "value", "") in OMITIR:
                continue
            texto = item.export_to_markdown(doc) if isinstance(item, TableItem) else getattr(item, "text", "")
            if texto and texto.strip():
                tipo = "tabla" if isinstance(item, TableItem) else item.label.value
                bloques.append({"texto": texto.strip(), "pagina": item.prov[0].page_no, "tipo": tipo})
        print(json.dumps({"progreso": [fin, total]}), flush=True)
    print(json.dumps({"bloques": bloques}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), *(sys.argv[5:6]))
