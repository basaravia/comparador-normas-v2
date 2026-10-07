"""Candidatos por sección (docs/09 §1, backend/engine/candidatos.py). FAISS real, vectores a mano."""
import numpy as np
import pytest

from backend.engine.candidatos import candidatos
from l3_ayudas import cfg, indice_a_mano

Q = np.array([[1, 0]], dtype=np.float32)       # consulta; con vectores (x, 0) el score es exactamente x
# Cada sección tiene score exacto contra Q (potencias de 2): S1 1.0, S2 .75, S3 .5, S4 .25, S5 .125
DESTINO = {"S1": [[1, 0]], "S2": [[0.75, 0]], "S3": [[0.5, 0]], "S4": [[0.25, 0]], "S5": [[0.125, 0]]}


def ids(res):
    return [s for s, _ in res]


def test_orden_por_score_descendente_y_tipos():
    res = candidatos(Q, indice_a_mano({"B": [[0.5, 0]], "A": [[1, 0]], "C": [[0.75, 0]]}),
                     cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.0, MIN_FLOOR=3, MAX_CANDIDATES=10))
    assert res == [("A", 1.0), ("C", 0.75), ("B", 0.5)]
    assert all(isinstance(s, str) and isinstance(x, float) for s, x in res)


def test_el_score_de_la_seccion_es_el_del_mejor_subchunk_no_el_promedio():
    destino = indice_a_mano({"S1": [[0.25, 0], [0.875, 0]], "S2": [[0.5, 0]]})
    res = candidatos(Q, destino, cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.0, MIN_FLOOR=1, MAX_CANDIDATES=10))
    assert res == [("S1", 0.875), ("S2", 0.5)]            # una entrada por sección, con su mejor sub-chunk


def test_con_varias_filas_de_consulta_gana_el_mejor_score_entre_filas():
    consulta = np.array([[1, 0], [0, 1]], dtype=np.float32)
    destino = indice_a_mano({"S1": [[0.5, 0]], "S2": [[0, 0.75]]})
    res = candidatos(consulta, destino, cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.0, MIN_FLOOR=1, MAX_CANDIDATES=10))
    assert res == [("S2", 0.75), ("S1", 0.5)]


def test_sim_threshold_filtra_e_incluye_el_valor_justo():
    res = candidatos(Q, indice_a_mano(DESTINO), cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.5, MIN_FLOOR=1, MAX_CANDIDATES=10))
    assert ids(res) == ["S1", "S2", "S3"]                # 0.5 pasa (>=); 0.25 y 0.125 no


def test_min_floor_devuelve_las_mejores_aunque_no_lleguen_al_umbral():
    res = candidatos(Q, indice_a_mano(DESTINO), cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.99, MIN_FLOOR=3, MAX_CANDIDATES=10))
    assert ids(res) == ["S1", "S2", "S3"]                # solo S1 pasa el umbral; el piso completa 3
    assert [x for _, x in res] == [1.0, 0.75, 0.5]


@pytest.mark.parametrize("umbral", [0.0, 0.3, 0.6, 0.8, 0.99, 5.0])
def test_siempre_pasan_al_menos_tres_si_el_indice_tiene_tres(umbral):
    res = candidatos(Q, indice_a_mano(DESTINO), cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=umbral, MIN_FLOOR=3, MAX_CANDIDATES=10))
    assert len(res) >= 3


def test_sobre_el_piso_manda_el_umbral():
    res = candidatos(Q, indice_a_mano(DESTINO), cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.2, MIN_FLOOR=3, MAX_CANDIDATES=10))
    assert ids(res) == ["S1", "S2", "S3", "S4"]


def test_max_candidates_acota():
    res = candidatos(Q, indice_a_mano(DESTINO), cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.0, MIN_FLOOR=1, MAX_CANDIDATES=2))
    assert ids(res) == ["S1", "S2"]


def test_k_mayor_que_el_indice_y_indice_menor_que_el_piso():
    res = candidatos(Q, indice_a_mano({"S1": [[1, 0]], "S2": [[0.5, 0]]}),
                     cfg(K_SUBCHUNKS=1000, SIM_THRESHOLD=0.99, MIN_FLOOR=3, MAX_CANDIDATES=10))
    assert ids(res) == ["S1", "S2"]                      # no hay 3: devuelve las que hay, sin error ni -1


def test_k_subchunks_limita_cuantos_subchunks_se_miran():
    res = candidatos(Q, indice_a_mano(DESTINO), cfg(K_SUBCHUNKS=2, SIM_THRESHOLD=0.0, MIN_FLOOR=1, MAX_CANDIDATES=10))
    assert ids(res) == ["S1", "S2"]


@pytest.mark.xfail(strict=True, reason="BAJA (diseño): K_SUBCHUNKS cuenta sub-chunks, no secciones; una sección larga con muchos "
                   "sub-chunks parecidos ocupa los K y deja menos de MIN_FLOOR secciones (candidatos.py)")
def test_min_floor_se_cumple_aunque_una_seccion_larga_ocupe_los_k_subchunks():
    destino = indice_a_mano({"LARGA": [[1, 0], [0.99, 0], [0.98, 0], [0.97, 0]], "S2": [[0.5, 0]], "S3": [[0.25, 0]]})
    res = candidatos(Q, destino, cfg(K_SUBCHUNKS=4, SIM_THRESHOLD=0.99, MIN_FLOOR=3, MAX_CANDIDATES=10))
    assert len(res) >= 3


@pytest.mark.xfail(strict=True, reason="BAJA conocida (efecto de Indice.buscar sin validar NaN): una consulta con NaN devuelve "
                   "[] en silencio (FAISS da indice -1) en vez de abortar con ERR-IDX-001")
def test_consulta_con_nan_no_deberia_dar_cero_candidatos_en_silencio():
    consulta = np.array([[np.nan, 0]], dtype=np.float32)
    res = candidatos(consulta, indice_a_mano(DESTINO), cfg(K_SUBCHUNKS=10, SIM_THRESHOLD=0.0, MIN_FLOOR=3, MAX_CANDIDATES=10))
    assert len(res) >= 3
