"""Seccionado en cascada de L2 (docs/07 §2, docs/13): lógica determinista, sin modelo ni Docling.

Los bloques se escriben a mano (una línea = un bloque, como los que emite Docling). Regla de docs/07: un patrón
vale para el documento si aparece >= 3 veces con numeración creciente; por eso cada fixture trae >= 3 apariciones,
salvo las pruebas que comprueban justamente lo contrario.
"""
import time

import pymupdf
import pytest
from pydantic import ValidationError

from backend.config import settings
from backend.extraction import sectioner
from backend.extraction.patterns import CORTE_ARTICULOS, PATRONES, Patron, numero
from backend.extraction.sectioner import SeccionadoError, parsear_bloques
from backend.models import Seccion


def bloques(texto, pagina=1, tipo="parrafo"):
    """Una línea de `texto` = un bloque."""
    return [{"texto": x, "pagina": pagina, "tipo": tipo} for x in texto.split("\n")]


def seccionar(texto, tipo_doc="normativa", pdf=None):
    avisos = []
    return parsear_bloques(bloques(texto), "N1", tipo_doc, pdf=pdf, avisos=avisos), avisos


def ids(secciones):
    return [s.id for s in secciones]


def pdf_con_lineas(ruta, lineas):
    """PDF de una página; `lineas` = [(texto, tamaño, negrita)], una por renglón."""
    doc = pymupdf.open()
    pagina = doc.new_page()
    y = 40
    for texto, tam, negrita in lineas:
        pagina.insert_text((40, y), texto, fontsize=tam, fontname="hebo" if negrita else "helv")
        y += tam + 8
    doc.save(ruta)
    doc.close()
    return ruta


# --- Modelo -----------------------------------------------------------------------------------------

def test_seccion_valida_el_contrato():
    s = Seccion(id="N1:ART-15", doc_id="N1", tipo_doc="normativa", nivel="articulo", identificador="Art. 15",
                ruta=["LIBRO I"], texto_literal="x", pagina_inicio=1, pagina_fin=2, seccionado_incierto=False,
                estrategia="patron", es_hoja=True)
    assert s.titulo is None
    with pytest.raises(ValidationError):
        Seccion(id="x", doc_id="N1", tipo_doc="otro", nivel="a", identificador="a", ruta=[], texto_literal="",
                pagina_inicio=1, pagina_fin=1, seccionado_incierto=False, estrategia="patron", es_hoja=True)


# --- Esquemas de encabezado (tabla de docs/13) ------------------------------------------------------

def test_articulo():
    r, _ = seccionar("Artículo 1.- Objeto\ntexto uno\nArtículo 2.- Alcance\ntexto dos\nArtículo 3.- Vigencia\ntexto tres")
    assert ids(r) == ["N1:ART-1", "N1:ART-2", "N1:ART-3"]
    assert [s.identificador for s in r] == ["Artículo 1", "Artículo 2", "Artículo 3"]
    assert r[0].titulo == "Objeto" and r[0].nivel == "articulo" and r[0].estrategia == "patron"
    assert all(s.es_hoja and not s.seccionado_incierto and s.ruta == [] for s in r)


def test_art_abreviado_y_mayusculas():
    r, _ = seccionar("ART. 1.- Objeto\nuno\nART. 2.- Alcance\ndos\nArt. 3.- Vigencia\ntres\nARTÍCULO 4.- Fin\ncuatro")
    assert ids(r) == ["N1:ART-1", "N1:ART-2", "N1:ART-3", "N1:ART-4"]
    assert [s.identificador for s in r] == ["ART. 1", "ART. 2", "Art. 3", "ARTÍCULO 4"]


def test_seccion_y_sec():
    r, _ = seccionar("Sección 1\nuno\nSección 2\ndos\nSEC. 3\ntres\nSECCIÓN 4\ncuatro", "manual_control")
    assert ids(r) == ["N1:SEC-1", "N1:SEC-2", "N1:SEC-3", "N1:SEC-4"]
    assert all(s.nivel == "seccion" for s in r)


def test_romanos():
    r, _ = seccionar("I. INTRODUCCIÓN\nuno\nII. OBJETIVO\ndos\nIII. ALCANCE\ntres\nIV. CIERRE\ncuatro", "manual_control")
    assert ids(r) == ["N1:R-1", "N1:R-2", "N1:R-3", "N1:R-4"]
    assert [s.titulo for s in r] == ["INTRODUCCIÓN", "OBJETIVO", "ALCANCE", "CIERRE"]


