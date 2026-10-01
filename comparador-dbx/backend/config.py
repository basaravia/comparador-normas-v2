"""Configuración leída del entorno y de `config/.env`.

Adaptado de `settings.py` de la v6, simplificado.

Precedencia: variable de entorno (app.yaml en Databricks) > `config/.env` (local, con
secretos, ignorado por git) > `config/.env.example` (valores iniciales versionados).
El código no tiene valores por defecto: los `[CALIBRAR]` viven solo en `.env.example`.

En Databricks el token de Foundry llega como variable de entorno: en Apps con `valueFrom`
en app.yaml y en notebooks con `dbutils.secrets.get` (línea comentada en cada notebook).
"""
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent  # comparador-dbx/
PROMPTS_DIR = RAIZ / "backend" / "prompts"

load_dotenv(RAIZ / "config" / ".env", override=False)
load_dotenv(RAIZ / "config" / ".env.example", override=False)  # solo rellena lo que falte


def _env(nombre: str) -> str:
    return os.environ.get(nombre, "").strip()


@dataclass(frozen=True)
class Settings:
    # Modelos
    LLM_PROVIDER: str = _env("LLM_PROVIDER")      # groq | foundry | ollama
    EMB_PROVIDER: str = _env("EMB_PROVIDER")    # ollama | foundry
    GROQ_API_KEY: str = _env("GROQ_API_KEY")
    GROQ_BASE_URL: str = _env("GROQ_BASE_URL")
    GROQ_LLM_MODEL: str = _env("GROQ_LLM_MODEL")
    OLLAMA_BASE_URL: str = _env("OLLAMA_BASE_URL")
    OLLAMA_LLM_MODEL: str = _env("OLLAMA_LLM_MODEL")
    OLLAMA_EMB_MODEL: str = _env("OLLAMA_EMB_MODEL")
    FOUNDRY_AI_ENDPOINT: str = _env("FOUNDRY_AI_ENDPOINT")
    FOUNDRY_AI_API_VERSION: str = _env("FOUNDRY_AI_API_VERSION")
    FOUNDRY_AI_TOKEN: str = _env("FOUNDRY_AI_TOKEN")
    FOUNDRY_AI_DEPLOYMENT: str = _env("FOUNDRY_AI_DEPLOYMENT")
    FOUNDRY_AI_EMBED_DEPLOYMENT: str = _env("FOUNDRY_AI_EMBED_DEPLOYMENT")
    # Los modelos de razonamiento (GPT-5.x) solo aceptan la temperatura de fábrica.
    FOUNDRY_OMIT_TEMPERATURE: bool = _env("FOUNDRY_OMIT_TEMPERATURE").lower() == "true"
    LLM_TEMPERATURE: float = float(_env("LLM_TEMPERATURE"))
    LLM_TIMEOUT_S: float = float(_env("LLM_TIMEOUT_S"))

    # Ingesta
    MAX_PAGES: int = int(_env("MAX_PAGES"))
    MAX_MB: int = int(_env("MAX_MB"))
    SCAN_TEXT_RATIO: float = float(_env("SCAN_TEXT_RATIO"))
    TYPE_CONFIDENCE: float = float(_env("TYPE_CONFIDENCE"))

    # Extracción
    DOCLING_ARTIFACTS: str = _env("DOCLING_ARTIFACTS")
    DOCLING_THREADS: int = int(_env("DOCLING_THREADS"))

    # Indexación
    SUBCHUNK_TOKENS: int = int(_env("SUBCHUNK_TOKENS"))
    SUBCHUNK_OVERLAP: float = float(_env("SUBCHUNK_OVERLAP"))
    EMB_BATCH: int = int(_env("EMB_BATCH"))

    # Recuperación
    K_SUBCHUNKS: int = int(_env("K_SUBCHUNKS"))
    SIM_THRESHOLD: float = float(_env("SIM_THRESHOLD"))
    MIN_FLOOR: int = int(_env("MIN_FLOOR"))
    MAX_CANDIDATES: int = int(_env("MAX_CANDIDATES"))

    # Juez
    LLM_CONCURRENCY: int = int(_env("LLM_CONCURRENCY"))
    LLM_RETRIES: int = int(_env("LLM_RETRIES"))
    CITATION_FUZZY_MIN: float = float(_env("CITATION_FUZZY_MIN"))
    CITATION_SHOW_MIN: float = float(_env("CITATION_SHOW_MIN"))

    # Sesión
    SESSION_TTL_HOURS: int = int(_env("SESSION_TTL_HOURS"))

    # Papel de trabajo
    COLOR_PRIMARIO: str = _env("COLOR_PRIMARIO")
    COLOR_FONDO: str = _env("COLOR_FONDO")

    def publico(self) -> dict:
        """La configuración con los secretos ocultos, para mostrar o registrar."""
        return {k: ("***" if es_secreto(k) and v else v) for k, v in self.__dict__.items()}


settings = Settings()


def es_secreto(nombre: str) -> bool:
    return nombre.endswith(("_KEY", "_TOKEN"))  # GROQ_API_KEY, FOUNDRY_AI_TOKEN


def falta(valor: str) -> bool:
    """Vacío o con el marcador `REEMPLAZAR-…` de app.yaml."""
    return not valor or valor.upper().startswith("REEMPLAZAR")


def cargar_prompt(nombre: str) -> tuple[str, str]:
    """Lee `backend/prompts/<nombre>.md` y devuelve `(sistema, usuario)`."""
    texto = (PROMPTS_DIR / f"{nombre}.md").read_text(encoding="utf-8")
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S)  # comentario con las variables
    sistema, usuario = texto.split("# SISTEMA", 1)[1].split("# USUARIO", 1)
    return sistema.strip(), usuario.strip()


def redact(texto: str) -> str:
    """Oculta los secretos configurados y claves con formato conocido antes de registrar."""
    for nombre, valor in settings.__dict__.items():
        if es_secreto(nombre) and len(valor) >= 4:
            texto = texto.replace(valor, "***")
    return re.sub(r"\b(sk-|gsk_|dapi)[A-Za-z0-9_-]{12,}", "***", texto)
