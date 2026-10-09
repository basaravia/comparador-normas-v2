"""Cliente de modelos: un solo SDK `openai` para Groq, Ollama y Azure AI Foundry.

Adaptado de `providers.py` de la v6, sin LangChain. El proveedor se elige en la
configuración (`LLM_PROVIDER`, `EMB_PROVIDER`), que fija cada stage: DMR en dev, Groq + Ollama en
sandbox y Foundry en mvp.

El SDK ya reintenta 429 y 5xx con backoff exponencial (`max_retries=LLM_RETRIES`).
Los dos textos fijos de este archivo (el del reintento de JSON y el del ping) son
mensajes técnicos del cliente, no prompts del producto: esos viven en `backend/prompts/`.
"""
from typing import Callable
import json
import re
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

    if proveedor in ("ollama", "dmr"):
        # Ollama y Docker Model Runner: locales, compatibles con OpenAI y sin clave
        # (el SDK no acepta una vacía, por eso se pasa el nombre del proveedor).
        if proveedor == "ollama":
            url, modelo = s.OLLAMA_BASE_URL, (s.OLLAMA_EMB_MODEL if embeddings else s.OLLAMA_LLM_MODEL)
        else:
            url, modelo = s.DMR_BASE_URL, (s.DMR_EMB_MODEL if embeddings else s.DMR_LLM_MODEL)
        _exigir(**{f"{proveedor.upper()}_{'EMB' if embeddings else 'LLM'}_MODEL": modelo})
        return OpenAI(base_url=url, api_key=proveedor, **opciones), modelo

    if proveedor == "foundry":
        deployment = s.FOUNDRY_AI_EMBED_DEPLOYMENT if embeddings else s.FOUNDRY_AI_DEPLOYMENT
        _exigir(FOUNDRY_AI_ENDPOINT=s.FOUNDRY_AI_ENDPOINT, FOUNDRY_AI_TOKEN=s.FOUNDRY_AI_TOKEN,
                FOUNDRY_AI_API_VERSION=s.FOUNDRY_AI_API_VERSION, FOUNDRY_AI_DEPLOYMENT=deployment)
        # Solo el host: si se pega una URL con ruta (…/openai/v1/), no se duplica (como en la v6).
        partes = urlparse(s.FOUNDRY_AI_ENDPOINT)
        if partes.scheme != "https":  # el token no puede viajar en claro
            raise ProviderConfigError("FOUNDRY_AI_ENDPOINT debe empezar por https://")
        cliente = AzureOpenAI(azure_endpoint=f"{partes.scheme}://{partes.netloc}",
                              api_key=s.FOUNDRY_AI_TOKEN, api_version=s.FOUNDRY_AI_API_VERSION,
                              **opciones)
        return cliente, deployment

    raise ProviderConfigError(f"Proveedor desconocido: {proveedor!r}")


_DEMASIADO_LARGO = re.compile(r"too large|too long|exceeds? the (maximum )?(context|token)|maximum context length|input.{0,40}tokens", re.I)


def demasiado_largo(error: Exception) -> bool:
    """¿El modelo rechazó el texto por superar su contexto? (DMR: "input (535 tokens) is too large to process")."""
    return bool(_DEMASIADO_LARGO.search(str(error)))


