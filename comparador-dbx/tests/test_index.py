"""Caché de embeddings, `Indice` FAISS y `construir_indice` (backend/retrieval/index.py). Sin modelo."""
import faiss
import numpy as np
import pytest

from backend.retrieval import index as idx
from backend.retrieval.index import Indice, IndiceError, construir_indice, embeber, limpiar_cache
from l3_ayudas import ClienteVectores, indice_a_mano, seccion


@pytest.fixture(autouse=True)
def cache_limpia(monkeypatch):
    monkeypatch.setenv("STAGE", "sandbox")
    limpiar_cache()
    yield
    limpiar_cache()


# --- embeber: caché ---------------------------------------------------------------------------------

def test_embeber_vacio():
    assert embeber([], ClienteVectores()).shape == (0, 0)


def test_mismo_texto_y_modelo_no_vuelve_a_llamar():
    c = ClienteVectores()
    a = embeber(["x"], c)
    b = embeber(["x"], c)
    assert c.llamadas == 1
    assert np.array_equal(a, b) and a.dtype == np.float32


def test_lote_mixto_solo_envia_los_textos_nuevos_y_conserva_el_orden():
    c = ClienteVectores()
    v1 = embeber(["a", "b"], c)
    v2 = embeber(["c", "b", "a"], c)
    assert c.textos == [["a", "b"], ["c"]]
    assert np.array_equal(v2[1], v1[1]) and np.array_equal(v2[2], v1[0])


def test_texto_repetido_en_el_mismo_lote_se_envia_una_vez():
    c = ClienteVectores()
    v = embeber(["a", "a", "b"], c)
    assert c.textos == [["a", "b"]] and np.array_equal(v[0], v[1]) and len(v) == 3


def test_la_clave_incluye_el_modelo():
    a, b = ClienteVectores(modelo="modelo-a"), ClienteVectores(modelo="modelo-b")
    embeber(["x"], a)
    embeber(["x"], b)
    assert b.llamadas == 1                           # mismo texto, otro modelo: no comparte caché
    assert len(idx._CACHE) == 2


def test_la_clave_incluye_el_stage(monkeypatch):
    c = ClienteVectores()
    embeber(["x"], c)
    monkeypatch.setenv("STAGE", "mvp")
    embeber(["x"], c)
    assert c.llamadas == 2


def test_tope_max_cache_incluso_dentro_de_un_lote(monkeypatch):
    monkeypatch.setattr(idx, "MAX_CACHE", 3)
    c = ClienteVectores(dim=16)
    textos = [f"t{i}" for i in range(10)]
    v = embeber(textos, c)
    assert len(idx._CACHE) == 3                       # el lote de 10 no revienta el tope
    assert v.shape == (10, 16) and len({tuple(f) for f in v}) == 10   # y la respuesta sigue completa y distinta
    assert len(idx._CACHE) <= 3


def test_el_tope_expulsa_los_mas_antiguos(monkeypatch):
    monkeypatch.setattr(idx, "MAX_CACHE", 2)
    c = ClienteVectores(dim=8)
    embeber(["a"], c); embeber(["b"], c); embeber(["c"], c)
    llamadas = c.llamadas
    embeber(["c"], c)                                 # el más reciente sigue en caché
    assert c.llamadas == llamadas
    embeber(["a"], c)                                 # el más antiguo fue expulsado
    assert c.llamadas == llamadas + 1


# --- embeber: respuestas inválidas -> ERR-IDX-001 y nada entra a la caché -----------------------------

def _con(vectores):
    return ClienteVectores(respuesta=lambda textos: vectores(len(textos)))


@pytest.mark.parametrize("nombre, resp", [
    ("NaN", lambda n: np.full((n, 4), np.nan)),
    ("inf", lambda n: np.full((n, 4), np.inf)),
    ("-inf", lambda n: np.full((n, 4), -np.inf)),
    ("un NaN entre vectores buenos", lambda n: np.vstack([np.eye(4)[:1].repeat(n - 1, 0), [[np.nan, 0, 0, 0]]])),
    ("vector cero", lambda n: np.zeros((n, 4))),
    ("un vector cero entre buenos", lambda n: np.vstack([np.eye(4)[:1].repeat(n - 1, 0), np.zeros((1, 4))])),
    ("respuesta corta", lambda n: np.eye(4)[:1].repeat(n - 1, 0)),
    ("respuesta larga", lambda n: np.eye(4)[:1].repeat(n + 1, 0)),
    ("vector 1-D", lambda n: np.ones(4)),
])
def test_respuesta_invalida_es_err_idx_001_y_no_entra_a_la_cache(nombre, resp):
    with pytest.raises(IndiceError) as e:
        embeber(["a", "b", "c"], _con(resp))
    assert e.value.codigo == "ERR-IDX-001"
    assert not idx._CACHE and not idx._DIMS


def test_dimension_distinta_del_mismo_modelo_es_err_idx_001_y_no_ensucia_la_cache():
    embeber(["a"], ClienteVectores(dim=4))
    antes = dict(idx._CACHE)
    with pytest.raises(IndiceError, match="Dimensión 8"):
        embeber(["b"], ClienteVectores(dim=8))
    assert idx._CACHE == antes


def test_otro_modelo_puede_tener_otra_dimension():
    embeber(["a"], ClienteVectores(dim=4, modelo="m1"))
    assert embeber(["a"], ClienteVectores(dim=8, modelo="m2")).shape == (1, 8)


def test_indice_error_trae_mensaje_de_negocio():
    assert IndiceError("detalle").mensaje_negocio and IndiceError.codigo == "ERR-IDX-001"


# --- Indice ---------------------------------------------------------------------------------------------

