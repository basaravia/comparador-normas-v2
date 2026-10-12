"""Lectura de la comparación manual: identificadores, secciones múltiples, omisiones y errores (sin modelos)."""
import pytest

from backend.retrieval.validacion import leer_comparacion, norm_id


def test_norm_id_ignora_espacios_mayusculas_y_punto_final():
    assert norm_id(" 4.1. ") == norm_id("4.1") == "4.1"
    assert norm_id("IV.") == norm_id("iv") == "iv"


def test_leer_csv_secciones_multiples_omision_y_filas_sin_articulo(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("Artículo,Sección\nArt. 31,4.1; 4.2\nArtículo 32,\nTotales,3.1\n32 bis,5.3 y V.\n", encoding="utf-8")
    filas, sin_numero = leer_comparacion(f, "Artículo", "Sección")
    assert filas == [(31, ["4.1", "4.2"]), (32, []), (32, ["5.3", "v"])]
    assert sin_numero == 1


def test_leer_xlsx_conserva_4_10_como_texto(tmp_path):
    import pandas as pd
    f = tmp_path / "c.xlsx"
    pd.DataFrame({"A": ["Art. 5"], "S": ["4.10"]}).to_excel(f, index=False)
    assert leer_comparacion(f, "A", "S")[0] == [(5, ["4.10"])]


def test_columna_inexistente_lista_las_que_hay(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\['x'\].*\['a', 'b'\]"):
        leer_comparacion(f, "a", "x")