def partir_en_ventanas(texto: str, n: int, solape: float = 0.15) -> list[str]:
    """`n` ventanas de palabras con solape que juntas cubren TODO el texto (ninguna palabra se pierde)."""
    palabras = texto.split()
    if n <= 1 or len(palabras) < 2 * n:
        return [texto]
    paso = -(-len(palabras) // n)                       # ceil: tamaño base de cada ventana
    extra = max(1, int(paso * solape))
    return [" ".join(palabras[max(0, i * paso - extra): min(len(palabras), (i + 1) * paso + extra)]) for i in range(n)]


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
                # Sin `input`: no repetir al log ni al modelo fragmentos de normas o manuales.
                errores = json.dumps(e.errors(include_url=False, include_input=False), ensure_ascii=False, default=str)
                log.warning("JSON inválido del LLM (intento %d): %s", intento, errores[:300])
                mensajes += [
                    {"role": "assistant", "content": respuesta},
                    {"role": "user", "content": f"Tu respuesta no cumple el esquema: {errores}\n"
                                                "Responde de nuevo SOLO con el objeto JSON corregido."},
                ]
        raise LLMOutputError(f"JSON inválido tras el reintento ({len(respuesta)} caracteres)")

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

    def _embed_por_ventanas(self, cliente, modelo: str, texto: str) -> np.ndarray:
        """Un texto que el modelo rechaza por largo (granite admite 512 tokens) se vectoriza en ventanas con solape que CUBREN TODO el texto.
        Devuelve un vector por ventana (norma 1), SIN promediar: el promedio diluye la información (coseno 0,89-0,95 con el texto entero);
        el índice guarda cada ventana como fila de la misma sección y el score es el máximo (multi-vector). No se recorta nada.

        Empieza con 2 ventanas y sube hasta 8 si hace falta. En un modelo de contexto amplio (bge-m3, Foundry) no se activa."""
        for n in range(2, 9):
            ventanas = partir_en_ventanas(texto, n)
            try:
                r = cliente.embeddings.create(model=modelo, input=ventanas)
            except Exception as e:
                if not demasiado_largo(e) or n == 8:
                    log.error("Fallo de embeddings %s: %s", modelo, redact(str(e)))
                    raise clasificar(e) from e
                continue
            log.info("Embeddings: un texto superaba el límite del modelo; se vectorizó en %d ventanas (un vector por ventana, sin recortar ni promediar).", n)
            m = np.array([d.embedding for d in r.data], dtype=np.float32)
            return m / np.linalg.norm(m, axis=1, keepdims=True)
        raise AssertionError("inalcanzable")

    def _un_texto(self, cliente, modelo: str, texto: str) -> np.ndarray:
        """Un texto suelto: entero si cabe; si el modelo lo rechaza por largo, por ventanas."""
        try:
            r = cliente.embeddings.create(model=modelo, input=[texto])
        except Exception as e:
            if demasiado_largo(e):
                return self._embed_por_ventanas(cliente, modelo, texto)
            log.error("Fallo de embeddings %s: %s", modelo, redact(str(e)))
            raise clasificar(e) from e
        m = np.array([r.data[0].embedding], dtype=np.float32)
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    def embed_multi(self, textos: list[str], progreso: Callable[[int, int], None] | None = None) -> list[np.ndarray]:
        """Embeddings por lotes de `EMB_BATCH`: una matriz por texto, de norma 1 por fila.

        Casi siempre es 1 fila por texto; si el modelo no admite el texto entero, una fila por ventana (ver `_embed_por_ventanas`).
        `progreso(hechos, total)` se llama tras cada lote (para barras de progreso)."""
        cliente, modelo = self.emb()
        matrices: list[np.ndarray] = []
        for i in range(0, len(textos), self.s.EMB_BATCH):
            lote = textos[i:i + self.s.EMB_BATCH]
            try:
                r = cliente.embeddings.create(model=modelo, input=lote)
                m = np.array([d.embedding for d in r.data], dtype=np.float32)
                m = m / np.linalg.norm(m, axis=1, keepdims=True)
                matrices += [fila[None, :] for fila in m]
            except Exception as e:
                if not demasiado_largo(e):
                    log.error("Fallo de embeddings %s: %s", modelo, redact(str(e)))
                    raise clasificar(e) from e
                matrices += [self._un_texto(cliente, modelo, t) for t in lote]   # un texto del lote no cabe: uno a uno
            if progreso:
                progreso(min(i + self.s.EMB_BATCH, len(textos)), len(textos))
        return matrices

    def embed(self, textos: list[str], progreso: Callable[[int, int], None] | None = None) -> np.ndarray:
        """Una fila por texto (norma 1). Para textos cortos (ping, pruebas); para chunks usa `embed_multi`, que admite ventanas."""
        matrices = self.embed_multi(textos, progreso)
        if any(len(m) != 1 for m in matrices):
            raise ValueError("Algún texto superó el contexto del modelo y se vectorizó por ventanas: usa embed_multi")
        return np.vstack(matrices)

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
                log.error("Ping de %s falló: %s", nombre, redact(str(err)))  # el detalle, solo al log
                estado[nombre] = {"ok": False, **err.para_usuario()}
        return estado