def test_letras_como_secciones_de_un_manual():
    r, _ = seccionar("A. Objetivo\nuno\nB. Alcance\ndos\nC. Responsables\ntres\nD. Vigencia\ncuatro", "manual_control")
    assert ids(r) == ["N1:LET-1", "N1:LET-2", "N1:LET-3", "N1:LET-4"]


def test_numeracion_jerarquica_3_2_1():
    r, _ = seccionar("1. Introducción\nt\n1.1 Alcance\nt\n1.2 Objeto\nt\n2. Controles\nt\n2.1 Accesos\nt\n2.1.1 Claves\nt",
                     "manual_control")
    assert ids(r) == ["N1:N-1", "N1:N-1/N-1.1", "N1:N-1/N-1.2", "N1:N-2", "N1:N-2/N-2.1", "N1:N-2/N-2.1/N-2.1.1"]
    clave = r[-1]
    assert clave.ruta == ["2", "2.1"] and clave.es_hoja and not r[0].es_hoja
    assert clave.nivel == "numeral" and not any(s.seccionado_incierto for s in r)


def test_ordinales_hasta_decimo_primero():
    r, _ = seccionar("PRIMERA.- Uno\nt\nSegunda.- Dos\nt\nTERCERA.- Tres\nt\nDÉCIMO.- Diez\nt\nDÉCIMO PRIMERO.- Once\nt")
    assert ids(r) == ["N1:DISP-1", "N1:DISP-2", "N1:DISP-3", "N1:DISP-10", "N1:DISP-11"]
    assert r[-1].identificador == "DÉCIMO PRIMERO"


def test_capitulo_primero_en_palabras():
    r, _ = seccionar("CAPÍTULO PRIMERO\nDEL OBJETO\nArtículo 1.- a\nCAPÍTULO SEGUNDO\nx\nArtículo 2.- b\n"
                     "CAPÍTULO TERCERO\nx\nArtículo 3.- c\nCAPÍTULO DÉCIMO PRIMERO\nx\nArtículo 4.- d")
    caps = [s for s in r if s.nivel == "capitulo"]
    assert ids(caps) == ["N1:C-1", "N1:C-2", "N1:C-3", "N1:C-11"]
    assert caps[0].titulo == "DEL OBJETO"
    assert r[1].id == "N1:C-1/ART-1" and r[1].ruta == ["CAPÍTULO PRIMERO"]
    assert not any(s.seccionado_incierto for s in r)


def test_articulo_con_sufijo_5a_y_5_bis_ordena_entre_5_y_6():
    r, _ = seccionar("Artículo 5.- a\nt\nArtículo 5-A.- b\nt\nArt. 5 bis.- c\nt\nArtículo 6.- d\nt")
    assert ids(r) == ["N1:ART-5", "N1:ART-5-A", "N1:ART-5-BIS", "N1:ART-6"]
    assert not any(s.seccionado_incierto for s in r)


def test_articulo_duplicado_conserva_ambos_con_sufijo_2_y_aviso():
    r, avisos = seccionar("Artículo 1.- a\ntexto\nArtículo 2.- b\ntexto\nARTÍCULO 2.- b repetido\ntexto\nArtículo 3.- c\ntexto")
    assert ids(r) == ["N1:ART-1", "N1:ART-2", "N1:ART-2#2", "N1:ART-3"]
    assert any("#2" in a and "ARTÍCULO 2" in a for a in avisos)


def test_literales_quedan_dentro_del_articulo():
    r, _ = seccionar("Art. 1.- Deberes:\na) uno\nb) dos\niv) cuatro\nArt. 2.- x\nt\nArt. 3.- y\nt\nArt. 4.- z\nt")
    assert ids(r) == ["N1:ART-1", "N1:ART-2", "N1:ART-3", "N1:ART-4"]
    assert "a) uno" in r[0].texto_literal and "b) dos" in r[0].texto_literal and "iv) cuatro" in r[0].texto_literal
    assert all(s.nivel != "literal" for s in r)


def test_numerales_y_romanos_dentro_de_un_articulo_no_abren_seccion_en_una_normativa():
    r, _ = seccionar("Artículo 1.- a\n1. Primero\n2. Segundo\n3. Tercero\nArtículo 2.- b\nt\nArtículo 3.- c\nI. Uno\nII. Dos\nIII. Tres")
    assert ids(r) == ["N1:ART-1", "N1:ART-2", "N1:ART-3"]
    assert "3. Tercero" in r[0].texto_literal and "III. Tres" in r[2].texto_literal


