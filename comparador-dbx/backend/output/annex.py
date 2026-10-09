"""Hoja 2 'Anexo técnico' (docs/10): TODOS los pares evaluados y el bloque de la vía 2.

Defiende ante el regulador que no hubo selección sesgada de evidencia. Se arma con pandas;
cada celda de texto pasa por `escribir` (neutralización de fórmulas). Las columnas son las de
docs/10; "Artículo" y "Sección manual" llevan `id | identificador | documento` en una celda.
"""
import math

import pandas as pd

from backend.output.styles import ajustar_impresion, alto_fila, escribir, estilo_encabezado, estilo_etiqueta

COLUMNAS = ["ID par", "Artículo", "Sección manual", "Origen", "Similitud v1", "Similitud v2",
            "Similitud máxima", "Rango v1", "Rango v2", "Naturaleza", "Cobertura", "Confianza",
            "Elegido para el papel", "Comentario del juez", "Banderas"]
ANCHOS = [14, 34, 34, 8, 10, 10, 10, 8, 8, 16, 10, 10, 30, 60, 40]
COL_COMENTARIO = COLUMNAS.index("Comentario del juez")
SEP_CELDA = " | "
TITULO_EXCLUIDAS = "Secciones excluidas como no comparables (carátula, preámbulo, índice, anexos…)"
COLUMNAS_EXCLUIDAS = ["Documento", "Identificador", "Título", "Ruta", "Páginas", "Motivo"]
TITULO_VIA2 = "Vía 2 — Controles del manual sin base normativa identificada"
COLUMNAS_VIA2 = ["ID sección", "Identificador", "Documento", "Ruta", "Páginas", "Texto literal"]
_ORDEN_COBERTURA = {"total": 2, "parcial": 1, "nula": 0}


def _motivo(par, elegido, marca: str) -> str:
    """Por qué un par no es el de respaldo del artículo (texto fijo, no del modelo)."""
    if marca == "P":
        return "artículo informativo: sin respaldo"
    if marca == "X":
        return "no aplica a la entidad: sin respaldo"
    if marca == "R":
        return "cobertura nula: ningún par cubre la obligación"
    if par.veredicto is None:
        return "sin veredicto: requiere revisión"
    if elegido is None or elegido.veredicto is None:
        return "no se eligió respaldo"
    v, e = par.veredicto, elegido.veredicto
    if _ORDEN_COBERTURA[v.cobertura] < _ORDEN_COBERTURA[e.cobertura]:
        return "cobertura menor"
    if v.confianza < e.confianza:
        return "confianza menor"
    return "empate: se eligió otro par"


def _banderas(par, articulo, seccion) -> str:
    b = []
    v = par.veredicto
    if not par.cita_norma_verificada or (v and v.cita_manual and not par.cita_manual_verificada):
        b.append("cita_no_verificada")
    if par.requiere_revision:
        b.append("requiere_revision")
    if articulo.seccionado_incierto or (seccion and seccion.seccionado_incierto):
        b.append("seccionado_incierto")
    return ", ".join(b)


def _etiqueta(s, docs: dict[str, str], id_: str) -> str:
    """`id | identificador | documento` de una sección (solo el id si no se conoce)."""
    if s is None:
        return id_
    return SEP_CELDA.join([s.id, s.identificador, docs.get(s.doc_id, s.doc_id)])


