"""backend/ingest/validation.py — límites, cabecera, corruptos, contraseña, PDF reparado y nombre seguro (RF-04)."""
import hashlib
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from backend.config import settings
from backend.ingest import validation
from backend.ingest.validation import nombre_seguro, validar_pdf

TEXTO_50 = "x" * 50   # justo el mínimo de caracteres para que una página cuente como "con texto"
TEXTO_49 = "x" * 49
# Mensajes literales de docs/05 (tabla de errores).
MSJ_ESCANEADO = "Este documento parece ser una imagen escaneada. Por ahora solo podemos leer PDFs con texto seleccionable."
MSJ_LIMITES = "El archivo supera el máximo de 100 páginas o 20 MB. Divídelo o consulta con el equipo de soporte."
RAIZ = Path(__file__).resolve().parent.parent  # comparador-dbx/


def con_settings(monkeypatch, **cambios):
    monkeypatch.setattr(validation, "settings", replace(settings, **cambios))


# --- Aceptado -----------------------------------------------------------------------

def test_pdf_valido_devuelve_paginas_sha256_y_metadatos(hacer_pdf):
    ruta = hacer_pdf(textos=["Página uno " * 10, "Página dos " * 10], metadatos={"title": "Manual", "author": "Banco"})
    v = validar_pdf(ruta)
    assert v.ok and v.codigo is None and v.mensaje is None
    assert v.paginas == 2
    assert v.sha256 == hashlib.sha256(ruta.read_bytes()).hexdigest()
    assert v.metadatos["title"] == "Manual" and v.metadatos["author"] == "Banco"
    assert v.advertencia is None  # PDF sano: sin advertencia de reparación


def test_mismo_contenido_mismo_sha256(hacer_pdf, tmp_path):
    a = hacer_pdf("a.pdf")
    b = tmp_path / "b.pdf"
    b.write_bytes(a.read_bytes())
    assert validar_pdf(a).sha256 == validar_pdf(b).sha256


def test_extension_no_importa_si_la_cabecera_es_pdf(hacer_pdf):
    assert validar_pdf(hacer_pdf("documento.txt")).ok


# --- Páginas: MAX_PAGES (RF-04) ------------------------------------------------------

def test_justo_max_pages_se_acepta(hacer_pdf):
    v = validar_pdf(hacer_pdf(textos=["Texto de relleno suficiente para contar " * 3] * settings.MAX_PAGES))
    assert v.ok and v.paginas == settings.MAX_PAGES


def test_max_pages_mas_uno_se_rechaza(hacer_pdf):
    v = validar_pdf(hacer_pdf(textos=["Texto de relleno suficiente para contar " * 3] * (settings.MAX_PAGES + 1)))
    assert not v.ok and v.codigo == "ERR-ING-002"
    assert v.mensaje == MSJ_LIMITES  # con MAX_PAGES=100 y MAX_MB=20 (RF-04)


# --- Tamaño: MAX_MB (se usa MAX_MB=1 para no escribir 20 MB en disco) -----------------

def test_justo_max_mb_pasa_el_control_de_tamano(monkeypatch, tmp_path):
    con_settings(monkeypatch, MAX_MB=1)
    ruta = tmp_path / "limite.pdf"
    ruta.write_bytes(b"%PDF-1.7\n" + b"0" * (1024**2 - 9))  # exactamente 1 MiB
    assert ruta.stat().st_size == 1024**2
    assert validar_pdf(ruta).codigo == "ERR-ING-003"  # pasa el tamaño; falla después al abrirlo


def test_max_mb_mas_un_byte_se_rechaza_sin_abrirlo(monkeypatch, tmp_path):
    con_settings(monkeypatch, MAX_MB=1)
    ruta = tmp_path / "grande.pdf"
    ruta.write_bytes(b"%PDF-1.7\n" + b"0" * (1024**2 - 8))  # 1 MiB + 1 byte
    v = validar_pdf(ruta)
    assert not v.ok and v.codigo == "ERR-ING-002"


# --- Escaneo: SCAN_TEXT_RATIO --------------------------------------------------------

@pytest.mark.parametrize("con_texto, ok", [(3, True), (2, False)])  # 3/5 = 0,6 (límite) · 2/5 = 0,4
def test_proporcion_de_paginas_con_texto_en_el_limite(monkeypatch, hacer_pdf, con_texto, ok):
    con_settings(monkeypatch, SCAN_TEXT_RATIO=0.6)
    v = validar_pdf(hacer_pdf(textos=[TEXTO_50] * con_texto + [""] * (5 - con_texto)))
    assert v.ok is ok
    if not ok:
        assert v.codigo == "ERR-ING-001" and v.mensaje == MSJ_ESCANEADO


@pytest.mark.parametrize("texto, ok", [(TEXTO_50, True), (TEXTO_49, False)])
def test_una_pagina_cuenta_con_texto_desde_50_caracteres(monkeypatch, hacer_pdf, texto, ok):
    con_settings(monkeypatch, SCAN_TEXT_RATIO=1.0)
    assert validar_pdf(hacer_pdf(textos=[texto])).ok is ok


def test_pdf_solo_con_imagen_se_rechaza_como_escaneado(hacer_pdf, tmp_path):
    origen = hacer_pdf("origen.pdf")
    with pymupdf.open(origen) as src:
        pix = src[0].get_pixmap(dpi=40)
    doc = pymupdf.open()
    doc.new_page().insert_image(doc[0].rect, pixmap=pix)
    doc.save(tmp_path / "escaneado.pdf")
    doc.close()
    assert validar_pdf(tmp_path / "escaneado.pdf").codigo == "ERR-ING-001"


