"""Aplicación FastAPI: monta /api y sirve el frontend compilado (docs/11, docs/12). Un solo proceso uvicorn (`--workers 1`, CLAUDE.md regla 6)."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.rutas import router
from backend.config import RAIZ, logo_permitido, settings
from backend.core.errors import ComparadorError, LLMUnavailableError
from backend.core.progreso import configurar_logs
from backend.core import sesiones
from backend.core.sesiones import IdentidadInvalida, SesionesLlenas, SesionPerdida

configurar_logs()
log = logging.getLogger(__name__)
DIST = RAIZ / "frontend" / "dist"

def comprobar_identidad() -> None:
    """Con `TRUST_PROXY_IDENTITY` la app solo debe correr detrás del proxy de Databricks Apps, que inyecta `DATABRICKS_APP_NAME`; si no, no arranca."""
    if settings.TRUST_PROXY_IDENTITY and not os.environ.get("DATABRICKS_APP_NAME"):
        raise RuntimeError("TRUST_PROXY_IDENTITY está encendida pero falta DATABRICKS_APP_NAME: la app no corre detrás del proxy de Databricks. Apaga la bandera o despliega en Databricks Apps.")


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    comprobar_identidad()
    if settings.LIMPIAR_TMP_AL_ARRANCAR:
        log.info("Limpieza de arranque: %d carpetas de sesión huérfanas borradas", sesiones.limpiar_tmp_huerfanos())
    yield


app = FastAPI(title="Comparador Normativo de Doble Vía", docs_url=None, redoc_url=None, openapi_url=None, lifespan=ciclo_de_vida)
app.include_router(router)

CABECERAS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
             "Content-Security-Policy": "default-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"}


@app.middleware("http")
async def cabeceras(request: Request, call_next):
    origen = request.headers.get("sec-fetch-site", "same-origin").lower()          # sin la cabecera (clientes que no son navegador) se permite
    largo = request.headers.get("content-length", "")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith("/api") and origen not in ("same-origin", "none"):
        respuesta = _json(403, "ERR-SEG-001", "No pudimos validar el origen de la solicitud. Recarga la página e inténtalo de nuevo.")
    elif request.method == "POST" and request.url.path == "/api/documents" and largo.isdigit() and int(largo) > tope_subida():
        # El cuerpo entero supera lo que cabría en una sesión: se corta antes de recibirlo (el límite por archivo sigue en `_leer`).
        respuesta = _json(413, "ERR-ING-002", f"El archivo supera el máximo de {settings.MAX_PAGES} páginas o {settings.MAX_MB} MB. Divídelo o consulta con el equipo de soporte.")
    else:
        respuesta = await call_next(request)
    return con_cabeceras(request, respuesta)


def tope_subida() -> int:
    """Bytes máximos de una subida: todos los documentos que caben en una sesión, cada uno con su máximo de MB, más un MB de sobres de formulario."""
    return (settings.MAX_DOCS_SESION * settings.MAX_MB + 1) * 1024 ** 2


def con_cabeceras(request: Request, respuesta):
    for k, v in CABECERAS.items():
        respuesta.headers.setdefault(k, v)
    if request.url.path.startswith("/api"):
        respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


def _json(estado: int, codigo: str, mensaje: str) -> JSONResponse:
    return JSONResponse({"codigo": codigo, "mensaje": mensaje}, status_code=estado)


@app.exception_handler(SesionPerdida)
async def _sesion_perdida(_: Request, __: SesionPerdida):
    return _json(410, "ERR-SES-001", "Se perdió lo que tenías cargado: la aplicación se reinició o pasó el plazo de conservación. Carga de nuevo tus PDF.")


@app.exception_handler(IdentidadInvalida)
async def _sin_identidad(_: Request, e: IdentidadInvalida):
    return _json(401, e.codigo, e.mensaje_negocio)


@app.exception_handler(SesionesLlenas)
async def _llenas(_: Request, e: SesionesLlenas):
    return _json(503, e.codigo, e.mensaje_negocio)


@app.exception_handler(LLMUnavailableError)
async def _llm(_: Request, e: LLMUnavailableError):
    log.error("LLM no disponible: %s", e)
    return _json(503, e.codigo, e.mensaje_negocio)


@app.exception_handler(ComparadorError)
async def _dominio(_: Request, e: ComparadorError):
    return _json(getattr(e, "estado_http", 422), e.codigo, e.mensaje_negocio)


@app.exception_handler(RequestValidationError)
async def _validacion(_: Request, __: RequestValidationError):
    return _json(422, "ERR-API-422", "La solicitud no es válida. Recarga la página e inténtalo de nuevo.")


@app.exception_handler(StarletteHTTPException)
async def _http(_: Request, e: StarletteHTTPException):
    return _json(e.status_code, f"ERR-HTTP-{e.status_code}", "No encontramos lo que buscabas." if e.status_code == 404 else "No pudimos completar la solicitud.")


@app.exception_handler(Exception)
async def _inesperado(request: Request, e: Exception):
    log.exception("Error no controlado")
    return con_cabeceras(request, _json(500, ComparadorError.codigo, ComparadorError.mensaje_negocio))


SIN_CACHE = {"Cache-Control": "no-cache"}       # el navegador revalida el index.html en cada carga (los bundles llevan hash en el nombre)
TIPOS_LOGO = {".svg": "image/svg+xml", ".png": "image/png"}


@app.get("/marca/{nombre}", include_in_schema=False)
def logo(nombre: str):
    """Sirve solo los logos que la configuración nombra (docs/ux/identidad-visual-v1.md §4). La CSP propia hace inofensivo un SVG abierto a pantalla completa."""
    archivo = logo_permitido(nombre)
    if archivo is None:
        return _json(404, "ERR-HTTP-404", "No encontramos lo que buscabas.")
    return FileResponse(archivo, media_type=TIPOS_LOGO[archivo.suffix.lower()],
                        headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox", "Cache-Control": "private, max-age=3600"})


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    async def spa(ruta: str):
        if ruta.startswith("api/"):
            return _json(404, "ERR-HTTP-404", "No encontramos lo que buscabas.")
        archivo = (DIST / ruta).resolve()
        if ruta and archivo.is_file() and DIST.resolve() in archivo.parents:
            return FileResponse(archivo, headers=SIN_CACHE if archivo.name == "index.html" else None)
        return FileResponse(DIST / "index.html", headers=SIN_CACHE)       # sin esto el navegador reutilizaba un index.html viejo que apunta a bundles ya borrados tras desplegar
