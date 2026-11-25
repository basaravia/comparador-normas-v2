"""Cliente de modelos: un solo SDK `openai` para Groq, Ollama, Azure AI Foundry y los modelos del propio workspace de Databricks.

Adaptado de `providers.py` de la v6, sin LangChain. El proveedor se elige en la
configuración (`LLM_PROVIDER`, `EMB_PROVIDER`), que fija cada stage: DMR en dev, Groq + Ollama en
sandbox y Foundry en mvp. Databricks Free (sin Foundry) usa sus propios modelos: `LLM_PROVIDER=databricks`.

El SDK ya reintenta 429 y 5xx con backoff exponencial (`max_retries=LLM_RETRIES`).
Los dos textos fijos de este archivo (el del reintento de JSON y el del ping) son
mensajes técnicos del cliente, no prompts del producto: esos viven en `backend/prompts/`.
"""
from collections import Counter
from contextvars import ContextVar
from typing import Callable
import json
import os
import re
import logging
import threading
import time
from urllib.parse import urlparse

import httpx
import numpy as np
from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel, ValidationError

from backend.config import Settings, falta, redact, settings
from backend.core.errors import LLMOutputError, LLMUnavailableError, ProviderConfigError, clasificar

log = logging.getLogger(__name__)


def _exigir(**variables: str) -> None:
    """Aborta antes de gastar un token si falta alguna variable, y dice cuáles."""
    faltan = [nombre for nombre, valor in variables.items() if falta(valor)]
    if faltan:
        raise ProviderConfigError(f"Faltan variables de configuración: {', '.join(faltan)}")


CANCELADO_POR: ContextVar[Callable[[], bool] | None] = ContextVar("cancelado_por", default=None)
"""Quien llama (el juez) pone aquí su «¿se canceló?» para que un hilo que espera su turno del modelo local lo mire y se retire sin llamar al modelo (QA-O1)."""


class TurnoCancelado(Exception):
    """Se canceló mientras el hilo esperaba su turno del modelo local: no se le llama."""


_UNIDAD_S = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}


def _limite_de_tasa(e: Exception) -> bool:
    texto = str(e)
    return "RateLimitError" in texto or re.search(r"\b429\b", texto) is not None            # `\b`: «429» como número entero, no dentro de un identificador (7b4291ac)


def espera_sugerida(e: Exception) -> float | None:
    """Segundos que el proveedor pide esperar («try again in 8.1075s», «in 1m30.5s», «in 250ms»), o None si no lo dice."""
    m = re.search(r"try again in ((?:\d+(?:\.\d+)?(?:ms|h|m|s))+)", str(e))
    if not m:
        return None
    return sum(float(n) * _UNIDAD_S[u] for n, u in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", m.group(1)))


class _TokenDatabricks(httpx.Auth):
    """Token de acceso de Databricks para cada petición: el personal de `DATABRICKS_TOKEN` (solo desarrollo local) o, dentro de una App, el OAuth del
    service principal (client credentials), que se renueva antes de vencer. Nunca se escribe en el registro."""

    def __init__(self, s: Settings, host: str):
        self.s, self.host = s, host
        self._token, self._vence, self._lock = "", 0.0, threading.Lock()

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._obtener()}"
        yield request

    def _obtener(self) -> str:
        if not falta(self.s.DATABRICKS_TOKEN):
            return self.s.DATABRICKS_TOKEN
        with self._lock:
            if self._token and time.monotonic() < self._vence:
                return self._token
            try:
                r = httpx.post(f"{self.host}/oidc/v1/token", data={"grant_type": "client_credentials", "scope": "all-apis"}, timeout=10,
                               auth=(self.s.DATABRICKS_CLIENT_ID, self.s.DATABRICKS_CLIENT_SECRET))
                r.raise_for_status()
                datos = r.json()
                self._token, self._vence = datos["access_token"], time.monotonic() + max(60, int(datos.get("expires_in", 3600)) - 120)
            except Exception as e:                                                  # noqa: BLE001
                raise ProviderConfigError(f"No se pudo obtener el token de Databricks ({type(e).__name__})") from None
            return self._token


