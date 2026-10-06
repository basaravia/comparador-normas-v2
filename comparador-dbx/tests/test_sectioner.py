import pytest
from pydantic import ValidationError
from backend.models import Seccion
from backend.sectioner import extraer_jerarquia, parsear_bloques, aplicar_cascada

def test_seccion_model_valida_atributos():
    s = Seccion(
        id="N1:L1/T2/ART-15",
        doc_id="N1",
        tipo_doc="normativa",
        nivel="articulo",
        identificador="Art. 15",
        titulo="De las pruebas",
        ruta=["Libro I", "Título II"],
        texto_literal="Texto de prueba.",
        pagina_inicio=1,
        pagina_fin=2,
        seccionado_incierto=False,
        estrategia="patron",
        es_hoja=True
    )
    assert s.id == "N1:L1/T2/ART-15"
    assert s.estrategia == "patron"

def test_extraer_jerarquia_libro_titulo_capitulo():
    texto = """LIBRO I\nTÍTULO II\nCAPÍTULO III\nART. 1.- Primer articulo."""
    bloques = [{"texto": x, "pagina": 1, "tipo": "párrafo"} for x in texto.split("\n")]
    secciones = parsear_bloques(bloques, doc_id="N1", tipo_doc="normativa")
    
    # Deberíamos tener el Art 1
    arts = [s for s in secciones if s.nivel == "articulo"]
    assert len(arts) == 1
    assert arts[0].ruta == ["LIBRO I", "TÍTULO II", "CAPÍTULO III"]
    assert arts[0].identificador == "ART. 1"
    assert arts[0].es_hoja is True

def test_literales_quedan_dentro_del_articulo():
    texto = "Art. 2.- Deberes.\na) Deber uno\nb) Deber dos"
    bloques = [{"texto": x, "pagina": 1, "tipo": "párrafo"} for x in texto.split("\n")]
    secciones = parsear_bloques(bloques, doc_id="N1", tipo_doc="normativa")
    
    arts = [s for s in secciones if s.nivel == "articulo"]
    assert len(arts) == 1
    assert "a) Deber uno" in arts[0].texto_literal
    assert "b) Deber dos" in arts[0].texto_literal

def test_manejo_articulos_duplicados():
    texto = "ARTÍCULO 1.- Uno.\nARTÍCULO 1.- Otro uno (error de fuente)."
    bloques = [{"texto": x, "pagina": 1, "tipo": "párrafo"} for x in texto.split("\n")]
    secciones = parsear_bloques(bloques, doc_id="N1", tipo_doc="normativa")
    
    arts = [s for s in secciones if s.nivel == "articulo"]
    assert len(arts) == 2
    assert arts[0].identificador == "ARTÍCULO 1"
    assert arts[1].identificador == "ARTÍCULO 1"
    assert arts[0].id.endswith("ARTICULO-1")
    assert arts[1].id.endswith("ARTICULO-1#2")
