"""Configuración leída del entorno y de `config/.env`.

Adaptado de `settings.py` de la v6, simplificado.

Precedencia: variable de entorno (app.yaml en Databricks) > `config/.env` (local, con
secretos, ignorado por git) > `config/stages/<STAGE>.env` (proveedores de cada stage:
dev, sandbox o mvp) > `config/defaults.env` (valores por defecto versionados; se lee siempre).
El código no tiene valores por defecto: los `[CALIBRAR]` viven solo en `defaults.env`.

En Databricks el token de Foundry llega como variable de entorno: en Apps con `valueFrom`
en app.yaml y en notebooks con `dbutils.secrets.get` (línea comentada en cada notebook).
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent  # comparador-dbx/
PROMPTS_DIR = RAIZ / "backend" / "prompts"

load_dotenv(RAIZ / "config" / ".env", override=False)
STAGES = ("dev", "sandbox", "mvp")
if os.environ.get("STAGE"):
    if os.environ["STAGE"] not in STAGES:
        raise ValueError(f"STAGE={os.environ['STAGE']!r} no existe; usa uno de {STAGES}")
    load_dotenv(RAIZ / "config" / "stages" / f"{os.environ['STAGE']}.env", override=False)
load_dotenv(RAIZ / "config" / "defaults.env", override=False)  # solo rellena lo que falte


def _env(nombre: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    return "" if valor.startswith("#") else valor   # un comentario de .env leído como valor (según la versión de python-dotenv)


@dataclass(frozen=True)
class Settings:
    # Modelos
    LLM_PROVIDER: str = _env("LLM_PROVIDER")      # groq | foundry | ollama | dmr
    EMB_PROVIDER: str = _env("EMB_PROVIDER")    # ollama | foundry | dmr
    GROQ_API_KEY: str = field(default=_env("GROQ_API_KEY"), repr=False)
    GROQ_BASE_URL: str = _env("GROQ_BASE_URL")
    GROQ_LLM_MODEL: str = _env("GROQ_LLM_MODEL")
    OLLAMA_BASE_URL: str = _env("OLLAMA_BASE_URL")
    OLLAMA_LLM_MODEL: str = _env("OLLAMA_LLM_MODEL")
    OLLAMA_EMB_MODEL: str = _env("OLLAMA_EMB_MODEL")
    DMR_BASE_URL: str = _env("DMR_BASE_URL")
    DMR_LLM_MODEL: str = _env("DMR_LLM_MODEL")
    DMR_EMB_MODEL: str = _env("DMR_EMB_MODEL")
    FOUNDRY_AI_ENDPOINT: str = _env("FOUNDRY_AI_ENDPOINT")
    FOUNDRY_AI_API_VERSION: str = _env("FOUNDRY_AI_API_VERSION")
    FOUNDRY_AI_TOKEN: str = field(default=_env("FOUNDRY_AI_TOKEN"), repr=False)
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
    MANUALES_DIR: str = _env("MANUALES_DIR")      # carpeta de manuales de control (los MOCK, versionados); relativa a comparador-dbx/
    NORMAS_DIR: str = _env("NORMAS_DIR")          # carpeta de PDFs de normas (no se versiona); relativa a comparador-dbx/
    DOCLING_THREADS: int = int(_env("DOCLING_THREADS"))
    DOCLING_DEVICE: str = _env("DOCLING_DEVICE")    # auto | cpu | cuda | mps
    TABLAS_ATOMICAS: bool = _env("TABLAS_ATOMICAS").lower() == "true"   # true: la tabla no se parte sin su cabecera y se unen las continuadas
    DOCLING_TABLES: str = _env("DOCLING_TABLES")          # fast | off | accurate
    DOCLING_TIMEOUT_S: int = int(_env("DOCLING_TIMEOUT_S"))
    DOCLING_CHUNK_PAGES: int = int(_env("DOCLING_CHUNK_PAGES"))

    # Seccionado
    SECCION_CHARS: int = int(_env("SECCION_CHARS"))              # nivel 3: caracteres por bloque
    SECCION_BLOQUE_MAX: int = int(_env("SECCION_BLOQUE_MAX"))    # tope de un bloque de texto (entrada hostil)

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


def _carpeta(valor: str) -> Path:
    ruta = Path(valor)
    return ruta if ruta.is_absolute() else RAIZ / ruta


def carpeta_normas() -> Path:
    """Carpeta donde se leen los PDF de las normas (`NORMAS_DIR`; si es relativa, desde `comparador-dbx/`)."""
    return _carpeta(settings.NORMAS_DIR)


def carpeta_manuales() -> Path:
    """Carpeta donde se leen los manuales de control (`MANUALES_DIR`; los MOCK ficticios están versionados)."""
    return _carpeta(settings.MANUALES_DIR)


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


def _sin_marcas(texto: str) -> str:
    """Quita las marcas `<texto_*>` (con atributos o espacios) en dos pasadas lineales:
    1) borra las marcas completas; 2) si al borrar quedó otra marca formada, su `<` pasa a `‹`
    (no se borra nada más, así que no se puede reconstruir ninguna)."""
    texto = re.sub(r"<\s*/?\s*texto_[^<>]*>", "", texto, flags=re.I)
    return re.sub(r"<(?=\s*/?\s*texto_)", "‹", texto, flags=re.I)


def rellenar_prompt(plantilla: str, **valores: str) -> str:
    """Sustituye `{variable}` en una sola pasada (un valor no puede inyectar la siguiente variable)
    y quita las marcas `<texto_*>` de los valores, para que un documento no cierre el delimitador."""
    limpios = {k: _sin_marcas(str(v)) for k, v in valores.items()}
    return re.sub(r"\{(\w+)\}", lambda m: limpios.get(m.group(1), m.group(0)), plantilla)


def redact(texto: str) -> str:
    """Oculta los secretos configurados y claves con formato conocido antes de registrar."""
    for nombre, valor in settings.__dict__.items():
        if es_secreto(nombre) and len(valor) >= 4:
            texto = texto.replace(valor, "***")
    return re.sub(r"\b(sk-|gsk_|dapi)[A-Za-z0-9_-]{12,}", "***", texto)
