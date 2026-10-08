"""backend/llm/client.py — solo la parte determinista, sin llamar a ningún modelo.

- `crear_cliente` arma el cliente del SDK sin hacer peticiones: se prueba qué exige y qué devuelve.
- Los errores de conexión se prueban contra un puerto local cerrado: no hay modelo ni respuesta
  falsa, solo el error real del SDK y su traducción.
- El reintento de `chat_json` y `LLMOutputError` necesitan respuestas del LLM: se prueban con el
  modelo real en tests/test_integracion_modelos.py (aquí habría que simularlo, y eso no se hace).
"""
import logging
import socket

import numpy as np
from dataclasses import replace

import pytest
from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel

from backend.config import settings
from backend.core.errors import LLMUnavailableError, ProviderConfigError
from backend.llm.client import ModelClient, crear_cliente

BASE = replace(
    settings,
    GROQ_API_KEY="gsk_clave_de_prueba", GROQ_LLM_MODEL="modelo-groq", GROQ_BASE_URL="https://api.groq.test/v1",
    OLLAMA_BASE_URL="http://localhost:11434/v1", OLLAMA_LLM_MODEL="llm-ollama", OLLAMA_EMB_MODEL="emb-ollama",
    DMR_BASE_URL="http://localhost:12434/engines/v1", DMR_LLM_MODEL="llm-dmr", DMR_EMB_MODEL="emb-dmr",
    FOUNDRY_AI_ENDPOINT="https://mi-recurso.openai.azure.com/openai/v1/", FOUNDRY_AI_TOKEN="token-prueba",
    FOUNDRY_AI_API_VERSION="2024-10-21", FOUNDRY_AI_DEPLOYMENT="gpt-dep", FOUNDRY_AI_EMBED_DEPLOYMENT="emb-dep",
    LLM_RETRIES=2, LLM_TIMEOUT_S=30.0,
)


def puerto_cerrado() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- crear_cliente ----------------------------------------------------------------

def test_groq_devuelve_cliente_y_modelo_con_reintentos_y_timeout():
    cliente, modelo = crear_cliente("groq", BASE)
    assert type(cliente) is OpenAI
    assert modelo == "modelo-groq"
    assert str(cliente.base_url).startswith("https://api.groq.test/v1")
    assert cliente.max_retries == 2 and cliente.timeout == 30.0


@pytest.mark.parametrize("variable", ["GROQ_API_KEY", "GROQ_LLM_MODEL"])
@pytest.mark.parametrize("valor", ["", "REEMPLAZAR-con-tu-clave"])
def test_groq_aborta_y_dice_que_variable_falta(variable, valor):
    with pytest.raises(ProviderConfigError, match=variable):
        crear_cliente("groq", replace(BASE, **{variable: valor}))


@pytest.mark.parametrize("proveedor, embeddings, modelo", [
    ("ollama", False, "llm-ollama"),
    ("ollama", True, "emb-ollama"),
    ("dmr", False, "llm-dmr"),
    ("dmr", True, "emb-dmr"),
])
def test_locales_eligen_el_modelo_segun_el_uso(proveedor, embeddings, modelo):
    cliente, elegido = crear_cliente(proveedor, BASE, embeddings=embeddings)
    assert elegido == modelo
    assert cliente.api_key == proveedor  # sin clave: el SDK no acepta una vacía


@pytest.mark.parametrize("proveedor, embeddings, variable", [
    ("ollama", False, "OLLAMA_LLM_MODEL"),
    ("ollama", True, "OLLAMA_EMB_MODEL"),
    ("dmr", False, "DMR_LLM_MODEL"),
    ("dmr", True, "DMR_EMB_MODEL"),
])
def test_locales_abortan_si_falta_el_modelo(proveedor, embeddings, variable):
    with pytest.raises(ProviderConfigError, match=variable):
        crear_cliente(proveedor, replace(BASE, **{variable: ""}), embeddings=embeddings)


def test_foundry_usa_solo_el_host_y_el_deployment():
    cliente, deployment = crear_cliente("foundry", BASE)
    assert type(cliente) is AzureOpenAI
    assert deployment == "gpt-dep"
    assert str(cliente.base_url) == "https://mi-recurso.openai.azure.com/openai/"  # sin duplicar /openai/v1
    assert crear_cliente("foundry", BASE, embeddings=True)[1] == "emb-dep"


def test_foundry_lista_todas_las_variables_que_faltan():
    s = replace(BASE, FOUNDRY_AI_ENDPOINT="", FOUNDRY_AI_TOKEN="", FOUNDRY_AI_API_VERSION="",
                FOUNDRY_AI_EMBED_DEPLOYMENT="")
    with pytest.raises(ProviderConfigError) as e:
        crear_cliente("foundry", s, embeddings=True)
    for variable in ("FOUNDRY_AI_ENDPOINT", "FOUNDRY_AI_TOKEN", "FOUNDRY_AI_API_VERSION", "FOUNDRY_AI_DEPLOYMENT"):
        assert variable in str(e.value)


