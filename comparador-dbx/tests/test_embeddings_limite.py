"""Embeddings con límite de consultas por segundo (hallado con Databricks Free, 25 nov 2026): el cliente espera con pausas crecientes y reintenta; cualquier otro error sube sin esperar.
Deterministas: solo se reemplaza el transporte del SDK; los embeddings reales se prueban en tests/test_integracion_modelos.py."""
from types import SimpleNamespace

import pytest

from backend.core.errors import LLMUnavailableError
from backend.llm import client
from backend.llm.client import ModelClient
from l3_ayudas import cfg


class RateLimitError(Exception):
    status_code = 429


class BadRequestError(Exception):
    status_code = 400


def cliente_que_falla(veces: int, error: Exception):
    llamadas = []

    def create(model, input):
        llamadas.append(list(input))
        if len(llamadas) <= veces:
            raise error
        return SimpleNamespace(data=[SimpleNamespace(embedding=[3.0, 4.0]) for _ in input])

    return SimpleNamespace(llamadas=llamadas, embeddings=SimpleNamespace(create=create))


@pytest.fixture
def dormidos(monkeypatch):
    esperas = []
    monkeypatch.setattr(client.time, "sleep", lambda s: esperas.append(s))
    return esperas


def mc(**cambios):
    return ModelClient(cfg(EMB_PROVIDER="databricks", EMB_BATCH=2, EMB_REINTENTOS_LIMITE=3, EMB_ESPERA_LIMITE_S=2, **cambios))


def test_un_429_se_reintenta_con_pausas_que_se_duplican_y_al_final_responde(dormidos):
    c = cliente_que_falla(3, RateLimitError("Error code: 429 - REQUEST_LIMIT_EXCEEDED QPS"))
    m = mc()._crear_embeddings(c, "modelo", ["a", "b"])
    assert len(m.data) == 2 and len(c.llamadas) == 4
    assert dormidos == [2, 4, 8]


def test_si_se_agotan_los_reintentos_el_error_sube(dormidos):
    c = cliente_que_falla(99, RateLimitError("Error code: 429 - QPS"))
    with pytest.raises(RateLimitError):
        mc()._crear_embeddings(c, "modelo", ["a"])
    assert len(c.llamadas) == 4 and dormidos == [2, 4, 8]


def test_otro_error_no_se_reintenta_ni_espera(dormidos):
    c = cliente_que_falla(99, BadRequestError("Error code: 400 - mal formado"))
    with pytest.raises(BadRequestError):
        mc()._crear_embeddings(c, "modelo", ["a"])
    assert len(c.llamadas) == 1 and dormidos == []


def test_un_error_con_429_solo_en_el_texto_no_cuenta_como_limite(dormidos):
    c = cliente_que_falla(99, BadRequestError("el texto tiene 4290 tokens"))
    with pytest.raises(BadRequestError):
        mc()._crear_embeddings(c, "modelo", ["a"])
    assert dormidos == []


def test_sin_error_no_espera_y_embed_multi_lo_usa_en_cada_lote(dormidos):
    c = cliente_que_falla(0, RateLimitError("x"))
    m = mc()
    m._emb = (c, "modelo")
    filas = m.embed_multi(["a", "b", "c"])
    assert len(filas) == 3 and len(c.llamadas) == 2 and dormidos == []             # lotes de 2 y de 1


def test_embed_multi_se_recupera_de_un_429_en_mitad_de_una_indexacion(dormidos):
    c = cliente_que_falla(2, RateLimitError("Error code: 429 - QPS"))
    m = mc()
    m._emb = (c, "modelo")
    assert len(m.embed_multi(["a", "b", "c"])) == 3
    assert dormidos == [2, 4]


def test_si_no_se_recupera_el_error_llega_clasificado_a_quien_llama(dormidos):
    c = cliente_que_falla(99, RateLimitError("Error code: 429 - QPS"))
    m = mc()
    m._emb = (c, "modelo")
    with pytest.raises(LLMUnavailableError):
        m.embed_multi(["a"])
