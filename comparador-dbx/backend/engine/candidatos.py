"""Candidatos por sección (docs/09 §1). Umbrales de `settings`, nada fijo en el código."""
import numpy as np

from backend.config import Settings, settings
from backend.retrieval.index import Indice


def candidatos(consulta: np.ndarray, destino: Indice, s: Settings = settings) -> list[tuple[str, float]]:
    """Secciones del índice destino más parecidas a una sección origen, de mayor a menor score.

    `consulta`: vectores de los sub-chunks de la sección origen. El score de una sección destino es
    el mejor de sus sub-chunks. Pasan las que llegan a `SIM_THRESHOLD` (máx. `MAX_CANDIDATES`);
    si son menos de `MIN_FLOOR`, el piso devuelve las mejores `MIN_FLOOR` aunque no lleguen al umbral.
    """
    D, I = destino.buscar(consulta, s.K_SUBCHUNKS)
    scores: dict[str, float] = {}
    for fila_d, fila_i in zip(D, I):
        for score, i in zip(fila_d, fila_i):
            if i < 0:
                continue
            sec = destino.mapa[i]
            scores[sec] = max(scores.get(sec, -1.0), float(score))
    orden = sorted(scores.items(), key=lambda x: -x[1])
    sobre = [x for x in orden if x[1] >= s.SIM_THRESHOLD][:s.MAX_CANDIDATES]
    return sobre if len(sobre) >= s.MIN_FLOOR else orden[:s.MIN_FLOOR]
