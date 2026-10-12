"""Pares únicos (docs/09 §2, backend/engine/pares.py). FAISS real, vectores a mano."""
import pytest

from backend.engine.pares import construir_pares
from backend.retrieval.index import IndiceError
from l3_ayudas import cfg, indice_a_mano

# Config del escenario asimétrico: solo el mejor candidato por consulta (MAX=1) y umbral 0.3.
C = cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.3, MIN_FLOOR=1, MAX_CANDIDATES=1)
NORMA = {"A1": [[1, 0]], "A2": [[0, 1]]}
MANUAL = {"S1": [[1, 0]], "S2": [[0.5, 0.4]]}
# vía 1 (norma -> manual): A1 -> S1 (1.0) ; A2 -> S2 (0.4)
# vía 2 (manual -> norma): S1 -> A1 (1.0) ; S2 -> A1 (0.5)   (A2 queda fuera por MAX=1)


@pytest.fixture
def escenario():
    return construir_pares(indice_a_mano(NORMA), indice_a_mano(MANUAL), {"A1", "A2"}, {"S1", "S2"}, C)


def por_clave(pares):
    return {(p.articulo_id, p.seccion_id): p for p in pares}


def test_union_de_las_dos_vias_sin_duplicados(escenario):
    pares, _ = escenario
    claves = [(p.articulo_id, p.seccion_id) for p in pares]
    assert sorted(claves) == [("A1", "S1"), ("A1", "S2"), ("A2", "S2")]
    assert len(set(claves)) == len(claves)


def test_origen_v1_v2_o_ambas(escenario):
    p = por_clave(escenario[0])
    assert p[("A1", "S1")].origen == {"v1", "v2"}
    assert p[("A2", "S2")].origen == {"v1"}
    assert p[("A1", "S2")].origen == {"v2"}


def test_scores_y_rangos_por_via(escenario):
    p = por_clave(escenario[0])
    ambas = p[("A1", "S1")]
    assert (ambas.score_v1, ambas.rank_v1, ambas.score_v2, ambas.rank_v2) == (1.0, 1, 1.0, 1)
    solo_v1, solo_v2 = p[("A2", "S2")], p[("A1", "S2")]
    assert (solo_v1.rank_v1, solo_v1.score_v2, solo_v1.rank_v2) == (1, None, None)
    assert solo_v1.score_v1 == pytest.approx(0.4)
    assert (solo_v2.score_v1, solo_v2.rank_v1, solo_v2.rank_v2) == (None, None, 1)
    assert solo_v2.score_v2 == pytest.approx(0.5)


def test_estadisticas_ingenuo_contra_unicos(escenario):
    pares, st = escenario
    assert st == {"n_pares_ingenuo": 4, "n_pares_unicos": 3, "solo_v1": 1, "solo_v2": 1, "ambas": 1}
    assert st["solo_v1"] + st["solo_v2"] + st["ambas"] == st["n_pares_unicos"] == len(pares)
    assert st["n_pares_unicos"] <= st["n_pares_ingenuo"]


def test_ids_secuenciales_y_orden_determinista(escenario):
    pares, _ = escenario
    assert [p.id for p in pares] == ["P1", "P2", "P3"]
    otra, _ = construir_pares(indice_a_mano(NORMA), indice_a_mano(MANUAL), {"A1", "A2"}, {"S1", "S2"}, C)
    assert [(p.id, p.articulo_id, p.seccion_id) for p in otra] == [(p.id, p.articulo_id, p.seccion_id) for p in pares]


def test_si_las_dos_vias_coinciden_todo_es_ambas():
    norma = indice_a_mano({"A1": [[1, 0, 0]], "A2": [[0, 1, 0]], "A3": [[0, 0, 1]]})
    manual = indice_a_mano({"S1": [[1, 0, 0]], "S2": [[0, 1, 0]], "S3": [[0, 0, 1]]})
    _, st = construir_pares(norma, manual, {"A1", "A2", "A3"}, {"S1", "S2", "S3"},
                            cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.5, MIN_FLOOR=1, MAX_CANDIDATES=10))
    assert st == {"n_pares_ingenuo": 6, "n_pares_unicos": 3, "solo_v1": 0, "solo_v2": 0, "ambas": 3}