def test_indice_es_faiss_real_flatip_con_mapa():
    ind = indice_a_mano({"S1": [[1, 0, 0], [0, 1, 0]], "S2": [[0, 0, 1]]})
    assert isinstance(ind.faiss, faiss.IndexFlatIP) and ind.faiss.ntotal == 3 == len(ind)
    assert ind.mapa == ["S1", "S1", "S2"] and ind.vectores.dtype == np.float32


def test_buscar_ordena_por_producto_interno():
    ind = indice_a_mano({"S1": [[1, 0]], "S2": [[0.5, 0]], "S3": [[0.25, 0]]})
    D, I = ind.buscar(np.array([[1, 0]], dtype=np.float32), 3)
    assert I[0].tolist() == [0, 1, 2] and D[0].tolist() == [1.0, 0.5, 0.25]


def test_buscar_con_varias_filas_devuelve_una_por_consulta():
    ind = indice_a_mano({"S1": [[1, 0]], "S2": [[0, 1]]})
    D, I = ind.buscar(np.array([[1, 0], [0, 1]], dtype=np.float32), 1)
    assert I.tolist() == [[0], [1]]


def test_k_mayor_que_el_indice_se_acota():
    ind = indice_a_mano({"S1": [[1, 0]], "S2": [[0, 1]]})
    D, I = ind.buscar(np.array([[1, 0]], dtype=np.float32), 50)
    assert D.shape == (1, 2) and (I >= 0).all()


@pytest.mark.parametrize("consulta", [np.ones((1, 3)), np.empty((0, 2)), np.ones(2), np.ones((1, 2, 2))])
def test_consulta_de_dimension_distinta_o_vacia_es_err_idx_001(consulta):
    ind = indice_a_mano({"S1": [[1, 0]]})
    with pytest.raises(IndiceError) as e:
        ind.buscar(consulta, 1)
    assert e.value.codigo == "ERR-IDX-001"


@pytest.mark.parametrize("malo", [np.nan, np.inf])
def test_consulta_con_nan_o_inf_deberia_ser_err_idx_001(malo):
    ind = indice_a_mano({"S1": [[1, 0]], "S2": [[0, 1]]})
    with pytest.raises(IndiceError):
        ind.buscar(np.array([[malo, 0]], dtype=np.float32), 1)


@pytest.mark.parametrize("vectores", [[[np.nan, 0]], [[np.inf, 0]], [[0, 0]]])
def test_nan_inf_o_cero_en_el_indice_es_err_idx_001(vectores):
    with pytest.raises(IndiceError):
        indice_a_mano({"S1": vectores})


def test_indice_con_distinto_numero_de_vectores_y_subchunks_es_err_idx_001():
    ind = indice_a_mano({"S1": [[1, 0]]})
    with pytest.raises(IndiceError):
        Indice(ind.subchunks * 2, ind.vectores)


def test_filtrar_deja_solo_las_secciones_pedidas_sin_tocar_el_original():
    ind = indice_a_mano({"S1": [[1, 0], [0.9, 0.1]], "S2": [[0, 1]], "S3": [[1, 1]]})
    sub = ind.filtrar({"S1", "S3"})
    assert sub.mapa == ["S1", "S1", "S3"] and len(sub) == 3 and len(ind) == 4
    assert sub.faiss.ntotal == 3 and ind.faiss.ntotal == 4
    D, I = sub.buscar(np.array([[0, 1]], dtype=np.float32), 5)
    assert {sub.mapa[i] for i in I[0]} == {"S1", "S3"}            # S2 ya no aparece


def test_filtrar_ignora_ids_desconocidos_pero_no_acepta_seleccion_vacia():
    ind = indice_a_mano({"S1": [[1, 0]]})
    assert ind.filtrar({"S1", "no-existe"}).mapa == ["S1"]
    for sel in (set(), {"no-existe"}):
        with pytest.raises(IndiceError):
            ind.filtrar(sel)


def test_vectores_de_una_seccion():
    ind = indice_a_mano({"S1": [[1, 0], [0, 1]], "S2": [[1, 1]]})
    assert ind.vectores_de("S1").tolist() == [[1, 0], [0, 1]]
    with pytest.raises(IndiceError):
        ind.vectores_de("S9")


# --- construir_indice ------------------------------------------------------------------------------------

def test_construir_indice_omite_no_hojas_y_vacias_y_embebe_con_prefijo():
    c = ClienteVectores()
    secs = [seccion("D:1", "Texto uno."), seccion("D:2", "Padre", es_hoja=False), seccion("D:3", "   "),
            seccion("D:4", "Texto cuatro.", ident="Artículo 4")]
    ind = construir_indice(secs, c, {"D": "Ley X"})
    assert ind.mapa == ["D:1", "D:4"]
    assert c.textos == [["Ley X > Título I > Artículo 1: Texto uno.", "Ley X > Título I > Artículo 4: Texto cuatro."]]


def test_construir_indice_sin_nombres_usa_el_doc_id_y_sin_texto_falla():
    c = ClienteVectores()
    construir_indice([seccion("D:1", "Texto uno.")], c)
    assert c.textos[0][0].startswith("D > ")
    with pytest.raises(ValueError):
        construir_indice([seccion("D:1", "  "), seccion("D:2", "x", es_hoja=False)], c)


def test_construir_indice_seccion_larga_aporta_varios_subchunks_de_una_seccion():
    larga = " ".join(f"palabra{i}" for i in range(1500))
    ind = construir_indice([seccion("D:1", larga)], ClienteVectores(dim=16))
    assert len(ind) > 1 and set(ind.mapa) == {"D:1"}
