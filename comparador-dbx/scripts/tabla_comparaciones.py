"""Tabla markdown con lo medido por `comparar_recuperacion.py` (output/comparaciones/resultados.jsonl). Se queda con la última medición de cada configuración.

    python scripts/tabla_comparaciones.py [--etiqueta arlaft] [--salida output/comparaciones]
"""
import argparse
import json
from pathlib import Path


def main(etiqueta: str, salida: str) -> None:
    f = Path(salida) / "resultados.jsonl"
    filas = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []
    ultimas = {}
    for r in filas:
        if etiqueta and r["etiqueta"] != etiqueta:
            continue
        ultimas[(r["etiqueta"], r["embeddings"], r["reranker"], r["configuracion"].split(" (")[0], r["top_n"], r.get("solo_art_etiquetados", False))] = r
    print("| conjunto | embeddings | reranker | configuración | n | unión top-K | IC95 | v1 MRR | v2 MRR | v1 k=1/3/5/10 | v2 k=1/3/5/10 | s rerank |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(ultimas.values(), key=lambda r: (r["etiqueta"], r["embeddings"], r["reranker"])):
        ks = lambda via: "/".join(str(r[f"{via}_k"][k]) for k in ("1", "3", "5", "10"))
        print(f"| {r['etiqueta']} | {r['embeddings']} | {r['reranker'] or '—'} | {r['configuracion']} | {r['n']} | {r['union10_pct']} % (K={r.get('tope', 10)}) | {r['ic95'][0]}–{r['ic95'][1]} | "
              f"{r['v1_mrr']:.3f} | {r['v2_mrr']:.3f} | {ks('v1')} | {ks('v2')} | {r.get('seg_reranker', '—')} |")


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--etiqueta", default=""); p.add_argument("--salida", default="output/comparaciones")
    a = p.parse_args(); main(a.etiqueta, a.salida)
