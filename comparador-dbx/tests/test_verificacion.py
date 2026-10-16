"""Verificación de fragmentos con posiciones (docs/09 §4, backend/engine/verificacion.py). Python determinista."""
from backend.engine.verificacion import verificar_fragmento
from l3_ayudas import cfg

C = cfg(CITATION_FUZZY_MIN=0.90, CITATION_SHOW_MIN=0.75)
TEXTO = "Art. 5. Las entidades deberán reportar\n las operaciones inusuales a la UIF en un plazo máximo de cuatro días. Además, conservarán los registros."


def test_exacto_normaliza_espacios_y_saltos_y_la_posicion_es_del_texto_original():
    v = verificar_fragmento("reportar las operaciones inusuales a la UIF", TEXTO, s=C)
    assert v.estado == "exacto" and v.verificado
    assert TEXTO[v.inicio:v.fin] == v.texto_real == "reportar\n las operaciones inusuales a la UIF"


def test_parafrasis_leve_se_corrige_al_texto_real():
    v = verificar_fragmento("reportar las operaciones inusuales a la UIF en un plazo máximo de cuatro dias", TEXTO, s=C)   # sin tilde
    assert v.estado == "corregido" and v.verificado and v.ratio >= 0.90
    assert TEXTO[v.inicio:v.fin] == v.texto_real and "cuatro días" in v.texto_real


def test_fragmento_inventado_no_se_verifica_ni_se_pinta():
    v = verificar_fragmento("las entidades podrán abstenerse de reportar cualquier operación", TEXTO, s=C)
    assert not v.verificado and v.inicio is None and v.fin is None
    assert v.estado in ("dudoso", "no_encontrado")


def test_fragmento_vacio_nunca_cuenta_como_verificado():
    for f in ("", "   \n "):
        v = verificar_fragmento(f, TEXTO, s=C)
        assert not v.verificado and v.estado == "no_encontrado"


def test_repetido_toma_la_ocurrencia_posterior_al_requisito_anterior():
    t = "El comité aprobará el plan. Otro asunto. El comité aprobará el plan."
    a = verificar_fragmento("El comité aprobará el plan.", t, s=C)
    b = verificar_fragmento("El comité aprobará el plan.", t, desde=a.fin, s=C)
    assert a.inicio == 0 and b.inicio > a.fin and t[b.inicio:b.fin] == "El comité aprobará el plan."


def test_posicion_cumple_texto_inicio_fin_igual_texto_real():
    for f in ("conservarán los registros", "Art. 5. Las entidades"):
        v = verificar_fragmento(f, TEXTO, s=C)
        assert v.verificado and TEXTO[v.inicio:v.fin] == v.texto_real
