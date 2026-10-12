"""Validación de la recuperación contra una comparación hecha a mano (archivo privado, solo en la máquina local).

El archivo no se versiona ni sale de la máquina. Aquí solo se leen identificadores (artículo, sección), nunca texto:
lo que se imprime o guarda son identificadores, rangos y scores.
"""
import re
from dataclasses import replace
from pathlib import Path

import pandas as pd

from backend.config import settings
from backend.engine.candidatos import candidatos
from backend.models import Seccion
from backend.retrieval.index import Indice


def norm_id(ident) -> str:
    """'4.1.' ≡ '4.1' ≡ ' 4.1 '; 'IV.' ≡ 'iv'. Compara identificadores sin depender de espacios, mayúsculas ni punto final."""
    return re.sub(r"\s+", "", str(ident)).lower().rstrip(".")


def leer_comparacion(ruta: Path, col_articulo: str, col_seccion: str, hoja: str | int = 0) -> tuple[list[tuple[int, list[str]]], int]:
    """Lee el CSV/XLSX: una fila por artículo; la celda de sección puede traer varias (separadas por ; , / o ' y ') o ir vacía (omisión).

    Devuelve ([(n.º de artículo, [identificadores de sección normalizados])], filas sin número de artículo).
    Todo se lee como texto: en Excel, da formato texto a la columna de secciones, o '4.10' se guarda como 4,1.
    """
    leer = pd.read_csv if ruta.suffix.lower() == ".csv" else lambda r, **kw: pd.read_excel(r, sheet_name=hoja, **kw)
    df = leer(ruta, dtype=str, keep_default_na=False)
    faltan = [c for c in (col_articulo, col_seccion) if c not in df.columns]
    if faltan:
        raise ValueError(f"No encuentro las columnas {faltan}. Columnas del archivo: {list(df.columns)}")
    filas, sin_numero = [], 0
    for art, sec in zip(df[col_articulo], df[col_seccion]):
        m = re.search(r"\d+", art)
        if not m:
            sin_numero += 1
            continue
        filas.append((int(m.group()), [norm_id(p) for p in re.split(r"[;,/\n]|\s+y\s+", sec) if p.strip()]))
    return filas, sin_numero


def evaluar_comparacion(filas: list[tuple[int, list[str]]], art_por_num: dict[int, str], manual: list[Seccion],
                        i_norma: Indice, i_manual: Indice, pares: list) -> dict:
    """Para cada par (artículo, sección) de la comparación manual: rango en cada vía (ranking completo, sin umbral ni tope),
    score y si quedó entre los candidatos reales (`pares`). Si el identificador de la sección es ambiguo (numeración repetida), cuenta el mejor.
    """
    todo = replace(settings, SIM_THRESHOLD=-1.0, MAX_CANDIDATES=10**6, K_SUBCHUNKS=10**6)
    ids_por_ident: dict[str, list[str]] = {}
    for x in manual:
        ids_por_ident.setdefault(norm_id(x.identificador), []).append(x.id)
    en_candidatos = {(p.articulo_id, p.seccion_id) for p in pares}
    norma_sel = i_norma.filtrar(set(art_por_num.values()))   # la vía 2 solo compite con los artículos seleccionados, como en construir_pares
    ranking_v1: dict[str, list] = {}
    filas_ev, omisiones, sin_articulo, sin_seccion = [], {}, [], []
    for n, secciones in filas:
        art = art_por_num.get(n)
        if art is None:
            sin_articulo.append(n)
            continue
        if not secciones:
            omisiones[n] = sum(1 for (a, _) in en_candidatos if a == art)
            continue
        if art not in ranking_v1:
            ranking_v1[art] = [sid for sid, _ in candidatos(i_norma.vectores_de(art), i_manual, todo)]
        for ident in secciones:
            ids = ids_por_ident.get(ident)
            if not ids:
                sin_seccion.append((n, ident))
                continue
            r1 = [ranking_v1[art].index(i) + 1 for i in ids]
            r2 = []
            for i in ids:
                rk = [a for a, _ in candidatos(i_manual.vectores_de(i), norma_sel, todo)]
                r2.append(rk.index(art) + 1 if art in rk else None)
            filas_ev.append({"articulo": n, "seccion": ident, "ambigua": len(ids) > 1, "rango_v1": min(r1),
                             "rango_v2": min((r for r in r2 if r), default=None),
                             "en_candidatos": any((art, i) in en_candidatos for i in ids)})
    return {"filas": filas_ev, "omisiones": omisiones, "sin_articulo": sin_articulo, "sin_seccion": sin_seccion}