@pytest.mark.parametrize("endpoint", ["http://mi-recurso.openai.azure.com", "mi-recurso.openai.azure.com",
                                      "ftp://mi-recurso.openai.azure.com"])
def test_foundry_exige_https(endpoint):
    with pytest.raises(ProviderConfigError, match="https://"):
        crear_cliente("foundry", replace(BASE, FOUNDRY_AI_ENDPOINT=endpoint))


@pytest.mark.parametrize("proveedor", ["openai", "", "GROQ", "bedrock"])
def test_proveedor_desconocido(proveedor):
    with pytest.raises(ProviderConfigError, match="Proveedor desconocido"):
        crear_cliente(proveedor, BASE)


# --- ModelClient: creación perezosa -------------------------------------------------

def test_los_clientes_se_crean_en_el_primer_uso_y_se_reutilizan():
    mc = ModelClient(replace(BASE, LLM_PROVIDER="no-existe", EMB_PROVIDER="ollama"))  # no falla al construir
    assert mc.emb() is mc.emb()                                                       # embeddings sin LLM
    with pytest.raises(ProviderConfigError):
        mc.llm()


def test_llm_se_reutiliza():
    mc = ModelClient(replace(BASE, LLM_PROVIDER="groq"))
    assert mc.llm() is mc.llm()


# --- Errores reales de conexión (sin modelo) ------------------------------------------

def cliente_sin_servicio(**cambios):
    url = f"http://127.0.0.1:{puerto_cerrado()}/v1"
    return ModelClient(replace(BASE, LLM_PROVIDER="ollama", EMB_PROVIDER="ollama", OLLAMA_BASE_URL=url,
                               LLM_RETRIES=0, LLM_TIMEOUT_S=5.0, **cambios))


class Cualquiera(BaseModel):
    ok: bool


def test_chat_json_sin_servicio_aborta_como_no_disponible():
    with pytest.raises(LLMUnavailableError) as e:
        cliente_sin_servicio().chat_json("s", "u", Cualquiera)
    assert type(e.value) is LLMUnavailableError
    assert "APIConnectionError" in str(e.value)


def test_chat_json_sin_servicio_con_foundry_omitiendo_temperatura():
    # Recorre la rama que no envía temperature; el error llega igual (endpoint https cerrado).
    s = replace(BASE, LLM_PROVIDER="foundry", FOUNDRY_OMIT_TEMPERATURE=True, LLM_RETRIES=0, LLM_TIMEOUT_S=5.0,
                FOUNDRY_AI_ENDPOINT=f"https://127.0.0.1:{puerto_cerrado()}")
    with pytest.raises(LLMUnavailableError):
        ModelClient(s).chat_json("s", "u", Cualquiera)


def test_embed_sin_servicio_aborta_como_no_disponible():
    with pytest.raises(LLMUnavailableError):
        cliente_sin_servicio().embed(["hola"])


def test_ping_sin_servicio_devuelve_mensaje_de_negocio_y_el_detalle_va_al_log(caplog):
    with caplog.at_level(logging.ERROR):
        estado = cliente_sin_servicio(GROQ_API_KEY="").ping()
    for nombre in ("llm", "embeddings"):
        assert estado[nombre] == {"ok": False, **LLMUnavailableError("").para_usuario()}
    assert "127.0.0.1" not in str(estado)          # nada técnico hacia la pantalla
    assert "Ping de llm falló" in caplog.text      # el detalle sí queda en el log



# --- Texto demasiado largo para el modelo de embeddings (solo la detección; el recorte real se comprueba con el modelo, en el notebook 03) ---

@pytest.mark.parametrize("mensaje", [
    "Error code: 500 - {'error': {'code': 500, 'message': 'input (535 tokens) is too large to process. increase the physical batch size', 'type': 'server_error'}}",
    "This model's maximum context length is 8192 tokens, however you requested 9000 tokens", "Input is too long for this model",
    "the request exceeds the maximum context size"])
def test_demasiado_largo_reconoce_los_rechazos_por_longitud(mensaje):
    from backend.llm.client import demasiado_largo
    assert demasiado_largo(Exception(mensaje))


@pytest.mark.parametrize("mensaje", ["Connection error.", "Error code: 401 - invalid api key", "Error code: 429 - rate limit exceeded", "model not found"])
def test_demasiado_largo_no_confunde_otros_errores(mensaje):
    from backend.llm.client import demasiado_largo
    assert not demasiado_largo(Exception(mensaje))


