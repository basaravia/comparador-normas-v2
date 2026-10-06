"""backend/ingest/pdf_metadata.py — texto de portada y metadatos nativos limpios (RF-03)."""
from backend.ingest.pdf_metadata import MAX_CARACTERES, MAX_VALOR, metadatos_limpios, texto_primeras_paginas


def test_solo_lee_las_dos_primeras_paginas(hacer_pdf):
    ruta = hacer_pdf(textos=["PAGINA-UNO", "PAGINA-DOS", "PAGINA-TRES"])
    texto = texto_primeras_paginas(ruta)
    assert "PAGINA-UNO" in texto and "PAGINA-DOS" in texto
    assert "PAGINA-TRES" not in texto


def test_se_puede_pedir_menos_paginas(hacer_pdf):
    assert texto_primeras_paginas(hacer_pdf(textos=["UNO", "DOS"]), paginas=1) == "UNO"


def test_documento_de_una_pagina(hacer_pdf):
    assert texto_primeras_paginas(hacer_pdf(textos=["SOLO"])) == "SOLO"


def test_texto_acotado_a_max_caracteres(hacer_pdf):
    pagina = "\n".join(["linea de relleno numero cero uno dos tres cuatro cinco seis"] * 90)  # ~5.400 car.
    texto = texto_primeras_paginas(hacer_pdf(textos=[pagina, pagina]))
    assert len(texto) == MAX_CARACTERES == 6000


def test_texto_sin_espacios_al_borde(hacer_pdf):
    texto = texto_primeras_paginas(hacer_pdf(textos=["", "contenido"]))  # página 1 vacía
    assert texto == "contenido"


def test_metadatos_limpios():
    nativos = {
        "format": "PDF 1.7",                       # no es un metadato del documento
        "title": "  Manual de\x00 Tesorería\t\n ",  # control y espacios fuera
        "author": "",
        "subject": None,
        "encryption": None,
        "keywords": "a" * 500,                     # acotado
        "pages": 3,                                # no texto: se convierte
    }
    assert metadatos_limpios(nativos) == {
        "title": "Manual de Tesorería",
        "keywords": "a" * MAX_VALOR,
        "pages": "3",
    }


def test_metadatos_solo_con_control_quedan_fuera():
    assert metadatos_limpios({"title": "\x00\x01\n\t", "author": "   "}) == {}


def test_metadatos_reales_de_un_pdf(hacer_pdf):
    import pymupdf
    with pymupdf.open(hacer_pdf(metadatos={"title": "Norma X", "author": "SB"})) as doc:
        limpios = metadatos_limpios(doc.metadata)
    assert limpios["title"] == "Norma X" and limpios["author"] == "SB"
    assert "format" not in limpios
