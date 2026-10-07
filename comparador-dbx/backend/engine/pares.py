"""Pares únicos (docs/09 §2): las dos vías solo construyen candidatos; se unen y se deduplican
por (articulo_id, seccion_id) para que cada par se juzgue exactamente una vez."""
import logging

from backend.config import Settings, settings
from backend.engine.candidatos import candidatos
from backend.models import Par
from backend.retrieval.index import Indice

log = logging.getLogger(__name__)


def construir_pares(norma: Indice, manual: Indice, articulos_sel: set[str], secciones_sel: set[str],
                    s: Settings = settings) -> tuple[list[Par], dict]:
    """Devuelve `(pares, estadisticas)`.

    Vía 1: cada artículo seleccionado consulta el índice del manual (filtrado a las secciones
    seleccionadas). Vía 2: cada sección seleccionada consulta el índice de la norma (filtrado a los
    artículos seleccionados). `origen` = {"v1"}, {"v2"} o ambas ({"v1","v2"}).
    """
    manual_sel, norma_sel = manual.filtrar(secciones_sel), norma.filtrar(articulos_sel)
    pares: dict[tuple[str, str], Par] = {}
    ingenuo = 0

    for art in sorted(articulos_sel):                                  # vía 1: norma -> manual
        for rank, (sec, score) in enumerate(candidatos(norma.vectores_de(art), manual_sel, s), start=1):
            ingenuo += 1
            p = pares.setdefault((art, sec), Par(id="", articulo_id=art, seccion_id=sec, origen=set()))
            p.origen.add("v1")
            p.score_v1, p.rank_v1 = score, rank

    for sec in sorted(secciones_sel):                                  # vía 2: manual -> norma
        for rank, (art, score) in enumerate(candidatos(manual.vectores_de(sec), norma_sel, s), start=1):
            ingenuo += 1
            p = pares.setdefault((art, sec), Par(id="", articulo_id=art, seccion_id=sec, origen=set()))
            p.origen.add("v2")
            p.score_v2, p.rank_v2 = score, rank

    lista = list(pares.values())
    for n, p in enumerate(lista, start=1):
        p.id = f"P{n}"
    stats = {"n_pares_ingenuo": ingenuo, "n_pares_unicos": len(lista),
             "solo_v1": sum(p.origen == {"v1"} for p in lista), "solo_v2": sum(p.origen == {"v2"} for p in lista),
             "ambas": sum(p.origen == {"v1", "v2"} for p in lista)}
    log.info("Pares: %s", stats)
    return lista, stats
