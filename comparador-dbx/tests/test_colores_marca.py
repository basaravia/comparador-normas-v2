"""D-40: los colores de las marcas A/L/R/X/P vienen de la configuración (docs/10, docs/14 #12), no del código. Deterministas."""
import dataclasses
import re

import pytest

from backend.config import settings
from backend.output import styles
from test_papel import H, entrada, guardar          # el mismo papel de trabajo que prueba test_papel.py
from test_config import correr_python

MARCAS = "ALRXP"


def test_cada_marca_tiene_un_color_hexadecimal_de_la_configuracion():
    for m in MARCAS:
        valor = getattr(settings, f"COLOR_MARCA_{m}")
        assert re.fullmatch(r"[0-9A-F]{6}", valor), (m, valor)
        assert styles.color_marca(m) == valor


def test_los_cinco_colores_son_distintos_para_poder_distinguir_las_marcas():
    assert len({styles.color_marca(m) for m in MARCAS}) == 5


def test_cambiar_un_color_cambia_el_relleno_del_papel(monkeypatch, tmp_path):
    nuevos = {f"COLOR_MARCA_{m}": c for m, c in zip(MARCAS, ("111111", "222222", "333333", "444444", "555555"))}
    monkeypatch.setattr(styles, "settings", dataclasses.replace(settings, **nuevos))
    ws = guardar(entrada(), tmp_path)[1]["Papel de trabajo"]
    for r, marca in zip(range(H + 1, H + 7), "ALRXPA"):
        celda = ws.cell(row=r, column=4)
        assert celda.value == marca and celda.fill.start_color.rgb.endswith(nuevos[f"COLOR_MARCA_{marca}"])


@pytest.mark.parametrize("valor", ["#C6EFCE", "C6EFC", "C6EFCEE", "ZZZZZZ", "", "rojo"])
def test_un_color_invalido_para_el_arranque_nombrando_la_variable(valor):
    r = correr_python("from backend.config import settings", STAGE="sandbox", COLOR_MARCA_R=valor)
    assert r.returncode != 0 and "COLOR_MARCA_R" in r.stderr and "6 dígitos hexadecimales" in r.stderr


def test_un_color_en_minusculas_se_normaliza_a_mayusculas():
    r = correr_python("from backend.config import settings; print(settings.COLOR_MARCA_A)", STAGE="sandbox", COLOR_MARCA_A="c6efce")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "C6EFCE"
