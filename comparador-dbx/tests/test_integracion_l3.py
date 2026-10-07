"""L3 · Recuperación con embeddings REALES (Ollama bge-m3) y FAISS real. Nada simulado.

Criterio de docs/13: recall@candidatos >= 90 % sobre tests/golden_pairs.csv (arts. 31-48 de la LA/FT
contra los 3 MOCK). Correr con (la Pi con Ollama: EMB_BATCH=64 agota el tiempo):

    STAGE=sandbox SIM_THRESHOLD=0.50 EMB_BATCH=8 LLM_TIMEOUT_S=900 taskset -c 3 pytest -m integracion tests/test_integracion_l3.py -s

Secciones de entrada (así se arman):
- Normativa: bloques de Docling real ya extraídos por dev-ia-motor (BLOQUES_DIR, por defecto
  /tmp/claude-1000/motor-l3/lafit.json = LA/FT págs. 19-24), pasados por `parsear_bloques` de ESTA rama
  (el seccionador de L1; la cascada de L2 aún no está aquí) tras partir los "Artículo N.-" pegados en un
  bloque. PROVISIONAL, igual que el notebook 03.
- Manuales: los 3 MOCK de samples/ con las secciones PROVISIONALES de notebooks/03_recuperacion.ipynb:
  una Seccion por encabezado romano (`V.`) o numeral (`5.3`), texto hasta el siguiente encabezado,
  se descarta el índice del PDF, seccionado_incierto=True.
Métricas propias (sustituyen a RAGAS hasta que exista `comparador_eval`; ver qa/eval-l3.md).
"""
import csv
import json
import os
import re
import time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest
from dotenv import dotenv_values

from backend.config import RAIZ, settings
from backend.engine.candidatos import candidatos
from backend.engine.pares import construir_pares
from backend.models import Seccion
from backend.retrieval.index import construir_indice, limpiar_cache
from backend.sectioner import parsear_bloques

pytestmark = pytest.mark.integracion

BLOQUES = Path(os.environ.get("BLOQUES_DIR", "/tmp/claude-1000/motor-l3"))
GOLDEN = RAIZ / "tests" / "golden_pairs.csv"
NOMBRES = {"N1": "Proyecto de Ley LA/FT", "M1": "MOCK-DEMO-01", "M2": "MOCK-DEMO-02", "M3": "MOCK-DEMO-03"}
DOC = {"MOCK-DEMO-01": "M1", "MOCK-DEMO-02": "M2", "MOCK-DEMO-03": "M3"}
UMBRAL_RECALL = 0.90


def dividir_bloques(bloques):
    """PROVISIONAL hasta L2: parte los 'Artículo N.-' pegados en un bloque (solo corta, no altera texto)."""
    return [{**b, "texto": t} for b in bloques for t in re.split(r"(?<=\S)\s+(?=Art[íi]culo\s+\d+\.-)", b["texto"])]


ENC = re.compile(r"^(?:(?P<rom>[IVX]+)\.|(?P<num>\d+(?:\.\d+)+))\s+(?P<tit>\S.*)$")


def secciones_provisionales(pdf, doc_id):
    """Copia del armado de notebooks/03_recuperacion.ipynb (celda 'Secciones provisionales de los MOCK')."""
    lineas = [(p.number + 1, l.strip()) for p in pymupdf.open(pdf) for l in p.get_text().splitlines() if l.strip()]
    heads = [i for i, (_, l) in enumerate(lineas) if ENC.match(l)]
    primero = lineas[heads[0]][1].split()[0]
    inicio = next(i for i in heads[1:] if lineas[i][1].split()[0] == primero)   # el índice repite los encabezados
    secs, padre, limites = [], None, [i for i in heads if i >= inicio] + [len(lineas)]
    for a, b in zip(limites, limites[1:]):
        m = ENC.match(lineas[a][1]); ident = m["rom"] or m["num"]
        if m["rom"]:
            padre = f'{ident}. {m["tit"]}'
        secs.append(Seccion(id=f"{doc_id}:{ident}", doc_id=doc_id, tipo_doc="manual_control", nivel="numeral" if m["num"] else "seccion",
                            identificador=ident, titulo=m["tit"], ruta=[padre] if m["num"] else [],
                            texto_literal="\n".join(l for _, l in lineas[a:b]), pagina_inicio=lineas[a][0], pagina_fin=lineas[b - 1][0],
                            seccionado_incierto=True, estrategia="patron", es_hoja=True))
    return secs


