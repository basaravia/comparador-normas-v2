"""Aplicación FastAPI: monta /api y sirve el frontend compilado (docs/11, docs/12). Un solo proceso uvicorn (`--workers 1`, CLAUDE.md regla 6)."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.rutas import router
from backend.config import RAIZ
from backend.core.errors import ComparadorError, LLMUnavailableError
from backend.core.progreso import configurar_logs
from backend.core.sesiones import SesionPerdida

configurar_logs()
log = logging.getLogger(__name__)
DIST = RAIZ / "frontend" / "dist"

app = FastAPI(title="Comparador Normativo de Doble Vía", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router)

CABECERAS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
             "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"}


@app.middleware("http")
async def cabeceras(request: Request, call_next):
    respuesta = await call_next(request)
    for k, v in CABECERAS.items():
        respuesta.headers.setdefault(k, v)
    if request.url.path.startswith("/api"):
        respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


def _json(estado: int, codigo: str, mensaje: str) -> JSONResponse:
    return JSONResponse({"codigo": codigo, "mensaje": mensaje}, status_code=estado)


@app.exception_handler(SesionPerdida)
async def _sesion_perdida(_: Request, __: SesionPerdida):
    return _json(410, "ERR-SES-001", "La sesión se reinició y los documentos ya no están disponibles. Vuelve a cargarlos o usa el ejemplo.")


@app.exception_handler(LLMUnavailableError)
async def _llm(_: Request, e: LLMUnavailableError):
    log.error("LLM no disponible: %s", e)
    return _json(503, e.codigo, e.mensaje_negocio)


@app.exception_handler(ComparadorError)
async def _dominio(_: Request, e: ComparadorError):
    return _json(422, e.codigo, e.mensaje_negocio)


@app.exception_handler(RequestValidationError)
async def _validacion(_: Request, __: RequestValidationError):
    return _json(422, "ERR-API-422", "La solicitud no es válida. Recarga la página e inténtalo de nuevo.")


@app.exception_handler(StarletteHTTPException)
async def _http(_: Request, e: StarletteHTTPException):
    return _json(e.status_code, f"ERR-HTTP-{e.status_code}", "No encontramos lo que buscabas." if e.status_code == 404 else "No pudimos completar la solicitud.")


@app.exception_handler(Exception)
async def _inesperado(_: Request, e: Exception):
    log.exception("Error no controlado")
    return _json(500, ComparadorError.codigo, ComparadorError.mensaje_negocio)


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    async def spa(ruta: str):
        if ruta.startswith("api/"):
            return _json(404, "ERR-HTTP-404", "No encontramos lo que buscabas.")
        archivo = (DIST / ruta).resolve()
        if ruta and archivo.is_file() and DIST.resolve() in archivo.parents:
            return FileResponse(archivo)
        return FileResponse(DIST / "index.html")