# --- No se puede abrir: ERR-ING-003 ---------------------------------------------------

@pytest.mark.parametrize("contenido", [
    b"esto no es un pdf, es texto plano",
    b"\x89PNG\r\n\x1a\n" + b"0" * 100,       # imagen renombrada a .pdf
    b"",                                     # archivo vacío
    b"%PDF",                                 # cabecera incompleta
    b"%PDF-1.4\n" + b"basura" * 50,          # corrupto
])
def test_cabecera_falsa_vacio_o_corrupto(tmp_path, contenido):
    ruta = tmp_path / "x.pdf"
    ruta.write_bytes(contenido)
    v = validar_pdf(ruta)
    assert not v.ok and v.codigo == "ERR-ING-003"
    assert v.mensaje == "No pudimos abrir este archivo. Verifica que sea un PDF válido y sin contraseña."


def test_pdf_con_contrasena(hacer_pdf):
    ruta = hacer_pdf(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="usuario", owner_pw="dueno")
    assert validar_pdf(ruta).codigo == "ERR-ING-003"


def test_pdf_sin_paginas(tmp_path):
    ruta = tmp_path / "vacio.pdf"
    ruta.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                     b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")
    assert validar_pdf(ruta).codigo == "ERR-ING-003"


def test_pdf_truncado_se_rechaza(hacer_pdf):
    ruta = hacer_pdf()
    datos = ruta.read_bytes()
    ruta.write_bytes(datos[: len(datos) // 2])
    v = validar_pdf(ruta)
    # docs/14 #21: MuPDF lo repara, pero la página quedó sin texto -> truncado, no abrible.
    assert not v.ok and v.codigo == "ERR-ING-003"


# --- PDF reparado por MuPDF (docs/14 #21) ----------------------------------------------

AVISO_REPARADO = "Revisa que estén todas las páginas."


def test_pdf_sin_tabla_xref_se_acepta_con_advertencia(monkeypatch, hacer_pdf):
    con_settings(monkeypatch, SCAN_TEXT_RATIO=0.6)
    ruta = hacer_pdf(textos=[TEXTO_50 + " uno", TEXTO_50 + " dos", TEXTO_50 + " tres"])
    datos = ruta.read_bytes()
    ruta.write_bytes(datos[: datos.index(b"xref")])  # sin tabla de referencias ni trailer
    v = validar_pdf(ruta)
    assert v.ok and v.codigo is None and v.paginas == 3
    assert v.sha256 == hashlib.sha256(ruta.read_bytes()).hexdigest()
    assert v.advertencia and AVISO_REPARADO in v.advertencia


def test_pdf_de_varias_paginas_truncado_a_la_mitad_es_err_ing_003_no_001(monkeypatch, hacer_pdf):
    con_settings(monkeypatch, SCAN_TEXT_RATIO=0.6)
    ruta = hacer_pdf(textos=[TEXTO_50] * 6)
    datos = ruta.read_bytes()
    ruta.write_bytes(datos[: len(datos) // 2])  # MuPDF lo repara: 3 de 6 páginas con texto (0,5 < 0,6)
    v = validar_pdf(ruta)
    assert not v.ok and v.codigo == "ERR-ING-003"  # no se confunde con un escaneado (ERR-ING-001)
    assert v.advertencia is None


@pytest.mark.parametrize("muestra", ["MOCK-DEMO-01.pdf", "MOCK-DEMO-02.pdf", "MOCK-DEMO-03.pdf"])
def test_mock_sano_se_acepta_sin_advertencia(muestra):
    v = validar_pdf(RAIZ / "samples" / muestra)
    assert v.ok and v.paginas > 0 and v.advertencia is None


# --- nombre_seguro (path traversal y nombres raros) -------------------------------------

@pytest.mark.parametrize("nombre, esperado", [
    ("manual.pdf", "manual.pdf"),
    ("../../etc/passwd", "passwd"),
    ("/etc/passwd.pdf", "passwd.pdf"),
    ("a/../../secreto.pdf", "secreto.pdf"),
    ("..\\..\\windows\\x.pdf", ".._.._windows_x.pdf"),  # en Linux "\" no separa: se neutraliza
    ("..", "documento.pdf"),
    ("...", "documento.pdf"),
    ("a/..", "documento.pdf"),
    ("", "documento.pdf"),
    ("mal<nombre>|*?.pdf", "mal_nombre____.pdf"),
    ("nulo\x00.pdf", "nulo_.pdf"),
    ("Señalización año 2026.pdf", "Señalización año 2026.pdf"),
])
def test_nombre_seguro(nombre, esperado):
    assert nombre_seguro(nombre) == esperado


def test_nombre_seguro_acorta_nombres_largos_y_conserva_la_extension():
    salida = nombre_seguro("x" * 300 + ".pdf")
    assert salida == "x" * 100 + ".pdf"


def test_nombre_seguro_acota_la_extension():
    assert nombre_seguro("a." + "p" * 50) == "a." + "p" * 9  # sufijo de 10 caracteres con el punto


def test_nombre_seguro_nunca_deja_separadores_de_ruta():
    for nombre in ["../../a.pdf", "a/b/c.pdf", "..\\b.pdf", "/", "./.././x"]:
        salida = nombre_seguro(nombre)
        assert "/" not in salida and "\\" not in salida and salida not in ("", ".", "..")