def test_disposiciones_y_su_ruta():
    r, _ = seccionar("Artículo 1.- a\nt\nArtículo 2.- b\nt\nArtículo 3.- c\nt\nDISPOSICIONES GENERALES\n"
                     "PRIMERA.- uno\nSEGUNDA.- dos\nTERCERA.- tres\nDISPOSICIÓN FINAL\nTexto final")
    assert ids(r)[3:] == ["N1:DISPOSICIONES-GENERALES", "N1:DISPOSICIONES-GENERALES/DISP-1",
                          "N1:DISPOSICIONES-GENERALES/DISP-2", "N1:DISPOSICIONES-GENERALES/DISP-3", "N1:DISPOSICION-FINAL"]
    assert r[4].ruta == ["DISPOSICIONES GENERALES"] and r[-1].ruta == []
    assert r[-1].texto_literal.endswith("Texto final")


def test_articulo_citado_dentro_de_una_disposicion_es_texto():
    r, _ = seccionar("Artículo 1.- a\nt\nArtículo 2.- b\nt\nArtículo 3.- c\nt\nDISPOSICIONES REFORMATORIAS\n"
                     "PRIMERA.- Sustitúyase:\nArt. 317.- texto del COIP\nSEGUNDA.- dos\nTERCERA.- tres")
    assert "N1:DISPOSICIONES-REFORMATORIAS/DISP-1" in ids(r)
    assert not any(s.identificador.startswith("Art. 317") for s in r)
    assert "Art. 317.- texto del COIP" in r[4].texto_literal


def test_ids_con_todas_las_abreviaturas_de_la_jerarquia():
    texto = ("LIBRO I\nl\nTÍTULO I\nt\nCAPÍTULO I\nc\nSECCIÓN I\ns\nArtículo 1.- a\ncuerpo\nSECCIÓN II\ns\nArtículo 2.- b\ncuerpo\n"
             "SECCIÓN III\ns\nArtículo 3.- c\ncuerpo\nCAPÍTULO II\nc\nArtículo 4.- d\ncuerpo\nCAPÍTULO III\nc\nArtículo 5.- e\ncuerpo\n"
             "LIBRO II\nl\nTÍTULO II\nt\nCAPÍTULO I\nc\nSECCIÓN I\ns\nArtículo 6.- f\ncuerpo\n"
             "LIBRO III\nl\nTÍTULO III\nt\nCAPÍTULO I\nc\nSECCIÓN I\ns\nArtículo 7.- g\ncuerpo")
    r, avisos = seccionar(texto)
    por_id = {s.id: s for s in r}
    assert r[0].id == "N1:L-1" and r[1].id == "N1:L-1/T-1" and r[2].id == "N1:L-1/T-1/C-1"
    assert r[3].id == "N1:L-1/T-1/C-1/SEC-1"
    art = por_id["N1:L-3/T-3/C-1/SEC-1/ART-7"]
    assert art.ruta == ["LIBRO III", "TÍTULO III", "CAPÍTULO I", "SECCIÓN I"] and art.es_hoja
    assert [s.nivel for s in r[:5]] == ["libro", "titulo", "capitulo", "seccion", "articulo"]
    assert not any(s.seccionado_incierto for s in r), avisos


def test_nivel_ausente_se_omite_de_la_ruta():
    """Sin Libro ni Sección: la ruta solo lleva Título y Capítulo."""
    texto = ("TÍTULO I\nt\nCAPÍTULO I\nc\nArtículo 1.- a\ncuerpo\nCAPÍTULO II\nc\nArtículo 2.- b\ncuerpo\nCAPÍTULO III\nc\nArtículo 3.- c\ncuerpo\n"
             "TÍTULO II\nt\nCAPÍTULO I\nc\nArtículo 4.- d\ncuerpo\nTÍTULO III\nt\nCAPÍTULO I\nc\nArtículo 5.- e\ncuerpo")
    r, avisos = seccionar(texto)
    assert r[-1].ruta == ["TÍTULO III", "CAPÍTULO I"] and r[-1].id == "N1:T-3/C-1/ART-5"
    assert not any(s.seccionado_incierto for s in r), avisos


# --- Reglas de aceptación del patrón -------------------------------------------------------------------

def test_patron_con_menos_de_3_apariciones_sin_validar_queda_como_texto():
    r, _ = seccionar("Artículo 1.- a\ntexto\nArtículo 2.- b\ntexto")
    assert len(r) == 1 and r[0].estrategia == "longitud" and r[0].seccionado_incierto
    assert "Artículo 2.- b" in r[0].texto_literal


