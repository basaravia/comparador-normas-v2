"""Paso 3a, parte determinista (docs/09 §3a, backend/engine/descomposicion.py): verificación, renumeración y controles. Sin LLM."""
from backend.engine.descomposicion import armar_descomposicion
from backend.models.schemas import DescomposicionLLM, RequisitoLLM, Seccion
from l3_ayudas import cfg

C = cfg(CITATION_FUZZY_MIN=0.90, CITATION_SHOW_MIN=0.75, MAX_REQUISITOS=3, MAX_TEXTO_SIN_REQUISITO=20)
TEXTO = ("Las entidades deberán:\na) designar un oficial de cumplimiento;\nb) reportar operaciones inusuales a la UIF en cuatro días.")


def art(texto=TEXTO):
    return Seccion(id="N:A5", doc_id="N", tipo_doc="normativa", nivel="articulo", identificador="Art. 5", ruta=["Ley"], texto_literal=texto,
                   pagina_inicio=1, pagina_fin=1, seccionado_incierto=False, estrategia="patron", es_hoja=True)


def llm(*fragmentos, nat="obligacion", oblig=True):
    return DescomposicionLLM(naturaleza_articulo=nat, requisitos=[RequisitoLLM(id=f"x{i}", fragmento=f, obligatorio=oblig) for i, f in enumerate(fragmentos)])


def test_renumera_por_orden_ignora_ids_del_modelo_y_da_posiciones_reales():
    d = armar_descomposicion(art(), llm("designar un oficial de cumplimiento", "reportar operaciones inusuales a la UIF en cuatro días", "Las entidades deberán"), C)
    assert [r.id for r in d.requisitos] == ["R1", "R2", "R3"]
    assert all(r.verificado and TEXTO[r.inicio:r.fin] == r.fragmento for r in d.requisitos)


def test_texto_completo_cubierto_y_literales_tocados_no_requiere_revision():
    d = armar_descomposicion(art(), llm("Las entidades deberán:\na) designar un oficial de cumplimiento;", "b) reportar operaciones inusuales a la UIF en cuatro días."), C)
    assert not d.requiere_revision and d.motivos == []


def test_fragmento_inventado_queda_sin_posicion_y_el_articulo_a_revision():
    d = armar_descomposicion(art(), llm("designar un oficial de cumplimiento", "abstenerse de reportar cualquier operación sospechosa"), C)
    malo = d.requisitos[1]
    assert not malo.verificado and malo.inicio is None
    assert d.requiere_revision and any("R2" in m for m in d.motivos)


def test_literal_sin_requisito_marca_revision():
    d = armar_descomposicion(art(), llm("designar un oficial de cumplimiento"), C)
    assert d.requiere_revision and any("b)" in m for m in d.motivos)


def test_obligacion_sin_requisitos_obligatorios_nunca_es_limpia():
    d = armar_descomposicion(art(), llm("designar un oficial de cumplimiento", oblig=False), C)
    assert d.requiere_revision and any("obligatorios" in m for m in d.motivos)


def test_tope_de_requisitos():
    f = ["Las entidades", "designar un oficial", "reportar operaciones", "inusuales a la UIF"]
    d = armar_descomposicion(art(), llm(*f), C)
    assert len(d.requisitos) == 3 and d.requiere_revision and any("más de 3" in m for m in d.motivos)


def test_informativo_sin_requisitos_y_sin_revision():
    d = armar_descomposicion(art("Definiciones generales."), llm(nat="informativo"), C)
    assert d.requisitos == [] and not d.requiere_revision
