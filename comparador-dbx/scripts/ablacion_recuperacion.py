"""Ablación de la recuperación sobre el golden: ¿mejoran una búsqueda léxica (BM25 + RRF) o un reranker cruzado al denso solo?

    STAGE=sandbox EMB_BATCH=8 python scripts/ablacion_recuperacion.py GOLDEN NORMA.pdf MANUAL.pdf [--reranker]

Mide recall@k (k=5, 10, 20, 30) y MRR por vía de lo que el variante deja en el top-k de cada artículo (vía 1) o sección (vía 2).
Experimento: no cambia el motor. Solo se adopta una mejora si el golden lo justifica (docs/13, L3b).
"""
import csv
import math
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

from backend.config import settings
from backend.core.progreso import configurar_logs, progreso
from backend.engine.candidatos import candidatos
from backend.extraction.lector import leer_documento
from backend.llm.client import ModelClient
from backend.retrieval.chunker import subchunkear
from backend.retrieval.exclusion import clasificar_secciones
from backend.retrieval.index import construir_indice

KS = (5, 10, 20, 30)
VACIAS = set("de la el los las y en a que por con para del al se un una o su sus es son lo como más sus no sin sobre entre ser este esta estos estas deben debe podrá podrán cuando".split())


def _tokens(texto: str) -> list[str]:
    s = unicodedata.normalize("NFD", texto.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return [w[:6] for w in re.findall(r"[a-z0-9]+", s) if w not in VACIAS and len(w) > 2]   # raíz tosca: primeras 6 letras


class BM25:
    def __init__(self, docs: dict[str, str], k1: float = 1.5, b: float = 0.75):
        self.tf = {i: Counter(_tokens(t)) for i, t in docs.items()}
        self.largo = {i: sum(c.values()) for i, c in self.tf.items()}
        self.prom = sum(self.largo.values()) / len(docs)
        df = Counter(w for c in self.tf.values() for w in c)
        n = len(docs)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
        self.k1, self.b = k1, b

    def ranking(self, consulta: str) -> list[str]:
        q = set(_tokens(consulta))
        punt = {}
        for i, c in self.tf.items():
            norm = self.k1 * (1 - self.b + self.b * self.largo[i] / self.prom)
            punt[i] = sum(self.idf.get(w, 0) * c[w] * (self.k1 + 1) / (c[w] + norm) for w in q if w in c)
        return sorted(punt, key=lambda i: -punt[i])


def rrf(*rankings: list[str], k: int = 60) -> list[str]:
    punt: dict[str, float] = {}
    for r in rankings:
        for pos, i in enumerate(r, 1):
            punt[i] = punt.get(i, 0) + 1 / (k + pos)
    return sorted(punt, key=lambda i: -punt[i])


def evaluar(nombre, positivas, rank_art, rank_sec):
    """`rank_art[a]`: secciones del manual ordenadas para el artículo a; `rank_sec[s]`: artículos ordenados para la sección s (puede faltar)."""
    print(f"\n== {nombre} ==")
    for via, r, clave in (("vía 1", rank_art, lambda f: (f["articulo_id"], f["seccion_id"])), ("vía 2", rank_sec, lambda f: (f["seccion_id"], f["articulo_id"]))):
        if not r:
            continue
        rangos = [(r[clave(f)[0]].index(clave(f)[1]) + 1) if clave(f)[1] in r[clave(f)[0]] else 9999 for f in positivas]
        n = len(rangos)
        ks = "  ".join(f"@{k}: {100 * sum(x <= k for x in rangos) / n:.0f} %" for k in KS)
        print(f"  {via}: {ks}  MRR={np.mean([1 / x for x in rangos]):.3f}")
    if rank_sec:
        unidos = [(f["articulo_id"], f["seccion_id"]) for f in positivas]
        for k in (10, 20):
            ok = sum(rank_art[a][:k].count(s) or rank_sec[s][:k].count(a) for a, s in unidos)
            print(f"  unión de las dos vías @{k}: {100 * ok / len(unidos):.0f} %")


def main(golden, norma, manual, reranker=False):
    configurar_logs()
    nsecs = leer_documento(Path(norma), "N", "normativa", cache=Path("output/bloques"))
    msecs = leer_documento(Path(manual), "M", "manual_control", cache=Path("output/bloques"))
    clas = clasificar_secciones(msecs)
    incl = [s for s in msecs if s.es_hoja and clas.get(s.id, (True, ""))[0]]
    arts = [s for s in nsecs if s.nivel == "articulo" and s.identificador.startswith("Art")]
    ids_m, ids_a = {s.id for s in incl}, {s.id for s in arts}
    cliente = ModelClient()
    with progreso("Indexando norma", "lote") as cb:
        i_norma = construir_indice(nsecs, cliente, {"N": "Norma", "M": "Manual"}, cb)
    with progreso("Indexando manual", "lote") as cb:
        i_manual = construir_indice(incl, cliente, {"N": "Norma", "M": "Manual"}, cb)
    todo = replace(settings, SIM_THRESHOLD=-1.0, MAX_CANDIDATES=10**6, K_SUBCHUNKS=10**6)
    ver = lambda l: [x for x, _ in l]
    d1 = {a: ver(candidatos(i_norma.vectores_de(a), i_manual, todo)) for a in ids_a}
    d2 = {s: ver(candidatos(i_manual.vectores_de(s), i_norma.filtrar(ids_a), todo)) for s in ids_m}

    texto = {s.id: s.texto_literal for s in nsecs + incl}
    bm_m, bm_a = BM25({s.id: s.texto_literal for s in incl}), BM25({s.id: s.texto_literal for s in arts})
    b1 = {a: bm_m.ranking(texto[a]) for a in ids_a}
    b2 = {s: bm_a.ranking(texto[s]) for s in ids_m}
    h1 = {a: rrf(d1[a], b1[a]) for a in ids_a}
    h2 = {s: rrf(d2[s], b2[s]) for s in ids_m}

    positivas = [f for f in csv.DictReader(open(golden, encoding="utf-8")) if f["seccion_id"] in ids_m]
    evaluar("denso (embeddings)", positivas, d1, d2)
    evaluar("léxico BM25 solo", positivas, b1, b2)
    evaluar("híbrido RRF (denso + BM25)", positivas, h1, h2)

    if reranker:
        from sentence_transformers import CrossEncoder   # no está en docs/12: solo para esta ablación
        ce = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)
        subs = {s.id: [c.texto for c in subchunkear(s, None)] for s in incl}
        pos_art = sorted({f["articulo_id"] for f in positivas})
        r1 = dict(d1)
        for a in progreso_iter(pos_art, "Reranker"):
            cand = d1[a][:30]
            pares = [(texto[a][:2000], t) for s in cand for t in subs[s]]
            sc = ce.predict(pares, batch_size=8)
            mejor, i = {}, 0
            for s in cand:
                mejor[s] = max(sc[i:i + len(subs[s])]); i += len(subs[s])
            r1[a] = sorted(cand, key=lambda s: -mejor[s]) + d1[a][30:]
        evaluar("reranker cruzado sobre el top-30 denso (solo vía 1)", positivas, r1, None)


def progreso_iter(it, nombre):
    from tqdm import tqdm
    return tqdm(list(it), desc=nombre)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(*args[:3], reranker="--reranker" in sys.argv)