def test_patron_sin_numeracion_creciente_no_vale():
    r, _ = seccionar("Artículo 3.- a\nt\nArtículo 2.- b\nt\nArtículo 1.- c\nt")
    assert [s.estrategia for s in r] == ["longitud"]


def test_numeral_con_menos_de_3_no_se_acepta():
    """Decisión del usuario: un numeral N.M con < 3 apariciones nunca se acepta (aunque venga en negrita)."""
    r, _ = seccionar("1. Introducción\nt\n1.1 Alcance\nt", "manual_control")
    assert [s.estrategia for s in r] == ["longitud"]


def test_numeral_con_menos_de_3_no_se_acepta_ni_en_negrita(tmp_path):
    ruta = pdf_con_lineas(tmp_path / "n.pdf", [("1. Introduccion", 10, True), ("texto", 10, False),
                                               ("1.1 Alcance", 10, True), ("texto", 10, False)])
    r = parsear_bloques(bloques("1. Introduccion\ntexto\n1.1 Alcance\ntexto"), "N1", "manual_control", pdf=ruta)
    assert all(s.nivel != "numeral" for s in r)


def test_encabezado_validado_con_menos_de_3_apariciones_se_acepta_con_aviso(tmp_path):
    """CAPÍTULO I una sola vez, en negrita y en su propia línea: patrón + negrita + línea propia."""
    ruta = pdf_con_lineas(tmp_path / "c.pdf", [("CAPITULO I", 10, True), ("Articulo 1.- Uno", 10, True),
                                               ("cuerpo del articulo uno", 10, False), ("Articulo 2.- Dos", 10, True),
                                               ("cuerpo del articulo dos", 10, False), ("Articulo 3.- Tres", 10, True),
                                               ("cuerpo del articulo tres", 10, False)])
    texto = "CAPITULO I\nArticulo 1.- Uno\ncuerpo del articulo uno\nArticulo 2.- Dos\ncuerpo del articulo dos\nArticulo 3.- Tres\ncuerpo del articulo tres"
    avisos = []
    r = parsear_bloques(bloques(texto), "N1", "normativa", pdf=ruta, avisos=avisos)
    assert ids(r) == ["N1:C-1", "N1:C-1/ART-1", "N1:C-1/ART-2", "N1:C-1/ART-3"]
    assert r[1].ruta == ["CAPITULO I"] and not any(s.seccionado_incierto for s in r)
    assert any("menos de 3 apariciones" in a and "CAPITULO I" in a for a in avisos)


def test_el_encabezado_sin_negrita_no_se_valida(tmp_path):
    ruta = pdf_con_lineas(tmp_path / "c.pdf", [("CAPITULO I", 10, False), ("Articulo 1.- Uno", 10, True), ("texto", 10, False),
                                               ("Articulo 2.- Dos", 10, True), ("texto", 10, False),
                                               ("Articulo 3.- Tres", 10, True), ("texto", 10, False)])
    r = parsear_bloques(bloques("CAPITULO I\nArticulo 1.- Uno\ntexto\nArticulo 2.- Dos\ntexto\nArticulo 3.- Tres\ntexto"),
                        "N1", "normativa", pdf=ruta)
    assert all(s.nivel != "capitulo" for s in r) and r[0].ruta == []


def test_mencion_de_un_articulo_fuera_de_negrita_se_descarta(tmp_path):
    ruta = pdf_con_lineas(tmp_path / "m.pdf", [("Articulo 1.- Uno", 10, True), ("cuerpo", 10, False),
                                               ("Articulo 2.- Dos", 10, True), ("cuerpo", 10, False),
                                               ("Articulo 3.- Tres", 10, True), ("cuerpo", 10, False),
                                               ("Articulo 4.- Cuatro", 10, True), ("cuerpo", 10, False),
                                               ("Articulo 9.- se cita sin negrita", 10, False)])
    texto = ("Articulo 1.- Uno\ncuerpo\nArticulo 2.- Dos\ncuerpo\nArticulo 3.- Tres\ncuerpo\nArticulo 4.- Cuatro\ncuerpo\n"
             "Articulo 9.- se cita sin negrita")
    avisos = []
    r = parsear_bloques(bloques(texto), "N1", "normativa", pdf=ruta, avisos=avisos)
    assert ids(r) == ["N1:ART-1", "N1:ART-2", "N1:ART-3", "N1:ART-4"]
    assert "Articulo 9.- se cita sin negrita" in r[-1].texto_literal
    assert any("Descartado por tipografía" in a for a in avisos)


# --- Árbol: lo que no se puede confiar se marca, nunca se inventa -----------------------------------------

