"""Tabla de recuperación (backend/retrieval/tabla.py): unitaria, sin modelos."""
import pymupdf
import pytest

from backend.models import Seccion
from backend.retrieval.tabla import COLUMNAS, tabla_recuperacion


def _pdf(tmp_path, paginas):
    ruta = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    for texto in paginas:
        doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 780), texto, fontsize=10)
    doc.save(ruta); doc.close()
    return ruta


def _seccion(id_, texto, pagina=1, hoja=True, **kw):
    campos = dict(id=id_, doc_id="D", tipo_doc="normativa", nivel="articulo", identificador=id_, titulo=None, ruta=["TÍTULO I"],
                  texto_literal=texto, pagina_inicio=pagina, pagina_fin=pagina, seccionado_incierto=False, estrategia="patron", es_hoja=hoja)
    campos.update(kw)
    return Seccion(**campos)


def test_columnas_y_una_fila_por_seccion(tmp_path):
    pdf = _pdf(tmp_path, ["Artículo 1.- Objeto de la norma. Regula el cumplimiento."])
    t = tabla_recuperacion([_seccion("Art. 1", "Artículo 1.- Objeto de la norma. Regula el cumplimiento.")], pdf, "Norma")
    assert list(t.columns) == COLUMNAS and len(t) == 1
    f = t.iloc[0]
    assert f["Rol"] == "se compara (hoja)" and f["Sub-chunks"] == 1 and f["Ruta"] == "TÍTULO I" and f["Págs"] == "1"


def test_inicio_en_el_pdf_marca_check_si_coincide_y_cruz_si_no(tmp_path):
    pdf = _pdf(tmp_path, ["Artículo 1.- Objeto de la norma."])
    t = tabla_recuperacion([_seccion("Art. 1", "Artículo 1.- Objeto de la norma."), _seccion("Art. 2", "Texto que no está en el documento")], pdf, "N")
    assert list(t["Inicio en el PDF"]) == ["✔", "✘"]


def test_un_contenedor_agrupa_y_no_tiene_subchunks(tmp_path):
    pdf = _pdf(tmp_path, ["TÍTULO I"])
    t = tabla_recuperacion([_seccion("T1", "TÍTULO I", nivel="titulo", hoja=False)], pdf, "N")
    assert t.iloc[0]["Rol"] == "agrupa" and t.iloc[0]["Sub-chunks"] == 0


def test_incierto_rango_de_paginas_y_texto_en_espanol(tmp_path):
    pdf = _pdf(tmp_path, ["Artículo 5.- ¿Quién es el obligado? El año siguiente.", "continúa"])
    s = _seccion("Art. 5", "Artículo 5.- ¿Quién es el obligado? El año siguiente.\ncontinúa", pagina_inicio=1, pagina_fin=2, seccionado_incierto=True)
    f = tabla_recuperacion([s], pdf, "N").iloc[0]
    assert f["Incierto"] == "⚠" and f["Págs"] == "1-2" and "¿Quién" in f["Inicio del texto"] and "⏎" in f["Fin del texto"] + f["Inicio del texto"] + "⏎"


@pytest.mark.parametrize("pagina_inicio", [1, 2, 3])
def test_acepta_que_el_inicio_este_en_una_pagina_vecina(tmp_path, pagina_inicio):
    pdf = _pdf(tmp_path, ["relleno", "Artículo 9.- Texto que empieza aquí", "relleno"])
    t = tabla_recuperacion([_seccion("Art. 9", "Artículo 9.- Texto que empieza aquí", pagina=pagina_inicio, pagina_fin=pagina_inicio)], pdf, "N")
    assert t.iloc[0]["Inicio en el PDF"] == "✔"


def test_titulo_visible_usa_el_titulo_de_la_seccion_o_la_primera_linea_sin_su_numeracion():
    from backend.retrieval.tabla import titulo_visible
    con = _seccion("3.2", "3.2 Etapas del sistema.\ntexto", identificador="3.2", titulo="Etapas del sistema")
    sin = _seccion("3.1", "3.1 Administración del Riesgo de LA/FT (ARLAFT).\ntexto", identificador="3.1", titulo=None)
    larga = _seccion("9", "9 " + "palabra " * 40, identificador="9", titulo=None)
    assert titulo_visible(con) == "Etapas del sistema"
    assert titulo_visible(sin) == "Administración del Riesgo de LA/FT (ARLAFT)."
    assert len(titulo_visible(larga)) <= 90


def test_guardar_csv_neutraliza_las_formulas_de_los_textos_del_documento(tmp_path):
    import pandas as pd
    from backend.retrieval.tabla import guardar_csv
    t = pd.DataFrame({"Título": ["=HYPERLINK(\"http://x\",\"clic\")", "+1+1", "-2", "@SUM(A1)", "\tcmd", "Texto normal", None], "Págs": [1, 2, 3, 4, 5, 6, 7]})
    ruta = tmp_path / "t.csv"
    guardar_csv(t, ruta)
    import csv
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        celdas = [fila[0] for fila in list(csv.reader(f))[1:]]
    assert all(c.startswith("'") for c in celdas[:5])                              # ninguna celda empieza como fórmula
    assert celdas[5] == "Texto normal" and celdas[6] == ""
    assert t["Título"][0].startswith("=")                                           # no modifica el DataFrame original
