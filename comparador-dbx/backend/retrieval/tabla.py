"""Tabla de recuperación: una fila por sección, con lo que L3 compara y una comprobación contra el PDF.

La usan el notebook 02 y, después, la UI: devuelve un DataFrame listo para mostrar o exportar a Excel/CSV.
"""
import re
from pathlib import Path

import pandas as pd
import pymupdf

from backend.models import Seccion
from backend.output.styles import PREFIJOS_FORMULA
from backend.retrieval.chunker import estimar_tokens, subchunkear
from backend.retrieval.exclusion import clasificar_secciones

COLUMNAS = ["Documento", "Rol", "Nivel", "Identificador", "Título", "Ruta", "Págs", "Caracteres", "Sub-chunks",
            "Tokens máx.", "Inicio en el PDF", "Incluir", "Motivo", "Incierto", "Inicio del texto", "Fin del texto", "Id"]


def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip().lower()


def titulo_visible(x: Seccion, maximo: int = 90) -> str:
    """Título para mostrar: el de la sección o, si el seccionador no lo aceptó (termina en punto, muy largo), la primera línea sin su numeración."""
    if x.titulo:
        return x.titulo
    linea = x.texto_literal.strip().split("\n", 1)[0]
    linea = re.sub(rf"^{re.escape(x.identificador)}(?![0-9A-Za-zÁÉÍÓÚÑáéíóúñ])", "", linea)        # solo si el identificador es una palabra completa
    return linea.lstrip(" .:-–—").strip()[:maximo]


def tabla_recuperacion(secciones: list[Seccion], pdf: Path, nombre: str) -> pd.DataFrame:
    """Una fila por sección: ruta y páginas, cómo se parte para embeddings y si su inicio coincide con el PDF.

    `Rol`: "se compara (hoja)" (se indexa), "excluida (hoja)" (no comparable: carátula, índice, anexo…; ver `exclusion.py`) o "agrupa"
    (Título, Capítulo… solo dan la ruta). `Incluir` (✔/✘) y `Motivo` dicen por qué; el auditor puede cambiarlos (`seleccion.cambiar`).
    `Sub-chunks` es lo que tendría la hoja si se incluye. `Id` es el identificador de la sección (clave para seleccionar).
    `Inicio en el PDF`: ✔ si el comienzo de la sección aparece en su página o en las vecinas, ✘ si hay que revisarla.
    `Incierto`: ⚠ si el seccionado la marcó `seccionado_incierto`.
    """
    with pymupdf.open(pdf) as doc:
        paginas = [_norm(p.get_text()) for p in doc]
    filas, clasificacion = [], clasificar_secciones(secciones)
    for x in secciones:
        incluir, motivo = clasificacion[x.id]
        subs = subchunkear(x, nombre) if x.es_hoja else []
        inicio = _norm(x.texto_literal)[:40]
        cerca = " ".join(paginas[max(x.pagina_inicio - 2, 0): x.pagina_inicio + 1])   # su página y las vecinas, seguidas
        texto = x.texto_literal.strip()
        filas.append({
            "Documento": nombre, "Rol": ("se compara (hoja)" if incluir else "excluida (hoja)") if x.es_hoja else "agrupa",
            "Nivel": x.nivel, "Identificador": x.identificador, "Título": titulo_visible(x), "Ruta": " › ".join(x.ruta),
            "Págs": f"{x.pagina_inicio}-{x.pagina_fin}" if x.pagina_fin != x.pagina_inicio else str(x.pagina_inicio),
            "Caracteres": len(x.texto_literal), "Sub-chunks": len(subs),
            "Tokens máx.": max((estimar_tokens(sc.texto) for sc in subs), default=0),
            "Inicio en el PDF": "✔" if inicio and inicio in cerca else "✘",
            "Incluir": "✔" if incluir else "✘", "Motivo": motivo,
            "Incierto": "⚠" if x.seccionado_incierto else "",
            "Inicio del texto": texto[:90].replace("\n", " ⏎ "), "Fin del texto": texto[-60:].replace("\n", " ⏎ "), "Id": x.id})
    return pd.DataFrame(filas, columns=COLUMNAS)


def guardar_csv(tabla: pd.DataFrame, ruta: Path) -> None:
    """CSV para abrir en Excel, sin inyección de fórmulas (CWE-1236): un texto del documento que empieza por = + - @ (o tab/CR) se guarda con un
    apóstrofo delante. Los textos salen de PDFs que no controlamos."""
    seguro = tabla.map(lambda v: "'" + v if isinstance(v, str) and v.startswith(PREFIJOS_FORMULA) else v)   # celda a celda: no depende del dtype
    seguro.to_csv(ruta, index=False, encoding="utf-8-sig")        # utf-8-sig: Excel lo abre con tildes
