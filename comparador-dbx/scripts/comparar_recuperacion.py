"""Compara la recuperación (embeddings solos o con reranker) contra pares (artículo, sección) etiquetados y PERSISTE la salida.

    STAGE=sandbox EMB_BATCH=8 [OLLAMA_EMB_MODEL=qwen3-embedding:0.6b] python scripts/comparar_recuperacion.py \\
        ARCHIVO.csv|xlsx NORMA.pdf MANUAL.pdf --col-articulo Artículo --col-seccion Sección --etiqueta arlaft \\
        [--reranker Qwen/Qwen3-Reranker-0.6B | BAAI/bge-reranker-v2-m3] [--top-n 20] [--reusar]

Embeddings y rerankers reales (nada simulado). Todas las configuraciones se miden igual: unión de las dos vías con los 10 mejores de cada una,
**sin umbral** (para no mezclar el efecto del umbral con el del modelo). Con --reranker, cada vía toma el top-N denso, lo puntúa el reranker
(consulta = artículo, documento = sección entera, sin recortar) y conserva los 10 mejores.

Persistencia (en output/<zona>/comparaciones/: test se puede versionar, val nunca; solo ids, rangos, puntajes y métricas, nunca texto):
  densos__<embeddings>__<etiqueta>.json   ranking denso completo de cada vía  -> con --reusar no se vuelve a indexar
  puntajes__<reranker>__<etiqueta>.json   puntaje del reranker por par        -> un par ya puntuado no se vuelve a puntuar
  resultados.jsonl                        una línea por configuración medida   -> `python scripts/tabla_comparaciones.py` arma la tabla
"""
import argparse
import json
import logging
import re
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np

from backend.config import carpeta_bloques, carpeta_salida, settings
from backend.core.progreso import configurar_logs, progreso
from backend.engine.candidatos import candidatos
from backend.extraction.lector import leer_documento
from backend.llm.client import ModelClient
from backend.retrieval.exclusion import clasificar_secciones
from backend.retrieval.index import construir_indice
from backend.retrieval.reranker import Reranker
from backend.retrieval.validacion import leer_comparacion, norm_id
from scripts.medir_recuperacion import fmt, wilson

log = logging.getLogger(__name__)
KS = (1, 3, 5, 10)
TOPE = 10


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", texto.lower()).strip("-")


def modelo_embeddings() -> str:
    return {"ollama": settings.OLLAMA_EMB_MODEL, "dmr": settings.DMR_EMB_MODEL, "foundry": settings.FOUNDRY_AI_EMBED_DEPLOYMENT}.get(settings.EMB_PROVIDER, settings.EMB_PROVIDER)