def _host_databricks(host: str) -> str:
    """URL base del workspace con https (el token no puede viajar en claro); la plataforma a veces entrega el host sin esquema."""
    host = host.strip()
    url = host if "://" in host else f"https://{host}"
    partes = urlparse(url)
    try:
        valido = (partes.scheme == "https" and partes.hostname and not (partes.username or partes.password)      # `https://dbc…@otro.com` enviaría la credencial a otro host
                  and not re.search(r"\s", partes.netloc) and partes.port != 0)                                    # `.port` falla si el puerto no es un número
    except ValueError:
        valido = False
    if not valido:
        raise ProviderConfigError("DATABRICKS_HOST debe ser la dirección del workspace (https://…), sin usuario ni contraseña")
    return f"https://{partes.netloc}"


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
        if proveedor == "ollama" and urlparse(url).hostname not in ("localhost", "127.0.0.1", "::1"):
            log.warning("OLLAMA_BASE_URL no es la máquina local: los textos de normas y manuales saldrán de ella")       # solo el aviso: puede ser una GPU propia en la red
        if proveedor == "ollama" and not embeddings:
            opciones = {"max_retries": 1, "timeout": s.OLLAMA_TIMEOUT_S}      # un modelo pequeño tarda: no se corta a los 120 s y se reintenta una sola vez (un timeout cuesta hasta 2 × OLLAMA_TIMEOUT_S)
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

    if proveedor == "databricks":
        endpoint = s.DATABRICKS_EMB_ENDPOINT if embeddings else s.DATABRICKS_LLM_ENDPOINT
        _exigir(DATABRICKS_HOST=s.DATABRICKS_HOST, **{"DATABRICKS_EMB_ENDPOINT" if embeddings else "DATABRICKS_LLM_ENDPOINT": endpoint})
        if falta(s.DATABRICKS_TOKEN):
            _exigir(DATABRICKS_CLIENT_ID=s.DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET=s.DATABRICKS_CLIENT_SECRET)
        host = _host_databricks(s.DATABRICKS_HOST)
        return OpenAI(base_url=f"{host}/serving-endpoints", api_key="databricks", http_client=httpx.Client(auth=_TokenDatabricks(s, host)), **opciones), endpoint

    if proveedor == "openrouter":
        # Solo como respaldo del LLM (docs/14 #14): un modelo gratuito, sin garantías de disponibilidad ni de privacidad.
        if embeddings:
            raise ProviderConfigError("OpenRouter solo se usa como respaldo del LLM, no para embeddings")
        _exigir(OPENROUTER_API_KEY=s.OPENROUTER_API_KEY, OPENROUTER_BASE_URL=s.OPENROUTER_BASE_URL, OPENROUTER_LLM_MODEL=s.OPENROUTER_LLM_MODEL)
        if os.environ.get("STAGE") == "mvp" and not s.PERMITIR_OPENROUTER:      # un servicio gratuito de un tercero no ve documentos reales sin una decisión explícita
            raise ProviderConfigError("OpenRouter no se admite en el stage mvp (documentos reales); si se quiere de verdad, PERMITIR_OPENROUTER=true")
        url = urlparse(s.OPENROUTER_BASE_URL)
        if url.scheme != "https" or not url.hostname or url.username or url.password:      # la clave no viaja en claro ni a otro host disfrazado (`https://openrouter.ai@otro.com`)
            raise ProviderConfigError("OPENROUTER_BASE_URL debe ser https://… sin usuario ni contraseña")
        return OpenAI(base_url=s.OPENROUTER_BASE_URL, api_key=s.OPENROUTER_API_KEY, **opciones), s.OPENROUTER_LLM_MODEL

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


def _con_json_en_el_usuario(mensajes: list[dict]) -> list[dict]:
    """Databricks exige la palabra «json» en el último mensaje del usuario cuando se pide `response_format` JSON (OpenAI la acepta en cualquiera)."""
    ultimo = max(i for i, m in enumerate(mensajes) if m["role"] == "user")
    if "json" in mensajes[ultimo]["content"].lower():
        return mensajes
    copia = list(mensajes)
    copia[ultimo] = {**mensajes[ultimo], "content": mensajes[ultimo]["content"] + "\n\nResponde en formato json."}
    return copia


