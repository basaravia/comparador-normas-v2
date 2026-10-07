"""Valida el golden set de L3 (tests/golden_pairs.csv). Unitaria: sin modelos."""
import csv
import re
from collections import Counter
from pathlib import Path

import pymupdf
import pytest

from backend.config import carpeta_normas

RAIZ = Path(__file__).resolve().parent
CSV = RAIZ / "golden_pairs.csv"
SAMPLES = RAIZ.parent / "samples"
COLUMNAS = ["articulo_identificador", "documento_norma", "seccion_identificador",
            "documento_manual", "cobertura_esperada"]
# Artículos de la matriz de LEEME-MANUALES-MOCK.md dentro de 31-48 (el 33 no está en la matriz).
ARTICULOS = [31, 32, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48]
# Matriz: cobertura esperada por manual (A = MOCK-DEMO-03, B = MOCK-DEMO-01, C = MOCK-DEMO-02).
OMISION_B = {32, 43, 45, 48}
MANUALES = ["MOCK-DEMO-01", "MOCK-DEMO-02", "MOCK-DEMO-03"]
NORMA_PDF = carpeta_normas() / "Proyecto-de-Ley-Organica-Organica-para-Reprimir-y-Prevenir-el-Lavado-de-Activos-y-la-Financiacion-del-Terrorismo.pdf"


def _filas():
    with open(CSV, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _texto(pdf):
    return "\n".join(p.get_text() for p in pymupdf.open(pdf))


def test_columnas():
    with open(CSV, encoding="utf-8", newline="") as f:
        cabecera = next(csv.reader(f))
    assert cabecera[:len(COLUMNAS)] == COLUMNAS


def test_articulos_31_48_presentes():
    en_csv = {int(f["articulo_identificador"].split()[-1]) for f in _filas()}
    assert en_csv == set(ARTICULOS)


def test_sin_duplicados():
    claves = Counter((f["articulo_identificador"], f["documento_manual"]) for f in _filas())
    assert [k for k, n in claves.items() if n > 1] == []


def test_numero_de_pares_coincide_con_la_matriz():
    filas = _filas()
    assert len(filas) == len(ARTICULOS) * len(MANUALES)
    cuenta = Counter(f["cobertura_esperada"] for f in filas)
    assert cuenta["cumple"] == len(ARTICULOS)
    assert cuenta["parcial"] == len(ARTICULOS) - len(OMISION_B)
    assert cuenta["omision"] == len(ARTICULOS) + len(OMISION_B)
    for f in filas:
        art = int(f["articulo_identificador"].split()[-1])
        esperada = {"MOCK-DEMO-03": "cumple", "MOCK-DEMO-02": "omision",
                    "MOCK-DEMO-01": "omision" if art in OMISION_B else "parcial"}[f["documento_manual"]]
        assert f["cobertura_esperada"] == esperada, f


def test_seccion_solo_si_cumple_o_parcial():
    for f in _filas():
        if f["cobertura_esperada"] == "omision":
            assert f["seccion_identificador"] == "", f
        else:
            assert f["seccion_identificador"] != "", f


def test_articulos_existen_en_la_norma():
    if not NORMA_PDF.exists():
        pytest.skip("PDF de la norma no disponible")
    texto = _texto(NORMA_PDF)
    for f in _filas():
        assert f["documento_norma"] == NORMA_PDF.name
        assert re.search(rf"^{f['articulo_identificador']}\.-", texto, re.M), f["articulo_identificador"]


def test_secciones_existen_en_los_pdf_de_samples():
    textos = {m: _texto(SAMPLES / f"{m}.pdf") for m in MANUALES}
    for f in _filas():
        sec = f["seccion_identificador"]
        if not sec:
            continue
        patron = rf"^{re.escape(sec)}\.?\s+\S"
        assert re.search(patron, textos[f["documento_manual"]], re.M), f
