"""Ajustes por sesión (RF-19, docs/14 #33, backend/engine/ajustes.py): lista blanca, rangos y coherencia. Sin modelo."""
import pytest

from backend.engine import ajustes
from backend.engine.ajustes import AjusteInvalido, validar
from l3_ayudas import cfg

C = cfg(SIM_THRESHOLD=0.30, MAX_CANDIDATES=10, K_SUBCHUNKS=10, MIN_FLOOR=3, CITATION_SHOW_MIN=0.75, CITATION_FUZZY_MIN=0.90, LLM_CONCURRENCY=6, MAX_PARES=600)


def test_solo_lo_que_difiere_del_defecto_y_solo_la_lista_blanca():
    ok = validar({"SIM_THRESHOLD": 0.45, "MAX_CANDIDATES": 10, "GROQ_API_KEY": 1, "MAX_MB": 999, "FOUNDRY_AI_TOKEN": 5}, C)
    assert ok == {"SIM_THRESHOLD": 0.45}                  # el defecto no se guarda; las claves ajenas (secretos, límites de seguridad) se descartan


@pytest.mark.parametrize("valores", [{"SIM_THRESHOLD": 0.05}, {"SIM_THRESHOLD": 0.9}, {"MAX_CANDIDATES": 2}, {"MAX_CANDIDATES": 5.5},
                                     {"MAX_PARES": 601}, {"LLM_CONCURRENCY": 99}, {"SIM_THRESHOLD": float("nan")}, {"SIM_THRESHOLD": True}, {"SIM_THRESHOLD": "0.4"}])
def test_fuera_de_rango_o_de_tipo_se_rechaza_con_mensaje_de_negocio(valores):
    with pytest.raises(AjusteInvalido) as e:
        validar(valores, C)
    assert e.value.codigo == "ERR-AJU-001" and "«" in e.value.mensaje_negocio


def test_max_pares_solo_puede_bajar_respecto_al_stage():
    assert validar({"MAX_PARES": 100}, C) == {"MAX_PARES": 100}
    chico = cfg(**{**C.__dict__, "MAX_PARES": 200})
    with pytest.raises(AjusteInvalido):
        validar({"MAX_PARES": 300}, chico)


def test_exigencia_para_mostrar_no_puede_superar_la_de_validar():
    with pytest.raises(AjusteInvalido):
        validar({"CITATION_SHOW_MIN": 0.95, "CITATION_FUZZY_MIN": 0.85}, C)
    assert validar({"CITATION_FUZZY_MIN": 0.80, "CITATION_SHOW_MIN": 0.70}, C) == {"CITATION_FUZZY_MIN": 0.80, "CITATION_SHOW_MIN": 0.70}


def test_formato_invalido_y_demasiadas_claves():
    for malo in ([1, 2], {f"K{i}": 1 for i in range(60)}):
        with pytest.raises(AjusteInvalido):
            validar(malo, C)


def test_definicion_cubre_exactamente_los_parametros_previstos_y_con_rangos_coherentes():
    d = ajustes.definicion()
    assert set(d) == {"SIM_THRESHOLD", "MAX_CANDIDATES", "MAX_PARES", "CITATION_SHOW_MIN", "K_SUBCHUNKS", "MIN_FLOOR", "CITATION_FUZZY_MIN", "LLM_CONCURRENCY"}
    assert all(x["min"] < x["max"] and x["etiqueta"] and x["ayuda"] for x in d.values())
