"""backend/retrieval/exclusion.py: clasificación determinista de secciones no comparables (docs/14 #24). Unitaria, sin modelos."""
import pytest

from backend.models import Seccion
from backend.retrieval.exclusion import CATALOGO, clasificar_secciones, motivo_propio


def sec(id_, ident, titulo, ruta=(), tipo="manual_control", texto=None, hoja=True):
    return Seccion(id=id_, doc_id="D", tipo_doc=tipo, nivel="numeral", identificador=ident, titulo=titulo, ruta=list(ruta),
                   texto_literal=texto or f"{ident} {titulo}\ncuerpo", pagina_inicio=1, pagina_fin=1, seccionado_incierto=False,
                   estrategia="patron", es_hoja=hoja)


@pytest.mark.parametrize("titulo, categoria", [
    ("REVISIÓN Y APROBACIÓN DEL DOCUMENTO", "revisión y aprobación"), ("Control de cambios", "revisión y aprobación"),
    ("Historial de versiones", "revisión y aprobación"), ("CORRESPONDENCIA CON LINEAMIENTOS DEL GRUPO", "correspondencia con lineamientos"),
    ("REGISTRO DE ELABORACIÓN/ACTUALIZACIÓN", "registro de elaboración"), ("Registro de actualización", "registro de elaboración"),
    ("Índice", "índice"), ("TABLA DE CONTENIDO", "índice"), ("Contenido", "índice"),
    ("INTRODUCCIÓN", "preámbulo"), ("Objetivos", "preámbulo"), ("Alcance del manual", "preámbulo"), ("Antecedentes", "preámbulo"),
    ("ASPECTOS GENERALES", "preámbulo"), ("Base normativa de aplicación general.", "preámbulo"),
    ("ANEXOS", "anexo"), ("Anexo Matriz de Riesgo", "anexo"), ("Apéndice A", "anexo"), ("METODOLOGÍAS ANEXAS", "anexo"), ("MANUAL DE USUARIO", "anexo"),
    ("Portada", "carátula"), ("Documentación de Procesos", "carátula")])
def test_el_manual_excluye_las_categorias_del_catalogo(titulo, categoria):
    assert motivo_propio(sec("s", "1", titulo)) == categoria


@pytest.mark.parametrize("titulo", [
    "Contenido mínimo de los informes del Oficial de Cumplimiento",                  # empieza por "contenido" pero es cuerpo
    "Conocimiento del cliente", "Procedimiento de Debida Diligencia Ampliada", "Funciones y responsabilidades del Directorio",
    "Señales de alerta", "Autoevaluación de riesgos y controles", "Reportes a organismos de control, documentos de soporte", "Definiciones",
    "Auditoría", "Sanciones"])
def test_el_cuerpo_del_manual_se_incluye(titulo):
    assert motivo_propio(sec("s", "5.1", titulo, ruta=["V"])) is None


def test_el_identificador_se_quita_solo_si_es_una_palabra_completa():
    # "I" de "I. INTRODUCCIÓN" no debe comerse la "I" de "INTRODUCCIÓN" cuando el título ya viene limpio
    assert motivo_propio(sec("s", "I", "INTRODUCCIÓN", texto="I. INTRODUCCIÓN\ncuerpo")) == "preámbulo"
    assert motivo_propio(sec("s", "I", None, texto="I. INTRODUCCIÓN\ncuerpo")) == "preámbulo"
    assert motivo_propio(sec("s", "I", None, texto="INTRODUCCIÓN\ncuerpo")) == "preámbulo"


def test_objetivos_y_base_normativa_dentro_de_un_procedimiento_son_cuerpo():
    assert motivo_propio(sec("a", "5.4.1", "Objetivos", ruta=["V", "5.4"])) is None
    assert motivo_propio(sec("b", "5.3.10.1", "Base normativa y otros documentos del procedimiento", ruta=["V", "5.3", "5.3.10"])) is None
    assert motivo_propio(sec("c", "2.1", "Objetivo principal", ruta=["II"])) == "preámbulo"          # hijo directo de un capítulo: preámbulo


