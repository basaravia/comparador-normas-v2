"""Mide la recuperación (L3) contra un golden set con embeddings reales del stage (sin simular nada).

    STAGE=sandbox python scripts/medir_recuperacion.py tests/golden_arlaft.csv NORMA.pdf MANUAL.pdf [--todas]

Indexa TODA la norma (todos los artículos) y las hojas incluidas del manual, y reporta recall@candidatos
(unión de las dos vías), recall@k de la vía 1, MRR, estratos, ruido en omisiones y pares a juzgar.
Con `--todas` cuenta también los pares de relevancia 1 (por defecto: relevancia 2 y 1 juntas, y aparte solo la 2).
"""
import csv
import logging
import math
import sys
from pathlib import Path

import numpy as np

from backend.config import settings
from backend.core.progreso import configurar_logs, progreso
from backend.engine.candidatos import candidatos
from backend.engine.pares import construir_pares
from backend.extraction.lector import leer_documento
from backend.llm.client import ModelClient
from backend.retrieval.exclusion import clasificar_secciones
from backend.retrieval.index import construir_indice

KS = (1, 3, 5, 10, 20)


def wilson(aciertos: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confianza de Wilson (95 %) de una proporción."""
    if n == 0:
        return 0.0, 0.0
    p = aciertos / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    mitad = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centro - mitad, centro + mitad


def fmt(aciertos: int, n: int) -> str:
    lo, hi = wilson(aciertos, n)
    return f"{aciertos}/{n} = {100 * aciertos / max(n, 1):.1f} %  (IC95 {100 * lo:.0f}–{100 * hi:.0f} %)"


def main(golden: str, norma: str, manual: str) -> None:
    configurar_logs()
    nsecs = leer_documento(Path(norma), "N", "normativa", cache=Path("output/bloques"))
    msecs = leer_documento(Path(manual), "M", "manual_control", cache=Path("output/bloques"))
    clas = clasificar_secciones(msecs)
    incluidas = [s for s in msecs if s.es_hoja and clas.get(s.id, (True, ""))[0]]
    print(f"Manual: {sum(s.es_hoja for s in msecs)} hojas, {len(incluidas)} incluidas · Norma: {len(nsecs)} secciones")

    cliente = ModelClient()
    nombres = {"N": "Norma", "M": "Manual"}
    with progreso("Indexando norma", "lote") as cb:
        i_norma = construir_indice(nsecs, cliente, nombres, cb)
    with progreso("Indexando manual", "lote") as cb:
        i_manual = construir_indice(incluidas, cliente, nombres, cb)

    articulos = {s.id for s in nsecs if s.nivel == "articulo" and s.identificador.startswith("Art")}
    ids_manual = {s.id for s in incluidas}
    pares, stats = construir_pares(i_norma, i_manual, articulos, ids_manual)
    unidos = {(p.articulo_id, p.seccion_id): p for p in pares}
    print(f"Pares a juzgar: {len(pares)} (ingenuos {stats['n_pares_ingenuo']}) · SIM_THRESHOLD={settings.SIM_THRESHOLD} K={settings.K_SUBCHUNKS} MAX={settings.MAX_CANDIDATES}")

    todo = replace_todo()
    r1 = {a: candidatos(i_norma.vectores_de(a), i_manual, todo) for a in articulos}
    r2 = {s: candidatos(i_manual.vectores_de(s), i_norma.filtrar(articulos), todo) for s in ids_manual}
    pos = lambda lista, x: next((i for i, (y, _) in enumerate(lista, 1) if y == x), None)

    filas = list(csv.DictReader(open(golden, encoding="utf-8")))
    positivas = [f for f in filas if f["seccion_id"] and f["seccion_id"].replace("M:", "M:") in ids_manual]
    faltan = [f["id"] for f in filas if f["seccion_id"] and f["seccion_id"] not in ids_manual]
    if faltan:
        print("AVISO: filas del golden con sección que no está entre las incluidas (id cambió o fue excluida):", faltan)

    def informe(nombre, sel):
        n = len(sel)
        en_cand = sum((f["articulo_id"], f["seccion_id"]) in unidos for f in sel)
        print(f"\n[{nombre}] n={n}")
        print("  recall@candidatos (unión):", fmt(en_cand, n))
        for via, r, clave in (("vía 1", r1, lambda f: (f["articulo_id"], f["seccion_id"])), ("vía 2", r2, lambda f: (f["seccion_id"], f["articulo_id"]))):
            rangos = [pos(r[clave(f)[0]], clave(f)[1]) for f in sel]
            ok = [x is not None and x <= settings.MAX_CANDIDATES and (f["articulo_id"], f["seccion_id"]) in unidos for x, f in zip(rangos, sel)]
            ks = "  ".join(f"k={k}: {100 * sum(x is not None and x <= k for x in rangos) / max(n, 1):.0f} %" for k in KS)
            mrr = np.mean([1 / x if x else 0 for x in rangos]) if rangos else 0
            print(f"  {via}: {ks}  MRR={mrr:.3f}  peor rango={max((x or 9999) for x in rangos)}")

    informe("todas (relevancia 1 y 2)", positivas)
    informe("solo relevancia 2", [f for f in positivas if f["relevancia"] == "2"])
    for est in ("larga", "tabla", "parcial", "cumple"):
        sel = [f for f in positivas if est in f["estrato"].split("+")]
        if sel:
            informe(f"estrato {est}", sel)

    omit = [f["articulo_id"] for f in filas if not f["seccion_id"]]
    cand_omit = [sum(1 for (a, _) in unidos if a == o) for o in omit]
    print(f"\nOmisiones ({len(omit)} artículos): candidatos por artículo, media {np.mean(cand_omit):.1f} (piso {settings.MIN_FLOOR}, tope {settings.MAX_CANDIDATES})")
    fallos = [(f["id"], f["articulo_identificador"], f["seccion_identificador"], pos(r1[f["articulo_id"]], f["seccion_id"]), pos(r2[f["seccion_id"]], f["articulo_id"]))
              for f in positivas if (f["articulo_id"], f["seccion_id"]) not in unidos]
    print("\nFallos (id, artículo, sección, rango vía 1, rango vía 2):")
    for x in fallos:
        print("  ", x)


def replace_todo():
    from dataclasses import replace
    return replace(settings, SIM_THRESHOLD=-1.0, MAX_CANDIDATES=10**6, K_SUBCHUNKS=10**6)


if __name__ == "__main__":
    main(*[a for a in sys.argv[1:] if not a.startswith("--")][:3])
