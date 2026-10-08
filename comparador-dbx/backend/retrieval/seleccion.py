"""Selección de las secciones que se comparan (RF-08, RF-09, docs/14 #24), sobre la tabla de recuperación.

Todo es determinista y trabaja sobre el DataFrame de `tabla_recuperacion`: la UI usará estas mismas funciones. Por defecto está incluido lo que
`exclusion.py` considera cuerpo del documento; el auditor puede cambiarlo. Marcar un nodo padre marca todos sus hijos (RF-09).
"""
import pandas as pd

HOJA_INCLUIDA, HOJA_EXCLUIDA = "se compara (hoja)", "excluida (hoja)"


def _descendientes(tabla: pd.DataFrame, fila: pd.Series) -> pd.Series:
    """Máscara de las secciones que cuelgan de `fila` (su ruta empieza por la ruta de `fila` más su identificador)."""
    camino = f"{fila['Ruta']} › {fila['Identificador']}" if fila["Ruta"] else fila["Identificador"]
    return (tabla["Documento"] == fila["Documento"]) & ((tabla["Ruta"] == camino) | tabla["Ruta"].str.startswith(camino + " › "))


def cambiar(tabla: pd.DataFrame, incluir: bool, ids: list[str] | tuple[str, ...] = (), texto: str | None = None) -> pd.DataFrame:
    """Copia de la tabla con `Incluir` cambiado en las secciones de `ids` y todas las que cuelgan de ellas (RF-09), y/o en las
    que contienen `texto` en el título o el identificador (el buscador del panel). `Motivo` queda como "… por el auditor"."""
    nueva = tabla.copy()
    marcadas = nueva["Id"].isin(ids)
    for _, fila in nueva[marcadas].iterrows():
        marcadas |= _descendientes(nueva, fila)
    if texto:
        marcadas |= nueva["Título"].str.contains(texto, case=False, regex=False) | nueva["Identificador"].str.contains(texto, case=False, regex=False)
    nueva.loc[marcadas, "Incluir"] = "✔" if incluir else "✘"
    nueva.loc[marcadas, "Motivo"] = "reincluida por el auditor" if incluir else "excluida por el auditor"
    hojas = nueva["Rol"] != "agrupa"
    nueva.loc[hojas, "Rol"] = nueva.loc[hojas, "Incluir"].map({"✔": HOJA_INCLUIDA, "✘": HOJA_EXCLUIDA})
    return nueva


def reincluir(tabla: pd.DataFrame, ids: list[str] | tuple[str, ...] = (), texto: str | None = None) -> pd.DataFrame:
    return cambiar(tabla, True, ids, texto)


def excluir(tabla: pd.DataFrame, ids: list[str] | tuple[str, ...] = (), texto: str | None = None) -> pd.DataFrame:
    return cambiar(tabla, False, ids, texto)


def ids_seleccionados(tabla: pd.DataFrame) -> set[str]:
    """Ids de las secciones hoja incluidas: lo que se indexa y se compara (entrada de `construir_indice` y `construir_pares`)."""
    return set(tabla.loc[tabla["Rol"] == HOJA_INCLUIDA, "Id"])


def solo_incluidas(secciones: list, tabla: pd.DataFrame) -> list:
    """Las secciones (objetos `Seccion`) que quedan tras la selección, en su orden original."""
    elegidas = ids_seleccionados(tabla)
    return [s for s in secciones if s.id in elegidas]


def excluidas(tabla: pd.DataFrame) -> pd.DataFrame:
    """Hojas no comparadas, con su motivo (para el anexo del papel de trabajo, RNF-06)."""
    return tabla.loc[tabla["Rol"] == HOJA_EXCLUIDA, ["Documento", "Identificador", "Título", "Ruta", "Págs", "Motivo", "Id"]].reset_index(drop=True)


def contadores(tabla: pd.DataFrame) -> pd.DataFrame:
    """Por documento: hojas, incluidas, excluidas y sub-chunks que se indexarían (el contador de cada panel, RF-09)."""
    hojas = tabla[tabla["Rol"] != "agrupa"]
    return hojas.groupby("Documento", sort=False).agg(
        hojas=("Id", "count"), incluidas=("Rol", lambda r: int((r == HOJA_INCLUIDA).sum())),
        excluidas=("Rol", lambda r: int((r == HOJA_EXCLUIDA).sum())),
        sub_chunks=("Sub-chunks", lambda c: int(c[hojas.loc[c.index, "Rol"] == HOJA_INCLUIDA].sum())))


def estimar_pares(tabla_norma: pd.DataFrame, tabla_manual: pd.DataFrame) -> int:
    """Pares posibles que se lanzarían (hojas incluidas de la norma × hojas incluidas del manual), antes de pulsar Comparar."""
    return len(ids_seleccionados(tabla_norma)) * len(ids_seleccionados(tabla_manual))


def resumen_exclusion(tabla: pd.DataFrame) -> str:
    """El aviso al auditor (docs/05): `Se excluyeron 17 secciones que no son cuerpo del documento (anexo: 4, preámbulo: 11…)`."""
    x = excluidas(tabla)
    if x.empty:
        return "No se excluyó ninguna sección."
    por_categoria = x["Motivo"].str.split(" (", regex=False).str[0].value_counts()
    detalle = ", ".join(f"{cat}: {n}" for cat, n in por_categoria.items())
    return f"Se excluyeron {len(x)} secciones que no son cuerpo del documento ({detalle})."


def avisos_exclusion(tabla: pd.DataFrame, max_pct: float | None = None, max_heredadas: int | None = None) -> list[str]:
    """Alertas para que el auditor confirme lo que el sistema excluyó (integridad: un título puede esconder un control, appsec 8 oct 2026).

    Avisa si se excluyó más de `EXCLUSION_MAX_PCT` % de las hojas de un documento, o si una sola exclusión arrastra más de
    `EXCLUSION_MAX_HEREDADAS` secciones por herencia. Los umbrales salen de la configuración."""
    from backend.config import settings
    max_pct = settings.EXCLUSION_MAX_PCT if max_pct is None else max_pct
    max_heredadas = settings.EXCLUSION_MAX_HEREDADAS if max_heredadas is None else max_heredadas
    avisos = []
    for doc, c in contadores(tabla).iterrows():
        pct = 100 * c["excluidas"] / c["hojas"] if c["hojas"] else 0
        if pct > max_pct:
            avisos.append(f"⚠ En «{doc}» se excluyó el {pct:.0f} % de las hojas ({c['excluidas']} de {c['hojas']}): confirma que sean carátulas, preámbulos o anexos.")
    x = excluidas(tabla)
    heredero = x["Motivo"].str.extract(r"\(hereda de (.+)\)$")[0]
    for (doc, origen), n in x.assign(origen=heredero).dropna(subset=["origen"]).groupby(["Documento", "origen"]).size().items():
        if n > max_heredadas:
            avisos.append(f"⚠ En «{doc}», la exclusión de «{origen}» arrastra {n} secciones: revisa que todo lo que cuelga de ahí no sea cuerpo del documento.")
    return avisos
