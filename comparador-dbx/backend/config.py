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
    DOCS_ZONA: str = _env("DOCS_ZONA") or "test"  # test (MOCK y normas públicas; lo que se versiona) | val (documentos reales de validación; nunca se versiona)
    MANUALES_DIR: str = _env("MANUALES_DIR")      # vacío: documentos/<zona>/manuales. Si se define, gana sobre la zona por defecto; relativa a comparador-dbx/
    EXCLUSION_MAX_PCT: float = float(_env("EXCLUSION_MAX_PCT"))        # [CALIBRAR] alerta si se excluye más de este % de las hojas de un documento
    EXCLUSION_MAX_HEREDADAS: int = int(_env("EXCLUSION_MAX_HEREDADAS"))  # [CALIBRAR] alerta si una sola exclusión arrastra más secciones
    NORMAS_DIR: str = _env("NORMAS_DIR")          # vacío: documentos/<zona>/normas. Si se define, gana sobre la zona por defecto; relativa a comparador-dbx/
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

    # Reranker (opcional)
    RERANK_ENABLED: bool = _env("RERANK_ENABLED").lower() == "true"
    RERANK_MODEL: str = _env("RERANK_MODEL")
    RERANK_TOP_N: int = int(_env("RERANK_TOP_N"))
    RERANK_DEVICE: str = _env("RERANK_DEVICE") or "auto"
    RERANK_BATCH: int = int(_env("RERANK_BATCH"))

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


ZONAS = ("test", "val")


def _zona(zona: str | None) -> str:
    z = zona or settings.DOCS_ZONA
    if z not in ZONAS:
        raise ValueError(f"Zona '{z}' no válida: usa {' o '.join(ZONAS)}.")
    return z


def carpeta_normas(zona: str | None = None) -> Path:
    """PDF de las normas: `documentos/<zona>/normas/`. `NORMAS_DIR` (si se define) gana cuando no se pide una zona explícita."""
    return _carpeta(settings.NORMAS_DIR) if settings.NORMAS_DIR and zona is None else RAIZ / "documentos" / _zona(zona) / "normas"


def carpeta_manuales(zona: str | None = None) -> Path:
    """Manuales de control: `documentos/<zona>/manuales/` (los MOCK ficticios, en `test`, van en git). `MANUALES_DIR` gana sin zona explícita."""
    return _carpeta(settings.MANUALES_DIR) if settings.MANUALES_DIR and zona is None else RAIZ / "documentos" / _zona(zona) / "manuales"


def carpeta_comparaciones(zona: str | None = None) -> Path:
    """Comparaciones hechas a mano para validar (CSV/XLSX): `documentos/<zona>/comparaciones/`. En `val` nunca se versionan."""
    return RAIZ / "documentos" / _zona(zona) / "comparaciones"


def carpeta_salida(zona: str | None = None) -> Path:
    """Resultados de las pruebas: `output/<zona>/`. `output/test/` se puede versionar (salvo cachés); `output/val/` nunca."""
    return RAIZ / "output" / _zona(zona)


def zona_de(ruta: str | Path) -> str | None:
    """Zona (`test` o `val`) a la que pertenece un archivo según su ubicación en `documentos/<zona>/`; `None` si está fuera de ambas."""
    p = Path(os.path.normpath(Path(ruta) if Path(ruta).is_absolute() else RAIZ / ruta))      # normaliza `..` sin seguir enlaces simbólicos
    for z in ZONAS:
        if Path(os.path.normpath(RAIZ / "documentos" / z)) in p.parents:
            return z
    return None


def exigir_en_zona(ruta: str | Path, zona: str | None = None) -> str:
    """Devuelve la zona de `ruta` y falla si el archivo está fuera de `documentos/test|val/`, o en otra zona que la pedida.

    Evita que un documento real, leído desde otra carpeta, deje resultados en una zona que se versiona.
    """
    z = zona_de(ruta)
    if z is None:
        raise ValueError(f"{Path(ruta).name} está fuera de documentos/test/ y documentos/val/: muévelo a la zona que corresponda (los reales, a val).")
    if zona and z != zona:
        raise ValueError(f"{Path(ruta).name} es de la zona '{z}' pero se pidió '{zona}'.")
    return z


def carpeta_bloques(zona: str | None = None) -> Path:
    """Caché del texto que Docling extrae de cada PDF: `output/<zona>/bloques/` (contiene el texto íntegro: jamás se versiona)."""
    return carpeta_salida(zona) / "bloques"


def manuales_locales(zona: str | None = None) -> list[Path]:
    """Manuales de la zona que no son los MOCK de git (p. ej. un manual real o parecido a uno real, solo en local)."""
    return sorted(p for p in carpeta_manuales(zona).glob("*.pdf") if not p.name.startswith("MOCK-DEMO-"))


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
    texto = re.sub(r"(://)[^/@\s]+@", r"\1***@", texto)      # usuario:clave@host de una URL (p. ej. HTTPS_PROXY)
    return re.sub(r"\b(sk-|gsk_|dapi)[A-Za-z0-9_-]{12,}", "***", texto)