def metricas(nombre: str, emb: str, rerank: str, positivas: list[tuple[str, str]], r1: dict, r2: dict, extra: dict, a, tope: int = TOPE) -> dict:
    n = len(positivas)
    rk1 = [r1[x].index(s) + 1 if s in r1[x] else None for x, s in positivas]
    rk2 = [r2[s].index(x) + 1 if x in r2[s] else None for x, s in positivas]
    union = sum((u is not None and u <= tope) or (v is not None and v <= tope) for u, v in zip(rk1, rk2))
    lo, hi = wilson(union, n)
    fila = {"fecha": datetime.now().isoformat(timespec="seconds"), "etiqueta": a.etiqueta, "configuracion": nombre, "embeddings": emb, "reranker": rerank,
            "top_n": a.top_n if rerank else None, "tope": tope, "solo_art_etiquetados": a.solo_articulos_etiquetados, "n": n, "union10": union, "union10_pct": round(100 * union / n, 1), "ic95": [round(100 * lo), round(100 * hi)], **extra}
    print(f"\n[{nombre}] n={n}\n  unión top-{tope} de las dos vías: {fmt(union, n)}")
    for via, rk in (("v1", rk1), ("v2", rk2)):
        fila[f"{via}_k"] = {k: round(100 * sum(x is not None and x <= k for x in rk) / n) for k in KS}
        fila[f"{via}_mrr"] = round(sum(1 / x for x in rk if x) / n, 3)
        fila[f"{via}_mediana"] = float(np.median([x or 999 for x in rk]))
        print(f"  vía {via[-1]}: " + "  ".join(f"k={k}: {v} %" for k, v in fila[f"{via}_k"].items()) + f"  MRR={fila[f'{via}_mrr']:.3f}  mediana rango={fila[f'{via}_mediana']:.0f}")
    with open(Path(a.salida) / "resultados.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return fila


def main(a) -> None:
    configurar_logs()
    salida = Path(a.salida) if a.salida else carpeta_salida(a.zona) / "comparaciones"
    salida.mkdir(parents=True, exist_ok=True)
    emb = modelo_embeddings()
    nsecs = leer_documento(Path(a.norma), "N", "normativa", cache=carpeta_bloques(a.zona))
    msecs = leer_documento(Path(a.manual), "M", "manual_control", cache=carpeta_bloques(a.zona))
    clas = clasificar_secciones(msecs)
    inc = [s for s in msecs if s.es_hoja and clas.get(s.id, (True, ""))[0]]
    arts = {s.id for s in nsecs if s.nivel == "articulo" and s.identificador.startswith("Art")}
    por_id = {s.id: s for s in nsecs}
    print(f"Embeddings: {settings.EMB_PROVIDER} {emb} · {len(nsecs)} secciones de norma · {len(inc)} hojas de manual")

    densos = salida / f"densos__{slug(emb)}__{a.etiqueta}.json"
    if a.reusar and densos.exists():
        d = json.loads(densos.read_text(encoding="utf-8"))
        d1, d2 = d["d1"], d["d2"]
        print(f"Ranking denso reutilizado de {densos.name} (no se indexa)")
    else:
        cliente, nombres = ModelClient(), {"N": "Norma", "M": "Manual"}
        with progreso("Indexando norma", "lote") as cb:
            i_n = construir_indice(nsecs, cliente, nombres, cb)
        with progreso("Indexando manual", "lote") as cb:
            i_m = construir_indice(inc, cliente, nombres, cb)
        todo = replace(settings, SIM_THRESHOLD=-1.0, MAX_CANDIDATES=10**6, K_SUBCHUNKS=10**6)
        norma_sel = i_n.filtrar(arts)
        d1 = {x: [s for s, _ in candidatos(i_n.vectores_de(x), i_m, todo)] for x in sorted(arts)}
        d2 = {s.id: [x for x, _ in candidatos(i_m.vectores_de(s.id), norma_sel, todo)] for s in inc}
        densos.write_text(json.dumps({"embeddings": emb, "etiqueta": a.etiqueta, "d1": d1, "d2": d2}), encoding="utf-8")
        print(f"Ranking denso guardado en {densos.name}")

    apn: dict[int, str] = {}
    for x in sorted(arts):                                   # número de artículo -> id; si el número se repite (capítulos, disposiciones) se usa el primero
        apn.setdefault(int(re.search(r"\d+", por_id[x].identificador).group()), x)
    if len(apn) < len(arts):
        print(f"AVISO: {len(arts) - len(apn)} artículos comparten número con otro (numeración repetida): se usa el primero de cada número.")
    ids_sec: dict[str, list[str]] = {}
    for s in inc:
        ids_sec.setdefault(norm_id(s.identificador), []).append(s.id)
    filas, _ = leer_comparacion(Path(a.archivo), a.col_articulo, a.col_seccion)
    positivas = [(apn[n], ids_sec[i][0]) for n, secs in filas if n in apn for i in secs if len(ids_sec.get(i, [])) == 1]
    fuera = sorted({n for n, _ in filas if n not in apn})
    if fuera:
        print(f"AVISO: artículos de tu archivo que no encuentro en la norma: {fuera}")
    etiquetados = sum(len(secs) for n, secs in filas if n in apn)
    print(f"Pares etiquetados evaluables: {len(positivas)} de {etiquetados} (el resto: sección excluida, no encontrada o con identificador repetido)")
    arts_pos, secs_pos = {p[0] for p in positivas}, {p[1] for p in positivas}
    if a.solo_articulos_etiquetados:                         # como en una corrida real: el auditor selecciona solo esos artículos
        universo = {apn[n] for n, _ in filas if n in apn}
        d2 = {s: [x for x in v if x in universo] for s, v in d2.items()}
        print(f"La vía 2 compite solo con los {len(universo)} artículos de tu archivo (no con los {len(arts)} de la norma)")
    metricas("solo embeddings", emb, "", positivas, d1, d2, {}, a)
    if not a.reranker:
        return

    d1n, d2n = {x: d1[x][:a.top_n] for x in arts_pos}, {s: d2[s][:a.top_n] for s in secs_pos}
    metricas(f"techo del reranker (embeddings, unión top-{a.top_n})", emb, "", positivas, d1n, d2n, {}, a, tope=a.top_n)
    cache_f = salida / f"puntajes__{slug(a.reranker)}__{a.etiqueta}.json"
    cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    pedidos = sorted({(x, s) for x in arts_pos for s in d1n[x]} | {(x, s) for s in secs_pos for x in d2n[s]})
    faltan = [p for p in pedidos if f"{p[0]}|{p[1]}" not in cache]
    print(f"\nReranker {a.reranker}: {len(pedidos)} pares (top-{a.top_n} de cada vía), {len(pedidos) - len(faltan)} ya en la caché, {len(faltan)} por puntuar")
    seg = 0.0
    if faltan:
        rr = Reranker(replace(settings, RERANK_MODEL=a.reranker, RERANK_BATCH=a.lote))
        textos = {**{s.id: s.texto_literal for s in inc}, **{x: por_id[x].texto_literal for x in arts}}
        t0 = time.perf_counter()
        with progreso(f"Reranker {a.reranker.split('/')[-1]}", "par") as cb:
            for k in range(0, len(faltan), 50):                      # la caché se guarda por tramos: una interrupción no pierde lo hecho
                trozo = faltan[k:k + 50]
                for (x, s), v in zip(trozo, rr.puntuar([(textos[x], textos[s]) for x, s in trozo])):
                    cache[f"{x}|{s}"] = v
                cache_f.write_text(json.dumps(cache), encoding="utf-8")
                cb(min(k + 50, len(faltan)), len(faltan))
        seg = time.perf_counter() - t0
        print(f"Reranker: {seg:.0f} s ({seg / len(faltan):.2f} s/par)")
    r1 = {x: sorted(d1n[x], key=lambda s: -cache[f"{x}|{s}"]) for x in arts_pos}
    r2 = {s: sorted(d2n[s], key=lambda x: -cache[f"{x}|{s}"]) for s in secs_pos}
    metricas(f"embeddings + reranker (top-{a.top_n} → top-{TOPE})", emb, a.reranker, positivas, r1, r2,
             {"seg_reranker": round(seg), "pares_puntuados": len(faltan), "pares_en_cache": len(pedidos) - len(faltan)}, a)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("archivo"); p.add_argument("norma"); p.add_argument("manual")
    p.add_argument("--col-articulo", default="Artículo"); p.add_argument("--col-seccion", default="Sección")
    p.add_argument("--etiqueta", default="dataset", help="nombre del conjunto etiquetado; separa cachés y filas de la tabla")
    p.add_argument("--reranker", default="", help="Qwen/Qwen3-Reranker-0.6B | BAAI/bge-reranker-v2-m3 | ruta local")
    p.add_argument("--top-n", type=int, default=20); p.add_argument("--lote", type=int, default=2)
    p.add_argument("--reusar", action="store_true", help="reutiliza el ranking denso guardado (no indexa)")
    p.add_argument("--solo-articulos-etiquetados", action="store_true", help="la vía 2 compite solo con los artículos que aparecen en tu archivo")
    p.add_argument("--zona", default="", help="test | val (por defecto DOCS_ZONA): decide dónde se guardan la caché de bloques y los resultados")
    p.add_argument("--salida", default="", help="carpeta de resultados (por defecto output/<zona>/comparaciones)")
    main(p.parse_args())
