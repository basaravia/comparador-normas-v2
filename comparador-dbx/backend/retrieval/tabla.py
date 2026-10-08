"""Tabla de recuperación: una fila por sección, con lo que L3 compara y una comprobación contra el PDF.

La usan el notebook 02 y, después, la UI: devuelve un DataFrame listo para mostrar o exportar a Excel/CSV.
"""
import re
from pathlib import Path

import pandas as pd
import pymupdf

from backend.models import Seccion
from backend.retrieval.chunker import estimar_tokens, subchunkear

COLUMNAS = ["Documento", "Rol", "Nivel", "Identificador", "Título", "Ruta", "Págs", "Caracteres", "Sub-chunks",
            "Tokens máx.", "Inicio en el PDF", "Incierto", "Inicio del texto", "Fin del texto"]


def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip().lower()


def tabla_recuperacion(secciones: list[Seccion], pdf: Path, nombre: str) -> pd.DataFrame:
    """Una fila por sección: ruta y páginas, cómo se parte para embeddings y si su inicio coincide con el PDF.

    `Rol`: "se compara (hoja)" (se indexa) o "agrupa" (Título, Capítulo… solo dan la ruta).
    `Inicio en el PDF`: ✔ si el comienzo de la sección aparece en su página o en las vecinas, ✘ si hay que revisarla.
    `Incierto`: ⚠ si el seccionado la marcó `seccionado_incierto`.
    """
    with pymupdf.open(pdf) as doc:
        paginas = [_norm(p.get_text()) for p in doc]
    filas = []
    for x in secciones:
        subs = subchunkear(x, nombre) if x.es_hoja else []
        inicio = _norm(x.texto_literal)[:40]
        cerca = " ".join(paginas[max(x.pagina_inicio - 2, 0): x.pagina_inicio + 1])   # su página y las vecinas, seguidas
        texto = x.texto_literal.strip()
        filas.append({
            "Documento": nombre, "Rol": "se compara (hoja)" if x.es_hoja else "agrupa",
            "Nivel": x.nivel, "Identificador": x.identificador, "Título": x.titulo or "", "Ruta": " › ".join(x.ruta),
            "Págs": f"{x.pagina_inicio}-{x.pagina_fin}" if x.pagina_fin != x.pagina_inicio else str(x.pagina_inicio),
            "Caracteres": len(x.texto_literal), "Sub-chunks": len(subs),
            "Tokens máx.": max((estimar_tokens(sc.texto) for sc in subs), default=0),
            "Inicio en el PDF": "✔" if inicio and inicio in cerca else "✘",
            "Incierto": "⚠" if x.seccionado_incierto else "",
            "Inicio del texto": texto[:90].replace("\n", " ⏎ "), "Fin del texto": texto[-60:].replace("\n", " ⏎ ")})
    return pd.DataFrame(filas, columns=COLUMNAS)