def test_capitulo_hermano_de_un_articulo_marca_el_articulo_como_incierto():
    """Como el Artículo 1 de la LA/FT: Docling lo emite antes de CAPÍTULO I, ambos bajo el mismo TÍTULO."""
    texto = ("TÍTULO I\nt\nArtículo 1.- a\ncuerpo\nCAPÍTULO I\nc\nArtículo 2.- b\ncuerpo\nCAPÍTULO II\nc\nArtículo 3.- c\ncuerpo\n"
             "CAPÍTULO III\nc\nArtículo 4.- d\ncuerpo\nTÍTULO II\nt\nCAPÍTULO I\nc\nArtículo 5.- e\ncuerpo\n"
             "TÍTULO III\nt\nCAPÍTULO I\nc\nArtículo 6.- f\ncuerpo")
    r, avisos = seccionar(texto)
    por_id = {s.id: s for s in r}
    art1 = por_id["N1:T-1/ART-1"]
    assert art1.seccionado_incierto and art1.ruta == ["TÍTULO I"]  # ruta leída, no inventada
    assert por_id["N1:T-1/C-1/ART-2"].ruta == ["TÍTULO I", "CAPÍTULO I"]
    assert [s.id for s in r if s.seccionado_incierto] == ["N1:T-1/ART-1"]
    assert any("Seccionado incierto en Artículo 1" in a for a in avisos)


def test_numeracion_decreciente_es_incierta_y_arrastra_a_sus_hijos():
    r, avisos = seccionar("CAPÍTULO I\nc\nArtículo 1.- a\nt\nCAPÍTULO II\nc\nArtículo 2.- b\nt\nCAPÍTULO III\nc\nArtículo 3.- c\nt\n"
                          "CAPÍTULO II\nc\nArtículo 4.- d\nt")
    inciertos = [s.id for s in r if s.seccionado_incierto]
    assert inciertos == ["N1:C-2#2", "N1:C-2/ART-4"]  # el segundo CAPÍTULO II es un duplicado (#2) y decrece
    assert any("decreciente" in a for a in avisos)


def test_capitulo_que_no_empieza_en_1_es_incierto():
    r, avisos = seccionar("CAPÍTULO II\nc\nArtículo 1.- a\nt\nCAPÍTULO III\nc\nArtículo 2.- b\nt\nCAPÍTULO IV\nc\nArtículo 3.- c\nt")
    assert [s.id for s in r if s.seccionado_incierto] == ["N1:C-2", "N1:C-2/ART-1"]
    assert any("no empieza en 1" in a for a in avisos)
    assert next(s for s in r if s.id == "N1:C-2/ART-1").ruta == ["CAPÍTULO II"]  # la ruta es la leída, no una inventada


def test_los_articulos_deben_crecer_en_todo_el_documento():
    r, _ = seccionar("Artículo 1.- a\nt\nArtículo 2.- b\nt\nArtículo 3.- c\nt\nArtículo 4.- d\nt\nArtículo 2.- e\nt")
    assert [s.id for s in r if s.seccionado_incierto] == ["N1:ART-2#2"]


def test_numeral_bajo_un_padre_con_otro_numero_es_incierto():
    r, avisos = seccionar("1. Uno\nt\n1.1 Aa\nt\n1.2 Bb\nt\n2. Dos\nt\n3.1 Cc\nt\n3.2 Dd\nt", "manual_control")
    assert any("el numeral no corresponde" in a for a in avisos)
    assert [s.identificador for s in r if s.seccionado_incierto] == ["3.1", "3.2"]
    assert next(s for s in r if s.identificador == "3.1").ruta == ["2"]  # la ruta leída, no una inventada


# --- Bloques partidos por Docling y portada ---------------------------------------------------------------------

def test_bloque_con_varios_articulos_se_parte():
    unico = [{"texto": "Artículo 1.- uno. Artículo 2.- dos; Artículo 3.- tres: Artículo 4.- cuatro", "pagina": 2, "tipo": "parrafo"}]
    r = parsear_bloques(unico, "N1", "normativa")
    assert ids(r) == ["N1:ART-1", "N1:ART-2", "N1:ART-3", "N1:ART-4"]
    assert r[1].texto_literal == "Artículo 2.- dos;"


def test_una_cita_en_medio_de_una_frase_no_parte_el_bloque():
    unico = [{"texto": "Artículo 1.- conforme al artículo 5 de esta Ley. Ver artículo 6.", "pagina": 1, "tipo": "parrafo"}]
    assert CORTE_ARTICULOS.search(unico[0]["texto"]) is None


