"""Golden por requisito (norma LA/FT contra el manual sintético ARLAFT): estructura y consistencia. Sin modelos."""
import csv
import re
from collections import Counter
from pathlib import Path

import pytest

DIR = Path(__file__).resolve().parent
REQ = DIR / "golden_requisitos_arlaft.csv"
PARES = DIR / "golden_arlaft_v2.csv"
COLUMNAS = ["articulo", "naturaleza", "req_id", "ancla_literal", "obligatorio", "estado_esperado", "secciones_respaldo", "cita_manual",
            "estado_A", "estado_B", "acuerdo", "nota", "confianza_mapeo"]
OBJETIVO = {str(n) for n in list(range(31, 64)) + [89, 90]}


def _leer(ruta):
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_columnas_y_articulos_objetivo():
    filas = _leer(REQ)
    assert list(filas[0].keys()) == COLUMNAS
    assert {f["articulo"] for f in filas} == OBJETIVO


def test_naturaleza_y_estados_validos():
    for f in _leer(REQ):
        assert f["naturaleza"] in ("obligacion", "informativo", "no_aplica_entidad") or "|" in f["naturaleza"]   # "a|b": discrepancia por confirmar
        if f["req_id"]:
            assert f["obligatorio"] in ("si", "no")
            assert f["estado_esperado"] in ("cubierto", "parcial", "no_cubierto", "")
            assert f["acuerdo"] in ("alta", "por_confirmar")


def test_lo_que_difiere_queda_por_confirmar_y_sin_estado():
    for f in _leer(REQ):
        if f["acuerdo"] == "por_confirmar":
            assert f["confianza_mapeo"] == "por_confirmar"
            assert f["estado_esperado"] == "" or f["req_id"] == ""
        if f["acuerdo"] == "alta" and f["req_id"]:
            assert f["estado_esperado"] == f["estado_A"] == f["estado_B"] and f["estado_esperado"]


def test_no_cubierto_no_tiene_respaldo_y_cubierto_si():
    for f in _leer(REQ):
        if f["acuerdo"] == "alta" and f["req_id"]:
            if f["estado_esperado"] == "no_cubierto":
                assert not f["secciones_respaldo"]
            else:
                assert f["secciones_respaldo"] and len(f["cita_manual"]) >= 15


def test_ids_de_requisito_unicos_por_articulo():
    ids = [(f["articulo"], f["req_id"]) for f in _leer(REQ) if f["req_id"]]
    assert len(ids) == len(set(ids))


def test_el_golden_tiene_los_tres_estados_y_acuerdo_suficiente():
    alta = [f for f in _leer(REQ) if f["acuerdo"] == "alta" and f["req_id"]]
    estados = Counter(f["estado_esperado"] for f in alta)
    assert all(estados[e] >= 10 for e in ("cubierto", "parcial", "no_cubierto")), estados
    todos = [f for f in _leer(REQ) if f["req_id"]]
    assert len(alta) / len(todos) >= 0.6      # acuerdo mínimo entre etiquetadores (medido: 69 de 100)


def test_pares_derivados_cuadran_con_los_requisitos():
    req = [f for f in _leer(REQ) if f["acuerdo"] == "alta" and f["req_id"] and f["obligatorio"] == "si"]
    esperados = {(f["articulo"], s) for f in req for s in f["secciones_respaldo"].split(";") if s}
    pares = {(re.search(r"\d+", f["articulo_identificador"]).group(), f["seccion_identificador"]) for f in _leer(PARES) if f["seccion_id"]}
    assert pares == esperados
    omisiones = {re.search(r"\d+", f["articulo_identificador"]).group() for f in _leer(PARES) if not f["seccion_id"]}
    assert all(f["relevancia"] in ("0", "1", "2") for f in _leer(PARES)) and omisiones.isdisjoint({a for a, _ in esperados})


def test_hay_requisitos_cubiertos_por_dos_secciones_complementarias():
    assert any(f["acuerdo"] == "alta" and f["estado_esperado"] == "cubierto" and len([s for s in f["secciones_respaldo"].split(";") if s]) >= 2
               for f in _leer(REQ))