@pytest.fixture(scope="module")
def l3():
    """Indexa con embeddings reales una sola vez y calcula pares y rankings completos."""
    if not (BLOQUES / "lafit.json").exists():
        pytest.skip(f"No existen los bloques de Docling en {BLOQUES}/lafit.json (los extrae dev-ia-motor)")
    efectivo = float(dotenv_values(RAIZ / "config" / "stages" / "sandbox.env")["SIM_THRESHOLD"])
    assert os.environ.get("STAGE") == "sandbox", "correr con STAGE=sandbox"
    sim = settings.SIM_THRESHOLD    # (variable aparte: el mensaje no debe volcar `settings`, que lleva claves)
    assert efectivo == 0.50 and sim == 0.50, (
        f"SIM_THRESHOLD efectivo {sim}, el del stage es {efectivo}: config/.env lo pisa; correr con SIM_THRESHOLD=0.50")
    assert settings.EMB_BATCH == 8, "correr con EMB_BATCH=8 (con 64 la Pi agota el tiempo)"

    lafit = parsear_bloques(dividir_bloques(json.load(open(BLOQUES / "lafit.json"))), "N1", "normativa")
    manual = [x for n in (1, 2, 3) for x in secciones_provisionales(RAIZ / "samples" / f"MOCK-DEMO-0{n}.pdf", f"M{n}")]
    cuenta = {d: sum(x.doc_id == d for x in manual) for d in ("M1", "M2", "M3")}

    from backend.llm.client import ModelClient
    limpiar_cache()
    cliente = ModelClient()
    t0 = time.perf_counter()
    i_norma = construir_indice(lafit, cliente, NOMBRES)
    i_manual = construir_indice(manual, cliente, NOMBRES)
    t_indexar = time.perf_counter() - t0

    num = lambda x: int(re.search(r"\d+", x.identificador).group())
    articulos = {x.id for x in lafit if 31 <= num(x) <= 48}
    secciones = {x.id for x in manual}
    t0 = time.perf_counter()
    pares, stats = construir_pares(i_norma, i_manual, articulos, secciones)
    t_pares = time.perf_counter() - t0

    ID = {(x.identificador, x.doc_id): x.id for x in lafit + manual}
    filas = [r for r in csv.DictReader(open(GOLDEN, encoding="utf-8"))]
    golden = [(ID[(r["articulo_identificador"], "N1")], ID[(r["seccion_identificador"], DOC[r["documento_manual"]])], r)
              for r in filas if r["seccion_identificador"]]
    return dict(lafit=lafit, manual=manual, cuenta=cuenta, i_norma=i_norma, i_manual=i_manual, t_indexar=t_indexar,
                t_pares=t_pares, articulos=articulos, secciones=secciones, pares=pares, stats=stats,
                golden=golden, n_filas=len(filas))


def _claves(pares):
    return {(p.articulo_id, p.seccion_id) for p in pares}


def _rankings(d):
    """Posición (1 = mejor) de cada par golden en el ranking COMPLETO de cada vía, sin umbral ni tope."""
    todo = replace(settings, K_SUBCHUNKS=len(d["i_manual"]) + len(d["i_norma"]), SIM_THRESHOLD=-1.0, MAX_CANDIDATES=10**6)
    r1 = {a: candidatos(d["i_norma"].vectores_de(a), d["i_manual"].filtrar(d["secciones"]), todo) for a, _, _ in d["golden"]}
    r2 = {s: candidatos(d["i_manual"].vectores_de(s), d["i_norma"].filtrar(d["articulos"]), todo) for _, s, _ in d["golden"]}
    pos = lambda lista, x: next(i for i, (y, _) in enumerate(lista, 1) if y == x)
    return {(a, s): (pos(r1[a], s), pos(r2[s], a)) for a, s, _ in d["golden"]}


def test_secciones_de_entrada(l3):
    print(f"\n[entrada] LA/FT págs. 19-24: {len(l3['lafit'])} secciones · MOCK provisionales por documento: {l3['cuenta']}"
          f" · golden: {l3['n_filas']} filas, {len(l3['golden'])} con sección (recall) y {l3['n_filas'] - len(l3['golden'])} omisiones")
    assert len(l3["articulos"]) == 18 and len(l3["golden"]) == 30 and l3["n_filas"] == 51