def test_lo_anterior_a_la_primera_seccion_no_es_evaluable_y_el_indice_se_descarta():
    texto = ("Memorando Nro. 1\nÍNDICE\nArtículo 1.- Objeto\nArtículo 2.- Alcance\nArtículo 3.- Vigencia\n"
             "Artículo 1.- Objeto\ncuerpo uno\nArtículo 2.- Alcance\ncuerpo dos\nArtículo 3.- Vigencia\ncuerpo tres")
    r, avisos = seccionar(texto)
    assert ids(r) == ["N1:ART-1", "N1:ART-2", "N1:ART-3"] and not avisos
    assert all("Memorando" not in s.texto_literal and "cuerpo" in s.texto_literal for s in r)


# --- Texto literal, páginas, ids ---------------------------------------------------------------------------------

def test_cada_seccion_es_subcadena_de_la_concatenacion_de_bloques_y_paginas_correctas():
    bs = [{"texto": "Artículo 1.- Uno", "pagina": 1, "tipo": "parrafo"}, {"texto": "cuerpo  con  espacios\ty tab", "pagina": 1, "tipo": "parrafo"},
          {"texto": "sigue en la pagina 2", "pagina": 2, "tipo": "parrafo"}, {"texto": "Artículo 2.- Dos", "pagina": 2, "tipo": "parrafo"},
          {"texto": "cuerpo ñandú", "pagina": 3, "tipo": "parrafo"}, {"texto": "Artículo 3.- Tres", "pagina": 3, "tipo": "parrafo"},
          {"texto": "fin", "pagina": 3, "tipo": "parrafo"}]
    r = parsear_bloques(bs, "N1", "normativa")
    todo = "\n".join(b["texto"] for b in bs)
    assert all(s.texto_literal in todo for s in r)
    assert [(s.pagina_inicio, s.pagina_fin) for s in r] == [(1, 2), (2, 3), (3, 3)]
    assert "cuerpo  con  espacios\ty tab" in r[0].texto_literal  # sin normalizar espacios


def test_texto_literal_de_secciones_por_longitud_tambien_es_literal():
    bs = [{"texto": f"parrafo {n} " + "x" * 400, "pagina": n, "tipo": "parrafo"} for n in range(1, 8)]
    r = parsear_bloques(bs, "M1", "manual_control")
    todo = "\n".join(b["texto"] for b in bs)
    assert all(s.texto_literal in todo for s in r)


# --- Nivel 3: longitud --------------------------------------------------------------------------------------------