def tabla_pares(entrada) -> pd.DataFrame:
    """Un renglón por par evaluado. Solo A y L tienen par elegido; en R, X y P ninguno lo es."""
    docs = {d.id: d.nombre for d in [entrada.manual, *entrada.normativas]}
    por_articulo = {f.articulo.id: f for f in entrada.filas}
    elegidos = {f.articulo.id: f.par for f in entrada.filas if f.par and f.marca in ("A", "L")}
    filas = []
    for p in entrada.pares:
        f = por_articulo.get(p.articulo_id)
        if f is None:
            continue
        a, s, v = f.articulo, entrada.secciones.get(p.seccion_id), p.veredicto
        elegido = elegidos.get(a.id)
        es_elegido = elegido is not None and elegido.id == p.id
        scores = [x for x in (p.score_v1, p.score_v2) if x is not None and math.isfinite(x)]
        filas.append({
            "ID par": p.id, "Artículo": _etiqueta(a, docs, a.id),
            "Sección manual": _etiqueta(s, docs, p.seccion_id),
            "Origen": "ambas" if p.origen == {"v1", "v2"} else "+".join(sorted(p.origen)),
            "Similitud v1": p.score_v1, "Similitud v2": p.score_v2,
            "Similitud máxima": max(scores) if scores else None,
            "Rango v1": p.rank_v1, "Rango v2": p.rank_v2,
            "Naturaleza": v.naturaleza_articulo if v else "", "Cobertura": v.cobertura if v else "",
            "Confianza": v.confianza if v else None,
            "Elegido para el papel": "Sí" if es_elegido else "No: " + _motivo(p, elegido, f.marca),
            "Comentario del juez": v.comentario if v else "",
            "Banderas": _banderas(p, a, s),
        })
    return pd.DataFrame(filas, columns=COLUMNAS)


def escribir_anexo(ws, entrada) -> None:
    tabla = tabla_pares(entrada)
    for col, nombre in enumerate(COLUMNAS, start=1):
        escribir(ws, 1, col, nombre, estilo=estilo_encabezado)
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = ANCHOS[col - 1]
    for i, fila in enumerate(tabla.itertuples(index=False), start=2):
        for col, valor in enumerate(fila, start=1):
            if pd.isna(valor):
                valor = None
            elif COLUMNAS[col - 1].startswith("Rango"):
                valor = int(valor)               # pandas los vuelve float si hay vacíos
            escribir(ws, i, col, valor)
        ws.row_dimensions[i].height = alto_fila([(fila[COL_COMENTARIO] or "", ANCHOS[COL_COMENTARIO])])
    ajustar_impresion(ws, 1)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{ws.cell(row=1, column=len(COLUMNAS)).column_letter}{max(1, len(tabla) + 1)}"

    # Bloque de la vía 2, al final de la misma hoja (decisión del usuario: sin tercera hoja)
    r = len(tabla) + 4
    escribir(ws, r, 1, TITULO_VIA2, estilo=estilo_etiqueta)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
    for col, nombre in enumerate(COLUMNAS_VIA2, start=1):
        escribir(ws, r + 1, col, nombre, estilo=estilo_encabezado)
    docs = {d.id: d.nombre for d in [entrada.manual, *entrada.normativas]}
    if not entrada.controles_sin_base:
        escribir(ws, r + 2, 1, "(ninguno)")
    ancho_texto = sum(ANCHOS[5:])
    ws.merge_cells(start_row=r + 1, start_column=6, end_row=r + 1, end_column=len(COLUMNAS))
    for i, s in enumerate(entrada.controles_sin_base, start=r + 2):
        pag = f"{s.pagina_inicio}" if s.pagina_inicio == s.pagina_fin else f"{s.pagina_inicio}-{s.pagina_fin}"
        for col, valor in enumerate([s.id, s.identificador, docs.get(s.doc_id, s.doc_id),
                                     " › ".join(s.ruta), pag, s.texto_literal], start=1):
            escribir(ws, i, col, valor, pagina=s.pagina_inicio)
        ws.merge_cells(start_row=i, start_column=6, end_row=i, end_column=len(COLUMNAS))
        ws.row_dimensions[i].height = alto_fila([(s.texto_literal, ancho_texto)])

    # Secciones excluidas (docs/14 #24): rastreables con su motivo, debajo del bloque de la vía 2
    r = r + 2 + max(1, len(entrada.controles_sin_base)) + 2
    escribir(ws, r, 1, TITULO_EXCLUIDAS, estilo=estilo_etiqueta)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
    for col, nombre in enumerate(COLUMNAS_EXCLUIDAS, start=1):
        escribir(ws, r + 1, col, nombre, estilo=estilo_encabezado)
    if not entrada.excluidas:
        escribir(ws, r + 2, 1, "(ninguna)")
    for i, x in enumerate(entrada.excluidas, start=r + 2):
        for col, valor in enumerate([x.documento, x.identificador, x.titulo, x.ruta, x.paginas, x.motivo], start=1):
            escribir(ws, i, col, valor)
