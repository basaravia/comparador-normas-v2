"""L5 · Borrador de conclusión (docs/10): parte determinista y UNA integración con el LLM real."""
import pytest
from pydantic import ValidationError

from backend.core.errors import LLMOutputError
from backend.output import conclusion
from backend.output.conclusion import (BorradorConclusion, cifras_no_entregadas, generar_borrador, resumen_conclusion,
                                       validar_borrador)
from backend.output.workpaper import FilaPapel
from datos_papel import entrada, seccion


def test_resumen_con_cifras_calculadas_en_python():
    r = resumen_conclusion(entrada())
    assert r["manual"] == "Manual Interno.pdf" and r["normativas"] == ["Norma Uno.pdf", "Norma Dos.pdf"]
    assert r["total_articulos"] == 6
    assert r["conteos_por_marca"] == {"A": 2, "L": 1, "R": 1, "X": 1, "P": 1}
    assert r["porcentaje_cumple_sobre_evaluables"] == 50.0          # 2 / (A+L+R = 4)
    assert r["articulos_R"] == [{"identificador": "Art. 3", "elementos_faltantes": ["plazo", "responsable"]}]
    assert r["articulos_L"] == [{"identificador": "Art. 2", "elementos_faltantes": ["periodicidad"]}]
    assert r["otros_articulos_R"] == 0 and r["otros_articulos_L"] == 0
    assert r["controles_sin_base_normativa"] == ["9.1", "9.2"] and r["total_controles_sin_base"] == 2


def test_resumen_sin_evaluables_da_cero_por_ciento():
    e = entrada()
    e.filas = [f for f in e.filas if f.marca in ("X", "P")]
    r = resumen_conclusion(e)
    assert r["porcentaje_cumple_sobre_evaluables"] == 0 and r["conteos_por_marca"]["A"] == 0


def test_resumen_acota_listas_y_textos():
    e = entrada()
    extra = [FilaPapel(articulo=seccion(f"N1-r{i}", "N1", f"Art. R{i}", pag=20 + i), marca="R",
                       elementos_faltantes=["z" * 500, "b", "c", "d"]) for i in range(12)]
    e.filas = [f for f in e.filas if f.marca != "R"] + extra
    e.controles_sin_base = [seccion(f"M1-k{i}", "M1", f"K{i}", tipo="manual_control") for i in range(13)]
    r = resumen_conclusion(e)
    assert len(r["articulos_R"]) == 10 and r["otros_articulos_R"] == 2
    assert r["articulos_R"][0]["elementos_faltantes"] == ["z" * 200, "b", "c"]
    assert len(r["controles_sin_base_normativa"]) == 10 and r["total_controles_sin_base"] == 13


def test_borrador_no_acepta_vacio_y_recorta():
    assert BorradorConclusion(borrador_conclusion="  hola \n").borrador_conclusion == "hola"
    for malo in ("", "   \n"):
        with pytest.raises(ValidationError):
            BorradorConclusion(borrador_conclusion=malo)


def test_cifras_propias_del_resumen_se_aceptan():
    r = resumen_conclusion(entrada())
    texto = "De 6 artículos, 2 cumplen (50,0 %), 1 es parcial (Art. 2), 1 no cumple (Art. 3) y 2 controles (9.1 y 9.2)."
    assert cifras_no_entregadas(texto, r) == []


@pytest.mark.parametrize("texto,extra", [("Hay 37 artículos.", [37.0]), ("Cumple el 83,3 %.", [83.3]),
                                          ("Son 7 y 12 casos", [7.0, 12.0])])
def test_cifras_inventadas_se_detectan(texto, extra):
    assert cifras_no_entregadas(texto, resumen_conclusion(entrada())) == extra


def test_limites_de_palabras_de_docs_10():
    assert (conclusion.MIN_PALABRAS, conclusion.MAX_PALABRAS) == (120, 220)


def test_resumen_porcentajes_salen_de_los_conteos():
    r = resumen_conclusion(entrada())                # A=2 L=1 R=1 X=1 P=1 sobre 6; evaluables 4
    assert r["articulos_evaluables_A_L_R"] == 4
    assert r["porcentaje_por_marca_sobre_total"] == {"A": 33.3, "L": 16.7, "R": 16.7, "X": 16.7, "P": 16.7}
    assert (r["porcentaje_cumple_sobre_evaluables"], r["porcentaje_parcial_sobre_evaluables"],
            r["porcentaje_no_cumple_sobre_evaluables"]) == (50.0, 25.0, 25.0)
    assert (r["porcentaje_cumple_sobre_evaluables"] + r["porcentaje_parcial_sobre_evaluables"]
            + r["porcentaje_no_cumple_sobre_evaluables"]) == 100.0
    assert abs(sum(r["porcentaje_por_marca_sobre_total"].values()) - 100) < 0.5    # redondeo a 1 decimal


def test_resumen_sin_articulos_da_ceros():
    e = entrada()
    e.filas = []
    r = resumen_conclusion(e)
    assert r["total_articulos"] == 0 and set(r["porcentaje_por_marca_sobre_total"].values()) == {0}
    assert r["porcentaje_no_cumple_sobre_evaluables"] == 0 and r["porcentaje_parcial_sobre_evaluables"] == 0


def _texto(n_palabras, extra=""):
    return " ".join(["palabra"] * (n_palabras - len(extra.split()))) + (" " + extra if extra else "")


@pytest.mark.parametrize("n", [119, 221, 0, 500])
def test_validar_borrador_fuera_de_limites(n):
    with pytest.raises(LLMOutputError, match="palabras"):
        validar_borrador(_texto(n), resumen_conclusion(entrada()))


@pytest.mark.parametrize("n", [120, 121, 219, 220])
def test_validar_borrador_en_limites(n):
    texto = _texto(n)
    assert len(texto.split()) == n
    validar_borrador(texto, resumen_conclusion(entrada()))            # no lanza


def test_validar_borrador_cifra_ajena():
    with pytest.raises(LLMOutputError, match="cifras") as e:
        validar_borrador(_texto(150, "El 37 por ciento"), resumen_conclusion(entrada()))
    assert "37" in str(e.value)


@pytest.mark.parametrize("cifra", ["16,7", "16.7", "16.7%", "16,7%", "(16.7)", "16.7."])
def test_validar_borrador_formatos_de_cifra_del_resumen(cifra):
    validar_borrador(_texto(150, f"cumple {cifra} ok"), resumen_conclusion(entrada()))


@pytest.mark.parametrize("cifra", ["16,8", "16.71", "83.3%", "1.234"])
def test_validar_borrador_formatos_de_cifra_ajena(cifra):
    with pytest.raises(LLMOutputError, match="cifras"):
        validar_borrador(_texto(150, f"cumple {cifra} ok"), resumen_conclusion(entrada()))


def test_validar_borrador_sin_cifras_es_valido():
    validar_borrador(_texto(130), resumen_conclusion(entrada()))


@pytest.mark.integracion
def test_generar_borrador_con_llm_real(cliente):
    """UNA llamada real al LLM del stage: 120-220 palabras y ninguna cifra fuera del resumen."""
    ent = entrada()
    try:
        texto = generar_borrador(ent, cliente)
    except LLMOutputError as e:                       # el modelo incumplió la regla: es un hallazgo, no un error de QA
        pytest.fail(f"El borrador real incumple la validación del código: {e}")
    assert 120 <= len(texto.split()) <= 220
    assert cifras_no_entregadas(texto, resumen_conclusion(ent)) == []