def test_longitud_agrupa_por_seccion_chars_sin_partir_parrafos_y_es_incierto():
    bs = [{"texto": "p%d " % n + "x" * 500, "pagina": 1 + n // 3, "tipo": "parrafo"} for n in range(9)]
    r = parsear_bloques(bs, "M1", "manual_control")
    assert all(s.estrategia == "longitud" and s.seccionado_incierto and s.es_hoja and s.nivel == "bloque" for s in r)
    assert [s.id for s in r] == [f"M1:BLOQUE-{n}" for n in range(1, len(r) + 1)]
    assert len(r) == 3  # 3 párrafos de ~500 caracteres alcanzan SECCION_CHARS (1200) y cierran un grupo
    assert sum(s.texto_literal.count("\n") + 1 for s in r) == 9  # ningún párrafo se pierde ni se parte
    assert all(len(s.texto_literal) >= settings.SECCION_CHARS for s in r)
    assert r[0].pagina_inicio == 1 and r[-1].pagina_fin == bs[-1]["pagina"]


def test_un_parrafo_mas_largo_que_seccion_chars_queda_entero():
    larga = "y" * (settings.SECCION_CHARS * 3)
    r = parsear_bloques([{"texto": larga, "pagina": 1, "tipo": "parrafo"}], "M1", "manual_control")
    assert len(r) == 1 and r[0].texto_literal == larga


# --- Nivel 2: tipografía -----------------------------------------------------------------------------------------

def test_tipografia_del_pdf_marca_encabezados_por_tamano(tmp_path):
    lineas = [("Politicas generales", 16, True), ("cuerpo uno del documento", 8, False), ("cuerpo dos del documento", 8, False),
              ("Controles de acceso", 12, True), ("cuerpo tres del documento", 8, False),
              ("Gestion de claves", 12, True), ("cuerpo cuatro del documento", 8, False)]
    ruta = pdf_con_lineas(tmp_path / "t.pdf", lineas)
    r = parsear_bloques(bloques("\n".join(t for t, _, _ in lineas)), "M1", "manual_control", pdf=ruta)
    assert [s.estrategia for s in r] == ["tipografia"] * 3
    assert [s.identificador for s in r] == ["Politicas generales", "Controles de acceso", "Gestion de claves"]
    assert [s.ruta for s in r] == [[], ["Politicas generales"], ["Politicas generales"]]
    assert not any(s.seccionado_incierto for s in r)  # la tipografía no marca incierto, solo la longitud
    assert "cuerpo dos del documento" in r[0].texto_literal


def test_tipografia_con_encabezados_de_docling_sin_pdf():
    bs = [{"texto": "Introduccion", "pagina": 1, "tipo": "encabezado", "nivel": 1}, {"texto": "texto uno", "pagina": 1, "tipo": "parrafo"},
          {"texto": "Detalle", "pagina": 1, "tipo": "encabezado", "nivel": 2}, {"texto": "texto dos", "pagina": 2, "tipo": "parrafo"},
          {"texto": "Cierre", "pagina": 2, "tipo": "encabezado", "nivel": 1}, {"texto": "texto tres", "pagina": 2, "tipo": "parrafo"}]
    r = parsear_bloques(bs, "M1", "manual_control")
    assert [s.estrategia for s in r] == ["tipografia"] * 3
    assert [s.ruta for s in r] == [[], ["Introduccion"], []]


def test_menos_de_3_encabezados_tipograficos_cae_a_longitud():
    bs = [{"texto": "Introduccion", "pagina": 1, "tipo": "encabezado", "nivel": 1}, {"texto": "texto uno", "pagina": 1, "tipo": "parrafo"},
          {"texto": "Cierre", "pagina": 1, "tipo": "encabezado", "nivel": 1}, {"texto": "texto dos", "pagina": 1, "tipo": "parrafo"}]
    r = parsear_bloques(bs, "M1", "manual_control")
    assert [s.estrategia for s in r] == ["longitud"]


def test_pdf_sin_texto_no_aporta_tipografia_pero_si_los_encabezados_de_docling(tmp_path):
    ruta = tmp_path / "vacio.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(ruta)
    doc.close()
    bs = [{"texto": t, "pagina": 1, "tipo": "encabezado", "nivel": 1} for t in ("Uno", "Dos", "Tres")]
    r = parsear_bloques(bs, "M1", "manual_control", pdf=ruta)
    assert [s.estrategia for s in r] == ["tipografia"] * 3


def test_las_tablas_no_son_encabezados():
    bs = [{"texto": "| a | b |", "pagina": 1, "tipo": "tabla"}] * 3 + [{"texto": "texto", "pagina": 1, "tipo": "parrafo"}]
    assert parsear_bloques(bs, "M1", "manual_control")[0].estrategia == "longitud"


# --- Límite de bloque (entrada hostil) ----------------------------------------------------------------------------------

def test_bloque_mayor_que_seccion_bloque_max_es_err_sec_001():
    enorme = [{"texto": "a" * (settings.SECCION_BLOQUE_MAX + 1), "pagina": 1, "tipo": "parrafo"}]
    with pytest.raises(SeccionadoError) as e:
        parsear_bloques(enorme, "N1", "normativa")
    assert e.value.codigo == "ERR-SEC-001" and "demasiado grande" in e.value.para_usuario()["mensaje"]


def test_bloque_justo_en_seccion_bloque_max_se_acepta():
    justo = [{"texto": "a" * settings.SECCION_BLOQUE_MAX, "pagina": 1, "tipo": "parrafo"}]
    assert parsear_bloques(justo, "N1", "normativa")[0].estrategia == "longitud"


def test_sin_bloques_no_hay_secciones():
    assert parsear_bloques([], "N1", "normativa") == []


# --- numero() --------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("3.2.1", (3, 2, 1)), ("7", (7,)), ("IV", (4,)), ("XIV", (14,)), ("iv", (4,)), ("PRIMERA", (1,)), ("Segundo", (2,)),
    ("Tercero", (3,)), ("DÉCIMO", (10,)), ("DÉCIMO PRIMERO", (11,)), ("Vigésimo Segundo", (22,)), ("VIGÉSIMA", (20,)),
    ("ÚNICA", (1,)), ("UNICO", (1,)), ("NOVENO", (9,)), ("SÉPTIMA", (7,))])
def test_numero_esquemas(texto, esperado):
    assert numero(texto) == esperado


def test_numero_letras_solo_si_es_letra():
    assert numero("A", es_letra=True) == (1,) and numero("c", es_letra=True) == (3,)