def test_la_seleccion_acota_articulos_y_secciones():
    pares, _ = construir_pares(indice_a_mano(NORMA), indice_a_mano(MANUAL), {"A1"}, {"S1", "S2"}, C)
    assert {p.articulo_id for p in pares} == {"A1"}
    pares, _ = construir_pares(indice_a_mano(NORMA), indice_a_mano(MANUAL), {"A1", "A2"}, {"S2"}, C)
    assert {p.seccion_id for p in pares} == {"S2"}


def test_el_piso_garantiza_candidatos_aunque_ninguno_llegue_al_umbral():
    c = cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.99, MIN_FLOOR=1, MAX_CANDIDATES=10)
    pares, st = construir_pares(indice_a_mano(NORMA), indice_a_mano(MANUAL), {"A2"}, {"S1"}, c)
    assert [(p.articulo_id, p.seccion_id, p.origen == {"v1", "v2"}) for p in pares] == [("A2", "S1", True)]


@pytest.mark.parametrize("arts, secs", [(set(), {"S1"}), ({"A1"}, set()), (set(), set()), ({"X"}, {"S1"}), ({"A1"}, {"X"})])
def test_listas_vacias_o_desconocidas_abortan_con_err_idx_001_y_no_devuelven_pares_en_silencio(arts, secs):
    with pytest.raises(IndiceError) as e:
        construir_pares(indice_a_mano(NORMA), indice_a_mano(MANUAL), arts, secs, C)
    assert e.value.codigo == "ERR-IDX-001"


def test_articulo_seleccionado_ausente_del_indice_aborta():
    with pytest.raises(IndiceError, match="A9"):
        construir_pares(indice_a_mano(NORMA), indice_a_mano(MANUAL), {"A1", "A9"}, {"S1"}, C)


# --- Reranker opcional (RERANK_ENABLED). Lógica de selección con un puntuador de prueba: el modelo real se mide con scripts/comparar_recuperacion.py ---
class PuntuadorPrueba:
    """Puntúa por reglas fijas para comprobar el corte, el orden y que cada par se puntúe una vez; no simula recuperación."""
    nombre = "prueba"

    def __init__(self, puntajes):
        self.puntajes, self.llamadas = puntajes, []

    def puntuar(self, pares, progreso=None):
        self.llamadas.append(list(pares))
        return [self.puntajes[(q, d)] for q, d in pares]


TEXTOS = {"A1": "A1", "A2": "A2", "S1": "S1", "S2": "S2"}


def test_rerank_reordena_recorta_y_puntua_cada_par_una_vez():
    c = cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.0, MIN_FLOOR=1, MAX_CANDIDATES=1, RERANK_ENABLED=True, RERANK_TOP_N=2)
    # el coseno prefiere A1->S1, pero el reranker prefiere A1->S2: debe ganar el reranker
    pt = PuntuadorPrueba({("A1", "S1"): 0.1, ("A1", "S2"): 0.9, ("A2", "S1"): 0.2, ("A2", "S2"): 0.8})
    pares, stats = construir_pares(indice_a_mano(NORMA), indice_a_mano(MANUAL), {"A1", "A2"}, {"S1", "S2"}, c, pt, TEXTOS)
    p = por_clave(pares)
    assert p[("A1", "S2")].score_rerank == 0.9 and p[("A1", "S2")].rank_v1 == 1
    assert ("A1", "S1") not in p                                      # recortado a MAX_CANDIDATES=1 por el reranker
    assert len(pt.llamadas) == 1 and len(pt.llamadas[0]) == len(set(pt.llamadas[0])) == 4
    assert stats["rerank_puntuados"] == 4


def test_rerank_exige_reranker_y_textos_y_top_n_suficiente():
    from backend.retrieval.reranker import RerankerError
    c = cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.0, MIN_FLOOR=1, MAX_CANDIDATES=2, RERANK_ENABLED=True, RERANK_TOP_N=2)
    with pytest.raises(RerankerError, match="requiere"):
        construir_pares(indice_a_mano(NORMA), indice_a_mano(MANUAL), {"A1"}, {"S1"}, c)
    with pytest.raises(RerankerError, match="RERANK_TOP_N"):
        construir_pares(indice_a_mano(NORMA), indice_a_mano(MANUAL), {"A1"}, {"S1"}, cfg(RERANK_ENABLED=True, RERANK_TOP_N=1, MAX_CANDIDATES=2), PuntuadorPrueba({}), TEXTOS)


def test_sin_rerank_los_pares_no_cambian(escenario):
    assert all(p.score_rerank is None for p in escenario[0]) and "rerank_puntuados" not in escenario[1]
