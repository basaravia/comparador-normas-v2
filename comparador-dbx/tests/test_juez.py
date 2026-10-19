"""Verificación de citas del juez (docs/09 §4, backend/engine/juez.py). Solo la parte determinista; el juicio con el modelo real va en test_integracion_e2e."""
from backend.engine.juez import _verificar_cita
from l3_ayudas import cfg

C = cfg(CITATION_FUZZY_MIN=0.90, CITATION_SHOW_MIN=0.75, MAX_FRAGMENTO_DIFUSO=600)
TEXTO = "El área de tesorería concilia diariamente los saldos de caja y reporta las diferencias al comité en un plazo máximo de cuatro días."


def test_cita_exacta_se_devuelve_con_el_texto_real():
    cita, ok = _verificar_cita("concilia   diariamente los saldos de caja", TEXTO, C)
    assert ok and cita == "concilia diariamente los saldos de caja"


def test_cita_inventada_no_se_verifica_ni_pasa_como_texto_del_documento():
    cita, ok = _verificar_cita("el comité aprueba las excepciones sin límite de plazo alguno", TEXTO, C)
    assert not ok and (cita is None or cita in TEXTO)


def test_sin_cita_no_hay_nada_que_verificar():
    assert _verificar_cita(None, TEXTO, C) == (None, True)
    assert _verificar_cita("", TEXTO, C) == (None, True)