@pytest.mark.parametrize("vacio", [None, "", "hola mundo", "XYZ?", "9.", "1..2"])
def test_numero_desconocido_es_none(vacio):
    assert numero(vacio) is None


def test_numero_ordena_5_antes_de_5a_antes_de_6():
    assert numero("5") < numero("5", "A") < numero("6")
    assert numero("5", "A") < numero("5", "B")
    assert numero("5", "bis") < numero("5", "ter") < numero("5", "quáter") < numero("6")


def test_numero_sufijo_a_es_uno_como_bis():
    assert numero("5", "A") == (5, 1) and numero("5", "bis") == (5, 1)


@pytest.mark.xfail(raises=ValueError, strict=False,
                   reason="Conocido e inalcanzable: int() rechaza > 4300 dígitos, pero parsear_bloques solo mira 300 caracteres por línea")
def test_numero_con_5000_digitos_lanza_value_error():
    assert numero("9" * 5000) is None


def test_una_linea_con_numero_de_300_digitos_no_rompe_el_seccionado():
    larga = "Artículo " + "9" * 280 + ".- x"
    bs = bloques(f"Artículo 1.- a\nt\nArtículo 2.- b\nt\n{larga}\nt\nArtículo 3.- c\nt") + [{"texto": "9" * 6000, "pagina": 1, "tipo": "parrafo"}]
    assert len(parsear_bloques(bs, "N1", "normativa")) >= 3


# --- Catálogo ----------------------------------------------------------------------------------------------------------------

def test_catalogo_claves_unicas_y_precedencia_de_docs_07():
    claves = [p.clave for p in PATRONES]
    assert len(claves) == len(set(claves))
    assert all(isinstance(p, Patron) for p in PATRONES)
    rango = {p.clave: p.rango for p in PATRONES}
    assert rango["libro"] < rango["titulo"] < rango["capitulo"] < rango["seccion"] < rango["articulo"] < rango["numeral"]
    assert rango["literal"] is None
    abreviaturas = {"libro": "L", "titulo": "T", "capitulo": "C", "seccion": "SEC", "romano": "R", "articulo": "ART",
                    "disposicion": "DISP", "numeral": "N", "letra": "LET"}
    assert sectioner.ABREVIATURA == abreviaturas


# --- Regex hostiles (appsec: ReDoS) ---------------------------------------------------------------------------------------------

N = 100_000
HOSTILES = {
    "espacios": " " * N, "tabuladores": "\t" * N, "letras": "A" * N, "puntos": "." * N,
    "punto_articulo_espacios": ". Artículo 1" + " " * N,        # el bloqueante anterior (ReDoS de CORTE_ARTICULOS)
    "punto_articulo_tabs": ". Artículo 1" + "\t" * N,
    "punto_articulo_mixto": ". Artículo 1" + " \t" * (N // 2),
    "salto_articulo_espacios": "\nArtículo 1" + " " * N,
    "punto_primera_espacios": ". PRIMERA" + " " * N,
    "primera_espacios": "PRIMERA" + " " * N,
    "guiones": "Artículo 5" + "-" * N,
    "articulos_repetidos": "Artículo 1. " * (N // 12),
    "puntos_articulo_repetidos": ". Artículo 1 " * (N // 12),
    "digitos": "Artículo " + "9" * N, "decimales": "1" + ".1" * (N // 2), "romanos": "M" * N,
    "ordinales": "DÉCIMO " * (N // 7), "saltos_con_espacios": ("\n" + " " * 50) * (N // 51),
    "literal": "a)" + " " * N, "capitulo_largo": "CAPÍTULO " + "A" * N,
}


@pytest.mark.parametrize("nombre", HOSTILES)
def test_regex_hostiles_de_100_kb_en_menos_de_0_1_s(nombre):
    texto = HOSTILES[nombre]
    assert len(texto) >= N - 100
    for regex in [CORTE_ARTICULOS, *(p.regex for p in PATRONES)]:
        t0 = time.perf_counter()
        regex.findall(texto) if regex is CORTE_ARTICULOS else regex.match(texto)
        assert time.perf_counter() - t0 < 0.1, regex.pattern[:60]


@pytest.mark.parametrize("nombre", HOSTILES)
def test_parsear_bloques_con_un_bloque_hostil_de_100_kb_en_menos_de_0_1_s(nombre):
    t0 = time.perf_counter()
    parsear_bloques([{"texto": HOSTILES[nombre], "pagina": 1, "tipo": "parrafo"}], "N1", "normativa")
    assert time.perf_counter() - t0 < 0.1
