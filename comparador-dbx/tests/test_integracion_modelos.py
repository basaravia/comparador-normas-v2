"""Integración con los modelos REALES del stage (sandbox: Groq + Ollama bge-m3). Nada simulado.

Correr con: pytest -m integracion   (gasta tokens)
"""
from dataclasses import replace

import numpy as np
import pytest
from pydantic import BaseModel, Field

from backend.config import RAIZ, settings
from backend.core.errors import LLMOutputError, ProviderConfigError
from backend.ingest.classifier import ingerir
from backend.llm.client import ModelClient

pytestmark = pytest.mark.integracion


def test_ping_llm_y_embeddings(cliente):
    # L0: una llamada al LLM devuelve JSON válido (esquema Pong) y los embeddings responden.
    estado = cliente.ping()
    assert estado["llm"]["ok"], estado
    assert estado["embeddings"]["ok"], estado


def test_lote_de_embeddings_normalizado_l2(cliente):
    # L0: un lote de embeddings sale normalizado L2.
    m = cliente.embed(["El banco concilia la caja a diario.", "Reporte de operaciones inusuales.", "Hola"])
    assert m.dtype == np.float32 and m.shape[0] == 3 and m.shape[1] > 0
    assert np.allclose(np.linalg.norm(m, axis=1), 1.0, atol=1e-5)


class Imposible(BaseModel):
    """Ningún valor cumple: obliga a que el JSON real del modelo no valide dos veces."""
    valor: int = Field(ge=10, le=5)


def test_chat_json_reintenta_una_vez_y_lanza_llm_output_error(cliente, caplog):
    with pytest.raises(LLMOutputError):
        cliente.chat_json('Responde solo este JSON: {"valor": 7}', "dame el JSON", Imposible)
    avisos = [r.getMessage() for r in caplog.records if "JSON inválido del LLM" in r.getMessage()]
    assert len(avisos) == 2  # intento 1 y reintento con los errores adjuntos


@pytest.mark.skipif(settings.LLM_PROVIDER != "groq", reason="solo aplica al stage con Groq")
def test_clave_invalida_es_error_de_configuracion():
    mal = ModelClient(replace(settings, GROQ_API_KEY="clave-invalida-de-prueba-qa", LLM_RETRIES=0))
    with pytest.raises(ProviderConfigError):
        mal.chat_json('Responde {"ok": true}', "ping", Imposible)


def test_ingerir_mock_demo_03_es_manual_control(cliente):
    # L1: los MOCK salen como manual_control.
    fila = ingerir(RAIZ / "samples" / "MOCK-DEMO-03.pdf", cliente)
    assert fila["ok"], fila
    assert fila["archivo"] == "MOCK-DEMO-03.pdf"
    assert fila["tipo_llm"] == "manual_control"
    assert fila["tipo"] == "manual_control"  # preseleccionado: confianza ≥ TYPE_CONFIDENCE
    assert fila["paginas"] > 0 and len(fila["sha256"]) == 64
    assert fila["evidencia"]