class ModelClient:
    """LLM y embeddings con los proveedores de la configuración.

    Los clientes se crean en el primer uso: así se puede usar solo embeddings sin tener
    configurado el LLM, y al revés.
    """

    def __init__(self, s: Settings = settings):
        self.s = s
        self._llm = None
        self._emb = None
        self._cadena: list[tuple[str, OpenAI, str]] | None = None     # el LLM principal y sus respaldos
        self._caidos: dict[str, float] = {}                              # proveedor → hasta cuándo se salta (time.monotonic)
        self.usos: Counter[str] = Counter()                              # llamadas al LLM resueltas por proveedor (solo nombres y cuentas: el registro del trabajo)
        self._lock = threading.Lock()
        self._cupos = {"ollama": threading.BoundedSemaphore(max(1, s.OLLAMA_CONCURRENCIA))}   # el LLM local atiende pocas llamadas a la vez: las demás esperan turno

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
                errores = json.dumps([{"campo": err["loc"], "tipo": err["type"]} for err in e.errors(include_url=False, include_input=False)], ensure_ascii=False, default=str)
                log.warning("JSON inválido del LLM (intento %d): %s", intento, errores[:300])
                mensajes += [
                    {"role": "assistant", "content": respuesta},
                    {"role": "user", "content": f"Tu respuesta no cumple el esquema: {errores}\n"
                                                "Responde de nuevo SOLO con el objeto JSON corregido."},
                ]
        raise LLMOutputError(f"JSON inválido tras el reintento ({len(respuesta)} caracteres)")

    def _proveedores_llm(self) -> list[tuple[str, OpenAI, str]]:
        """El LLM principal y, en orden, sus respaldos de `LLM_FALLBACK`. Un respaldo sin configurar se omite con un aviso; el principal, no."""
        with self._lock:
            if self._cadena is None:
                cliente, modelo = self.llm()
                cadena = [(self.s.LLM_PROVIDER, cliente, modelo)]
                for nombre in (p.strip() for p in self.s.LLM_FALLBACK.split(",")):
                    if not nombre or any(nombre == c[0] for c in cadena):
                        continue
                    try:
                        cadena.append((nombre, *crear_cliente(nombre, self.s)))
                    except ProviderConfigError as e:
                        log.warning("Respaldo del LLM «%s» omitido: %s", nombre, redact(str(e)))       # nombra variables, nunca valores
                self._cadena = cadena
            return self._cadena

    def _conviene_respaldo(self, err: Exception) -> bool:
        """¿Vale la pena pasar al siguiente proveedor? Un límite de tasa corto se espera (lo hace el juez); uno que pide esperar más de lo que esta
        aplicación espera (el límite diario) o cualquier otra caída sí. Los datos del usuario no cambian: solo adónde va la misma llamada."""
        if _limite_de_tasa(err):
            sugerida = espera_sugerida(err)
            return sugerida is not None and sugerida > self.s.LLM_ESPERA_LIMITE_S * self.s.LLM_INTENTOS_LIMITE
        return True

    def _esta_caido(self, proveedor: str) -> bool:
        with self._lock:
            return self._caidos.get(proveedor, 0.0) > time.monotonic()

    def _esperar_turno(self, cupo: threading.BoundedSemaphore) -> None:
        """Espera el turno del modelo local mirando cada segundo si se canceló. El tope cubre TODA la cola, no una llamada: cada hilo de adelante puede tardar hasta
        `OLLAMA_TIMEOUT_S` y con 6 hilos del juez el último espera cinco llamadas (QA-O4: un tope de una sola llamada abortaba la comparación con Ollama sano)."""
        limite = time.monotonic() + self.s.OLLAMA_TIMEOUT_S * max(1, self.s.LLM_CONCURRENCY)
        while not cupo.acquire(timeout=max(0.0, min(1.0, limite - time.monotonic()))):
            cancelado = CANCELADO_POR.get()
            if cancelado is not None and cancelado():
                raise TurnoCancelado()
            if time.monotonic() >= limite:
                raise TimeoutError("se agotó la espera de turno del modelo local")
        try:
            cancelado = CANCELADO_POR.get()
            if cancelado is not None and cancelado():              # canceló justo cuando le tocaba: tampoco se llama
                raise TurnoCancelado()
        except BaseException:
            cupo.release()                                         # el turno ya se tomó: sea cancelación o un fallo al consultarla, no se pierde (QA-O5)
            raise

    def _cabe_en_ollama(self, mensajes: list[dict]) -> bool:
        """¿El prompt cabe en el contexto del modelo local, con la respuesta incluida? Estimación: 3 caracteres por token (español, por lo alto). Si no cabe NO se
        envía: Ollama recortaría el comienzo del prompt (la instrucción del juez) sin avisar y el veredicto sería de otra pregunta."""
        return sum(len(m["content"]) for m in mensajes) / 3 + self.s.OLLAMA_RESERVA_SALIDA <= self.s.OLLAMA_NUM_CTX

    def _completar(self, mensajes: list[dict]) -> str:
        cadena = self._proveedores_llm()
        ahora = time.monotonic()
        with self._lock:
            activos = [c for c in cadena if self._caidos.get(c[0], 0.0) <= ahora] or cadena          # los caídos hace poco se saltan, salvo que todos lo estén
        for i, (proveedor, cliente, modelo) in enumerate(activos):
            enviar = _con_json_en_el_usuario(mensajes) if proveedor == "databricks" else mensajes
            parametros = {"model": modelo, "messages": enviar, "response_format": {"type": "json_object"}}
            if not (proveedor == "foundry" and self.s.FOUNDRY_OMIT_TEMPERATURE):
                parametros["temperature"] = self.s.LLM_TEMPERATURE
            if proveedor == "ollama" and not self._cabe_en_ollama(enviar):
                log.warning("LLM «ollama» no recibe esta llamada: el texto no cabe en su contexto de %d tokens", self.s.OLLAMA_NUM_CTX)
                if i < len(activos) - 1:
                    continue                                   # no está caído: solo no sirve para este texto
                # Ya no hay a quién más pedírselo: este par queda a revisión (como un JSON inválido, docs/09 §4) en vez de abortar toda la comparación (QA-O3).
                raise LLMOutputError(f"El texto no cabe en el contexto del modelo local ({self.s.OLLAMA_NUM_CTX} tokens)")
            cupo = self._cupos.get(proveedor)
            con_turno = False
            try:
                if cupo is not None:
                    self._esperar_turno(cupo)
                    con_turno = True
                    if i < len(activos) - 1 and self._esta_caido(proveedor):      # mientras esperaba, otro hilo comprobó que este proveedor cayó: no se paga otro timeout (QA-O2)
                        continue
                r = cliente.chat.completions.create(**parametros)
            except TurnoCancelado:
                raise
            except Exception as e:
                log.error("Fallo del LLM %s: %s", modelo, redact(str(e)))
                err = clasificar(e)
                if i < len(activos) - 1 and self._conviene_respaldo(err):
                    with self._lock:
                        self._caidos[proveedor] = time.monotonic() + self.s.LLM_FALLBACK_REINTENTO_S
                    log.warning("LLM «%s» no disponible (%s): se usa «%s» durante %d s", proveedor, type(err).__name__, activos[i + 1][0], self.s.LLM_FALLBACK_REINTENTO_S)
                    continue
                if i == len(activos) - 1:
                    with self._lock:
                        self._caidos.clear()                  # nada respondió: la próxima llamada vuelve a probar desde el principal
                raise err from e
            finally:
                if con_turno:
                    cupo.release()                              # DESPUÉS de marcar el proveedor como caído: el siguiente hilo en cola ya lo ve caído y no lo llama
            with self._lock:
                self.usos[proveedor] += 1
            return r.choices[0].message.content or ""
        raise AssertionError("inalcanzable")

    def _crear_embeddings(self, cliente, modelo: str, entrada: list[str]):
        """`embeddings.create` con espera creciente ante un límite de tasa (429): el endpoint gratuito de embeddings de Databricks limita las consultas por segundo
        y no dice cuánto esperar. Cualquier otro error, o agotar los reintentos, sube tal cual."""
        for intento in range(self.s.EMB_REINTENTOS_LIMITE + 1):
            try:
                return cliente.embeddings.create(model=modelo, input=entrada)
            except Exception as e:
                if intento == self.s.EMB_REINTENTOS_LIMITE or not (type(e).__name__ == "RateLimitError" or getattr(e, "status_code", None) == 429):
                    raise
                espera = self.s.EMB_ESPERA_LIMITE_S * 2 ** intento
                log.info("Embeddings: límite de tasa del proveedor, espera %.0f s (reintento %d de %d)", espera, intento + 1, self.s.EMB_REINTENTOS_LIMITE)
                time.sleep(espera)
        raise AssertionError("inalcanzable")

    def _embed_por_ventanas(self, cliente, modelo: str, texto: str) -> np.ndarray:
        """Un texto que el modelo rechaza por largo (granite admite 512 tokens) se vectoriza en ventanas con solape que CUBREN TODO el texto.
        Devuelve un vector por ventana (norma 1), SIN promediar: el promedio diluye la información (coseno 0,89-0,95 con el texto entero);
        el índice guarda cada ventana como fila de la misma sección y el score es el máximo (multi-vector). No se recorta nada.

        Empieza con 2 ventanas y sube hasta 8 si hace falta. En un modelo de contexto amplio (bge-m3, Foundry) no se activa."""
        for n in range(2, 9):
            ventanas = partir_en_ventanas(texto, n)
            try:
                r = self._crear_embeddings(cliente, modelo, ventanas)
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
            r = self._crear_embeddings(cliente, modelo, [texto])
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
                r = self._crear_embeddings(cliente, modelo, lote)
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
