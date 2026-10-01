"""Cliente de modelos: un solo SDK `openai` para Groq, Ollama y Azure AI Foundry.

Adaptado de `providers.py` de la v6, sin LangChain. El proveedor se elige en la
configuración (`LLM_PROVIDER`, `EMB_PROVIDER`): Groq + Ollama en desarrollo, Foundry en la demo.

El SDK ya reintenta 429 y 5xx con backoff exponencial (`max_retries=LLM_RETRIES`).
Los dos textos fijos de este archivo (el del reintento de JSON y el del ping) son
mensajes técnicos del cliente, no prompts del producto: esos viven en `backend/prompts/`.
"""
import json
import logging
import time
from urllib.parse import urlparse

import numpy as np
from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel, ValidationError

from backend.config import Settings, falta, redact, settings
from backend.core.errors import LLMOutputError, ProviderConfigError, clasificar

log = logging.getLogger(__name__)


def _exigir(**variables: str) -> None:
    """Aborta antes de gastar un token si falta alguna variable, y dice cuáles."""
    faltan = [nombre for nombre, valor in variables.items() if falta(valor)]
    if faltan:
        raise ProviderConfigError(f"Faltan variables de configuración: {', '.join(faltan)}")


def crear_cliente(proveedor: str, s: Settings, embeddings: bool = False) -> tuple[OpenAI, str]:
    """Devuelve `(cliente, modelo)`. En Foundry, el modelo es el nombre del deployment."""
    opciones = {"max_retries": s.LLM_RETRIES, "timeout": s.LLM_TIMEOUT_S}

    if proveedor == "groq":
        _exigir(GROQ_API_KEY=s.GROQ_API_KEY, GROQ_LLM_MODEL=s.GROQ_LLM_MODEL)
        return OpenAI(base_url=s.GROQ_BASE_URL, api_key=s.GROQ_API_KEY, **opciones), s.GROQ_LLM_MODEL

    if proveedor == "ollama":
        modelo = s.OLLAMA_EMB_MODEL if embeddings else s.OLLAMA_LLM_MODEL
        _exigir(OLLAMA_MODEL=modelo)
        # Ollama no pide clave, pero el SDK no acepta una vacía.
        return OpenAI(base_url=s.OLLAMA_BASE_URL, api_key="ollama", **opciones), modelo

    if proveedor == "foundry":
        deployment = s.FOUNDRY_AI_EMBED_DEPLOYMENT if embeddings else s.FOUNDRY_AI_DEPLOYMENT
        _exigir(FOUNDRY_AI_ENDPOINT=s.FOUNDRY_AI_ENDPOINT, FOUNDRY_AI_TOKEN=s.FOUNDRY_AI_TOKEN,
                FOUNDRY_AI_API_VERSION=s.FOUNDRY_AI_API_VERSION, FOUNDRY_AI_DEPLOYMENT=deployment)
        # Solo el host: si se pega una URL con ruta (…/openai/v1/), no se duplica (como en la v6).
        partes = urlparse(s.FOUNDRY_AI_ENDPOINT)
        cliente = AzureOpenAI(azure_endpoint=f"{partes.scheme}://{partes.netloc}",
                              api_key=s.FOUNDRY_AI_TOKEN, api_version=s.FOUNDRY_AI_API_VERSION,
                              **opciones)
        return cliente, deployment

    raise ProviderConfigError(f"Proveedor desconocido: {proveedor!r}")


class ModelClient:
    """LLM y embeddings con los proveedores de la configuración.

    Los clientes se crean en el primer uso: así se puede usar solo embeddings sin tener
    configurado el LLM, y al revés.
    """

    def __init__(self, s: Settings = settings):
        self.s = s
        self._llm = None
        self._emb = None

    def llm(self) -> tuple[OpenAI, str]:
        if self._llm is None:
            self._llm = crear_cliente(self.s.LLM_PROVIDER, self.s)
        return self._llm

    def emb(self) -> tuple[OpenAI, str]:
        if self._emb is None:
            self._emb = crear_cliente(self.s.EMB_PROVIDER, self.s, embeddings=True)
        return self._emb

    def chat_json(self, sistema: str, usuario: str, esquema: type[BaseModel]) -> BaseModel:
        """Pide JSON al LLM y lo valida con `esquema`.

        Si no valida, se reintenta una vez con los errores adjuntos (docs/09 §4).
        Si vuelve a fallar, lanza `LLMOutputError` y quien llama marca la fila para revisión.
        """
        mensajes = [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]
        for intento in (1, 2):
            respuesta = self._completar(mensajes)
            try:
                return esquema.model_validate_json(respuesta)
            except ValidationError as e:
                errores = json.dumps(e.errors(include_url=False), ensure_ascii=False, default=str)
                log.warning("JSON inválido del LLM (intento %d): %s", intento, errores[:300])
                mensajes += [
                    {"role": "assistant", "content": respuesta},
                    {"role": "user", "content": f"Tu respuesta no cumple el esquema: {errores}\n"
                                                "Responde de nuevo SOLO con el objeto JSON corregido."},
                ]
        raise LLMOutputError(f"JSON inválido tras el reintento: {respuesta[:500]}")

    def _completar(self, mensajes: list[dict]) -> str:
        cliente, modelo = self.llm()
        parametros = {"model": modelo, "messages": mensajes, "response_format": {"type": "json_object"}}
        if not (self.s.LLM_PROVIDER == "foundry" and self.s.FOUNDRY_OMIT_TEMPERATURE):
            parametros["temperature"] = self.s.LLM_TEMPERATURE
        try:
            r = cliente.chat.completions.create(**parametros)
        except Exception as e:
            log.error("Fallo del LLM %s: %s", modelo, redact(str(e)))
            raise clasificar(e) from e
        return r.choices[0].message.content or ""

    def embed(self, textos: list[str]) -> np.ndarray:
        """Embeddings por lotes de `EMB_BATCH`: matriz float32 con cada fila de norma 1."""
        cliente, modelo = self.emb()
        vectores = []
        for i in range(0, len(textos), self.s.EMB_BATCH):
            try:
                r = cliente.embeddings.create(model=modelo, input=textos[i:i + self.s.EMB_BATCH])
            except Exception as e:
                log.error("Fallo de embeddings %s: %s", modelo, redact(str(e)))
                raise clasificar(e) from e
            vectores += [d.embedding for d in r.data]
        m = np.array(vectores, dtype=np.float32)
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    def ping(self) -> dict:
        """Una llamada mínima real al LLM y a los embeddings. Para el health check."""
        class Pong(BaseModel):
            ok: bool

        pruebas = {
            "llm": lambda: self.chat_json('Responde solo este JSON: {"ok": true}', "ping", Pong),
            "embeddings": lambda: self.embed(["ping"]),
        }
        estado = {}
        for nombre, prueba in pruebas.items():
            t0 = time.perf_counter()
            try:
                prueba()
                estado[nombre] = {"ok": True, "ms": round((time.perf_counter() - t0) * 1000)}
            except Exception as e:
                err = clasificar(e)
                estado[nombre] = {"ok": False, **err.para_usuario(), "detalle": redact(str(err))}
        return estado
