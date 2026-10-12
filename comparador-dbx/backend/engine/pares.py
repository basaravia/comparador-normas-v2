"""Pares únicos (docs/09 §2): las dos vías solo construyen candidatos; se unen y se deduplican
por (articulo_id, seccion_id) para que cada par se juzgue exactamente una vez."""
import logging
from dataclasses import replace

from backend.config import Settings, settings
from backend.engine.candidatos import candidatos
from backend.models import Par
from backend.retrieval.index import Indice
from backend.retrieval.reranker import Reranker, RerankerError

log = logging.getLogger(__name__)


def construir_pares(norma: Indice, manual: Indice, articulos_sel: set[str], secciones_sel: set[str],
                    s: Settings = settings, reranker: Reranker | None = None, textos: dict[str, str] | None = None) -> tuple[list[Par], dict]:
    """Devuelve `(pares, estadisticas)`.

    Vía 1: cada artículo seleccionado consulta el índice del manual (filtrado a las secciones
    seleccionadas). Vía 2: cada sección seleccionada consulta el índice de la norma (filtrado a los
    artículos seleccionados). `origen` = {"v1"}, {"v2"} o ambas ({"v1","v2"}).

    Con `s.RERANK_ENABLED`, cada vía toma el top-`RERANK_TOP_N` denso y el reranker (consulta = artículo, documento = sección,
    texto literal completo de `textos`) se queda con los `MAX_CANDIDATES` mejores: `rank_*` pasa a ser el del reranker y
    `score_*` sigue siendo el coseno. Cada par se puntúa una sola vez aunque salga en las dos vías.
    """
    manual_sel, norma_sel = manual.filtrar(secciones_sel), norma.filtrar(articulos_sel)
    pares: dict[tuple[str, str], Par] = {}
    ingenuo = 0
    s_denso = replace(s, MAX_CANDIDATES=s.RERANK_TOP_N) if s.RERANK_ENABLED else s
    via1 = {art: candidatos(norma.vectores_de(art), manual_sel, s_denso) for art in sorted(articulos_sel)}   # norma -> manual
    via2 = {sec: candidatos(manual.vectores_de(sec), norma_sel, s_denso) for sec in sorted(secciones_sel)}   # manual -> norma
    puntajes: dict[tuple[str, str], float] = {}
    if s.RERANK_ENABLED:
        puntajes = _puntuar(reranker, textos, via1, via2, s)
        via1 = {art: _mejores(lista, lambda sec: puntajes[(art, sec)], s.MAX_CANDIDATES) for art, lista in via1.items()}
        via2 = {sec: _mejores(lista, lambda art: puntajes[(art, sec)], s.MAX_CANDIDATES) for sec, lista in via2.items()}

    for art, lista in via1.items():                                    # vía 1: norma -> manual
        for rank, (sec, score) in enumerate(lista, start=1):
            ingenuo += 1
            p = pares.setdefault((art, sec), Par(id="", articulo_id=art, seccion_id=sec, origen=set()))
            p.origen.add("v1")
            p.score_v1, p.rank_v1, p.score_rerank = score, rank, puntajes.get((art, sec))

    for sec, lista in via2.items():                                    # vía 2: manual -> norma
        for rank, (art, score) in enumerate(lista, start=1):
            ingenuo += 1
            p = pares.setdefault((art, sec), Par(id="", articulo_id=art, seccion_id=sec, origen=set()))
            p.origen.add("v2")
            p.score_v2, p.rank_v2, p.score_rerank = score, rank, puntajes.get((art, sec))

    lista = list(pares.values())
    for n, p in enumerate(lista, start=1):
        p.id = f"P{n}"
    stats = {"n_pares_ingenuo": ingenuo, "n_pares_unicos": len(lista),
             "solo_v1": sum(p.origen == {"v1"} for p in lista), "solo_v2": sum(p.origen == {"v2"} for p in lista),
             "ambas": sum(p.origen == {"v1", "v2"} for p in lista)}
    if s.RERANK_ENABLED:
        stats["rerank_puntuados"] = len(puntajes)
    log.info("Pares: %s", stats)
    return lista, stats


def _mejores(lista: list[tuple[str, float]], puntaje, n: int) -> list[tuple[str, float]]:
    """Las `n` mejores por puntaje del reranker (desempate: orden denso, que `sorted` conserva)."""
    return sorted(lista, key=lambda x: -puntaje(x[0]))[:n]


def _puntuar(reranker: Reranker | None, textos: dict[str, str] | None, via1: dict, via2: dict, s: Settings) -> dict[tuple[str, str], float]:
    """Puntaje del reranker para cada par (artículo, sección) candidato en cualquiera de las dos vías, sin repetir pares."""
    if reranker is None or textos is None:
        raise RerankerError("RERANK_ENABLED=true requiere pasar `reranker` y `textos` (texto literal de cada artículo y sección).")
    if s.RERANK_TOP_N < s.MAX_CANDIDATES:
        raise RerankerError(f"RERANK_TOP_N ({s.RERANK_TOP_N}) debe ser >= MAX_CANDIDATES ({s.MAX_CANDIDATES}).")
    pedidos = sorted({(art, sec) for art, l in via1.items() for sec, _ in l} | {(art, sec) for sec, l in via2.items() for art, _ in l})
    log.info("Reranker %s: puntuando %d pares únicos (top-%d de cada vía)", reranker.nombre, len(pedidos), s.RERANK_TOP_N)
    return dict(zip(pedidos, reranker.puntuar([(textos[a], textos[b]) for a, b in pedidos])))