def test_partir_en_ventanas_cubre_todo_el_texto_sin_perder_ninguna_palabra():
    from backend.llm.client import partir_en_ventanas
    texto = " ".join(f"p{i}" for i in range(500))
    for n in (2, 3, 5, 8):
        v = partir_en_ventanas(texto, n)
        assert len(v) == n and set(" ".join(v).split()) == set(texto.split())                  # cubren todo
        assert all(len(x.split()) < 500 for x in v) and v[0].split()[0] == "p0" and v[-1].split()[-1] == "p499"
        assert set(v[0].split()) & set(v[1].split())                                           # y se solapan


def test_partir_en_ventanas_no_parte_un_texto_corto():
    from backend.llm.client import partir_en_ventanas
    assert partir_en_ventanas("uno dos tres", 4) == ["uno dos tres"] and partir_en_ventanas("a b c d e f", 1) == ["a b c d e f"]


# --- embed con textos más largos que el contexto del modelo ----------------------------------------------------------------
# TransporteConLimite NO imita un modelo: solo rechaza por longitud, como DMR con granite, para probar la lógica de ventanas y de error.

class _Dato:
    def __init__(self, v): self.embedding = v


class TransporteConLimite:
    """`embeddings.create` que rechaza todo texto de más de `limite` palabras con el mensaje real de DMR; el resto sale como [1, len/limite]."""
    def __init__(self, limite, mensaje="Error code: 500 - {'error': {'message': 'input (535 tokens) is too large to process'}}"):
        self.limite, self.mensaje, self.llamadas = limite, mensaje, []
        self.embeddings = self

    def create(self, model, input):
        self.llamadas.append(list(input))
        if any(len(t.split()) > self.limite for t in input):
            raise RuntimeError(self.mensaje)
        return type("R", (), {"data": [_Dato([1.0, len(t.split()) / self.limite]) for t in input]})()


def cliente_con(transporte, lote=4):
    mc = ModelClient(replace(BASE, EMB_PROVIDER="ollama", EMB_BATCH=lote))
    mc._emb = (transporte, "modelo-prueba")
    return mc


def test_embed_un_texto_largo_se_vectoriza_por_ventanas_sin_recortar_nada():
    t = TransporteConLimite(limite=60)
    corto, largo = "palabra " * 10, " ".join(f"p{i}" for i in range(100))
    m = cliente_con(t).embed([corto, largo])
    assert m.shape == (2, 2) and abs(float(np.linalg.norm(m[1])) - 1.0) < 1e-5 and abs(float(np.linalg.norm(m[0])) - 1.0) < 1e-5
    ventanas = [v for llamada in t.llamadas for v in llamada if v.startswith("p0")]
    assert " ".join(ventanas).split().count("p99") >= 1                              # la última palabra del texto llegó al modelo
    todo = set(" ".join(v for llamada in t.llamadas[2:] for v in llamada).split())
    assert {f"p{i}" for i in range(100)} <= todo                                      # ninguna palabra se perdió


def test_embed_con_textos_que_caben_no_usa_ventanas():
    t = TransporteConLimite(limite=60)
    cliente_con(t).embed(["uno dos", "tres cuatro", "cinco"])
    assert len(t.llamadas) == 1                                                       # un solo lote


def test_embed_sube_el_numero_de_ventanas_hasta_que_caben():
    t = TransporteConLimite(limite=20)
    m = cliente_con(t).embed([" ".join(f"p{i}" for i in range(100))])
    assert m.shape == (1, 2) and max(len(v.split()) for llamada in t.llamadas[-1:] for v in llamada) <= 20


def test_embed_si_ni_con_8_ventanas_cabe_el_error_se_propaga():
    from backend.core.errors import ComparadorError
    t = TransporteConLimite(limite=1)
    with pytest.raises(ComparadorError):                                              # error de negocio de nuestro código, no una traza del SDK
        cliente_con(t).embed([" ".join(f"p{i}" for i in range(40))])
    assert len(t.llamadas) == 1 + 7                                                   # el lote entero y luego 2..8 ventanas


def test_embed_otro_error_no_se_toma_por_texto_largo():
    from backend.core.errors import ComparadorError
    t = TransporteConLimite(limite=1, mensaje="Error code: 401 - invalid api key")
    with pytest.raises(ComparadorError):
        cliente_con(t).embed(["uno dos tres"])
    assert len(t.llamadas) == 1                                                       # no reintenta ni parte en ventanas


def test_embed_informa_el_progreso_con_textos_largos():
    t, avance = TransporteConLimite(limite=30), []
    cliente_con(t, lote=2).embed(["a b", " ".join(f"p{i}" for i in range(80)), "c d"], progreso=lambda h, tot: avance.append((h, tot)))
    assert avance == [(2, 3), (3, 3)]