def test_un_anexo_citado_dentro_de_un_procedimiento_no_es_un_anexo():
    assert motivo_propio(sec("a", "5.6.2", "Reporte según el Anexo 3", ruta=["V", "5.6"])) is None
    assert motivo_propio(sec("b", "12.1", "Anexo Matriz de riesgo", ruta=["XII"])) == "anexo"


def test_una_norma_solo_excluye_caratula_indice_y_considerandos():
    norma = lambda t: motivo_propio(sec("n", "Art. 1", t, tipo="normativa"))
    assert norma("Índice") == "índice" and norma("CONSIDERANDO") == "considerandos" and norma("Portada") == "carátula"
    for t in ("Anexo I", "Disposiciones transitorias", "Introducción", "Objetivos", "Revisión y aprobación"):
        assert norma(t) is None


def test_los_hijos_heredan_la_exclusion_de_su_ancestro_y_el_siguiente_capitulo_no():
    secs = [sec("1", "XII", "ANEXOS", hoja=False), sec("1a", "12.1", "Matriz de riesgo", ruta=["XII"]),
            sec("1b", "12.2", "Metodología", ruta=["XII"]), sec("1b1", "12.2.1", "Detalle", ruta=["XII", "12.2"]),
            sec("2", "XIII", "SANCIONES", hoja=False), sec("2a", "13.1", "Régimen", ruta=["XIII"])]
    c = clasificar_secciones(secs)
    assert c["1"] == (False, "anexo") and c["1a"] == (False, "anexo (hereda de XII)") and c["1b1"] == (False, "anexo (hereda de XII)")
    assert c["2"] == (True, "") and c["2a"] == (True, "")


def test_dos_capitulos_con_el_mismo_numero_se_clasifican_cada_uno_por_su_titulo():
    secs = [sec("a", "XII", "SEÑALES DE ALERTA", hoja=False), sec("a1", "12.1", "Negocios internacionales", ruta=["XII"]),
            sec("b", "XII#2", "ANEXOS", hoja=False), sec("b1", "12.1#2", "Matriz de riesgo", ruta=["XII"])]
    c = clasificar_secciones(secs)
    assert c["a1"][0] is True and c["b1"] == (False, "anexo (hereda de XII#2)")


def test_el_catalogo_son_datos_con_categoria_patron_y_tipo_de_documento():
    assert all(r.categoria and r.patron.pattern and r.aplica_a <= {"normativa", "manual_control"} for r in CATALOGO)


@pytest.mark.parametrize("titulo", [
    "Introducción de nuevos clientes: obligación de reportar", "Control de cambios de límites de efectivo",
    "Revisión y aprobación de excepciones al procedimiento de apertura de cuentas", "Alcance de la debida diligencia ampliada para clientes PEP",
    "Objetivos de control de las transferencias internacionales", "Registro de elaboración de reportes a la UAFE de operaciones sospechosas"])
def test_un_titulo_largo_que_empieza_como_una_categoria_es_cuerpo_del_manual(titulo):
    assert motivo_propio(sec("s", "1", titulo, ruta=[])) is None


def test_un_anexo_con_un_titulo_largo_empezando_por_anexo_si_se_excluye():
    assert motivo_propio(sec("s", "12.1", "Anexo Matriz de Riesgo para la Prevención de Lavado de Activos y Financiamiento del Terrorismo", ruta=["XII"])) == "anexo"


def test_un_capitulo_titulado_anexos_arrastra_a_sus_hijos_y_queda_el_motivo():
    secs = [sec("a", "V", "ANEXOS", hoja=False)] + [sec(f"a{i}", f"5.{i}", f"Control crítico {i}", ruta=["V"]) for i in range(1, 4)]
    c = clasificar_secciones(secs)
    assert all(c[f"a{i}"] == (False, "anexo (hereda de V)") for i in range(1, 4))      # visible en el motivo; el aviso lo da avisos_exclusion