def test_recall_de_candidatos_cumple_el_criterio_de_l3(l3):
    claves = _claves(l3["pares"])
    aciertos = [(a, s) in claves for a, s, _ in l3["golden"]]
    recall = sum(aciertos) / len(aciertos)
    fallos = [r for (a, s, r), ok in zip(l3["golden"], aciertos) if not ok]
    sin_pc = [ok for (_, _, r), ok in zip(l3["golden"], aciertos) if r["confianza_mapeo"] != "por_confirmar"]
    print(f"\n[recall@candidatos] {sum(aciertos)}/{len(aciertos)} = {recall:.1%} (umbral {UMBRAL_RECALL:.0%}) · "
          f"sin filas por_confirmar: {sum(sin_pc)}/{len(sin_pc)} = {sum(sin_pc) / len(sin_pc):.1%}")
    for r in fallos:
        print("  FALLO", r["articulo_identificador"], "->", r["documento_manual"], r["seccion_identificador"],
              f"({r['cobertura_esperada']}, {r['confianza_mapeo'] or 'confirmada'})")
    print(f"[tiempo] indexar (norma + manual, embeddings reales): {l3['t_indexar']:.0f}s · pares: {l3['t_pares']:.2f}s")
    assert recall >= UMBRAL_RECALL
    assert len(aciertos) == 30 and len(sin_pc) == 28
    assert all(r["confianza_mapeo"] == "por_confirmar" for r in fallos), "falla una fila confirmada del golden"
    assert all(sin_pc)                                  # 28/28 sin las dos filas por_confirmar


def test_pares_antes_y_despues_de_deduplicar(l3):
    st = l3["stats"]
    print(f"\n[pares] ingenuos {st['n_pares_ingenuo']} · únicos {st['n_pares_unicos']} · solo_v1 {st['solo_v1']} · solo_v2 {st['solo_v2']} · "
          f"ambas {st['ambas']} · ahorro de llamadas al juez {1 - st['n_pares_unicos'] / st['n_pares_ingenuo']:.0%}")
    assert st["n_pares_unicos"] < st["n_pares_ingenuo"]
    assert st["solo_v1"] + st["solo_v2"] + st["ambas"] == st["n_pares_unicos"] == len(l3["pares"])
    assert len(_claves(l3["pares"])) == len(l3["pares"])                      # cada par se juzga una vez
    assert max(p.rank_v1 or 0 for p in l3["pares"]) <= settings.MAX_CANDIDATES


def test_recall_y_precision_a_k(l3):
    """recall@k y precision@k propios (qa-eval-ia). k = posición en el ranking de cada vía (mejor de las dos)."""
    rk = _rankings(l3)
    n = len(rk)
    claves = _claves(l3["pares"])
    print("\n[recall@k] (el par golden entra si queda en el top-k de la vía 1 o de la vía 2)")
    for k in (1, 3, 5, 10, 20):
        print(f"  k={k:>2}  recall@k = {sum(min(p) <= k for p in rk.values())}/{n} = {sum(min(p) <= k for p in rk.values()) / n:.1%}")
    por_art = defaultdict(set)
    for a, s, _ in l3["golden"]:
        por_art[a].add(s)
    print("[precision@k] vía 1: de los k candidatos de cada artículo, cuántos son del golden (promedio por artículo con golden)")
    for k in (1, 3, 5, 10):
        prec = []
        for a, esperadas in por_art.items():
            top = [s for s, _ in candidatos(l3["i_norma"].vectores_de(a), l3["i_manual"].filtrar(l3["secciones"]),
                                            replace(settings, SIM_THRESHOLD=-1.0, MAX_CANDIDATES=k, MIN_FLOOR=k))][:k]
            prec.append(sum(s in esperadas for s in top) / k)
        print(f"  k={k:>2}  precision@k = {sum(prec) / len(prec):.1%}")
    acertados = sum(k_ in claves for k_ in rk)
    print(f"[precision@candidatos] pares golden en candidatos / pares únicos = {acertados}/{len(l3['pares'])} = {acertados / len(l3['pares']):.1%}"
          " (baja por diseño: prioriza recall)")
    assert sum(min(p) <= settings.MAX_CANDIDATES for p in rk.values()) / n >= UMBRAL_RECALL
