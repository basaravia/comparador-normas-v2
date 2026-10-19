"""Endpoints REST (docs/11). Prefijo /api. Los endpoints son síncronos: FastAPI los corre en su pool de hilos y el trabajo largo va a jobs."""
import logging
import os
import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import FileResponse

from backend.api import schemas as S
from backend.config import settings
from backend.core import sesiones
from backend.core.errors import ComparadorError
from backend.core.sesiones import Sesion, SesionPerdida
from backend.engine import servicio
from backend.llm.client import ModelClient

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
COOKIE = "session_id"
_cliente = ModelClient()                                     # un cliente por proceso (los SDK son seguros entre hilos)
_health: dict = {"t": 0.0, "out": None}


def sesion_actual(request: Request, response: Response) -> Sesion:
    """La sesión de la cookie. Sin cookie se crea una; con una cookie que ya no existe (reinicio, expiración) → 410."""
    sid = request.cookies.get(COOKIE)
    if sid is None:
        s = sesiones.crear()
        seguro = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        response.set_cookie(COOKIE, s.id, httponly=True, samesite="lax", secure=seguro, max_age=settings.SESSION_TTL_HOURS * 3600)
        return s
    return sesiones.obtener(sid)


Ses = Annotated[Sesion, Depends(sesion_actual)]


def _doc(s: Sesion, doc_id: str):
    d = s.docs.get(doc_id)
    if d is None:
        raise servicio.ComparacionError("ERR-DOC-001", "No encontramos ese documento. Puede que la sesión se haya reiniciado.")
    return d


def _leer(archivo: UploadFile) -> bytes:
    """Lee el archivo por tramos y corta al pasar el máximo: un cuerpo enorme no llena la memoria."""
    limite, trozos, total = settings.MAX_MB * 1024 ** 2, [], 0
    while chunk := archivo.file.read(1024 * 1024):
        total += len(chunk)
        if total > limite:
            raise servicio.ComparacionError("ERR-ING-002", f"El archivo supera el máximo de {settings.MAX_PAGES} páginas o {settings.MAX_MB} MB. Divídelo o consulta con el equipo de soporte.")
        trozos.append(chunk)
    return b"".join(trozos)


@router.get("/session", response_model=S.SesionOut)
def sesion(s: Ses):
    ultima = next((i for i, c in reversed(s.comparaciones.items()) if c.out.estado == "listo"), None)
    return S.SesionOut(documentos=[d.out for d in s.docs.values()], comparacion_id=ultima)


@router.delete("/session")
def reiniciar(request: Request, response: Response):
    sesiones.reiniciar(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.post("/documents", response_model=list[S.DocumentoOut])
def subir(s: Ses, archivos: Annotated[list[UploadFile], File()]):
    if len(archivos) > settings.MAX_DOCS_SESION - len(s.docs):
        raise servicio.ComparacionError("ERR-ING-004", f"Puedes cargar hasta {settings.MAX_DOCS_SESION} documentos por sesión. Reinicia la sesión para empezar de nuevo.")
    contenidos = [(a.filename or "documento.pdf", _leer(a)) for a in archivos]
    return servicio.subir_varios(s, contenidos, _cliente)


@router.patch("/documents/{doc_id}", response_model=S.DocumentoOut)
def editar(s: Ses, doc_id: str, cambios: S.DocumentoPatch):
    d = _doc(s, doc_id)
    if d.out.estado not in ("cargado", "error"):
        raise servicio.ComparacionError("ERR-DOC-003", "Este documento ya se procesó; para cambiar su tipo, reinicia la sesión y cárgalo de nuevo.")
    if cambios.tipo is not None:
        d.out.tipo, d.out.tipo_sugerido = cambios.tipo, False
    if cambios.metadatos is not None:
        d.out.metadatos = d.out.metadatos.model_copy(update=cambios.metadatos.model_dump(exclude_unset=True))      # solo los campos enviados
    return d.out


@router.post("/documents/process", response_model=S.JobOut)
def procesar(s: Ses, cuerpo: S.ProcesarIn):
    return servicio.procesar(s, cuerpo.doc_ids, _cliente)


@router.get("/jobs/{job_id}", response_model=S.JobOut)
def job(s: Ses, job_id: str):
    j = s.jobs.get(job_id)
    if j is None:
        raise servicio.ComparacionError("ERR-JOB-404", "No encontramos esa tarea. Puede que la sesión se haya reiniciado.")
    return j


@router.get("/sections/tree", response_model=list[S.ArbolDocOut])
def arbol(s: Ses, tipo: S.Tipo):
    return servicio.arbol(s, tipo)


@router.get("/sections/{section_id:path}", response_model=S.SeccionOut)
def seccion(s: Ses, section_id: str):
    return servicio.seccion(s, section_id)


@router.post("/comparisons", response_model=S.JobOut)
def comparar(s: Ses, cuerpo: S.ComparacionIn):
    return servicio.comparar(s, cuerpo.articulo_ids, cuerpo.seccion_ids, _cliente)


def _comp(s: Sesion, cid: str):
    c = s.comparaciones.get(cid)
    if c is None:
        raise servicio.ComparacionError("ERR-CMP-404", "No encontramos esa comparación. Puede que la sesión se haya reiniciado.")
    return c


@router.get("/comparisons/{cid}", response_model=S.ComparacionOut)
def resultado(s: Ses, cid: str):
    return _comp(s, cid).out


@router.put("/comparisons/{cid}/conclusion", response_model=S.ComparacionOut)
def conclusion(s: Ses, cid: str, cuerpo: S.ConclusionIn):
    c = _comp(s, cid)
    if c.entrada is None:
        raise servicio.ComparacionError("ERR-CMP-005", "La comparación todavía no termina.")
    if len(cuerpo.texto) > 20000:
        raise servicio.ComparacionError("ERR-CMP-006", "La conclusión es demasiado larga (máximo 20 000 caracteres).")
    return servicio.guardar_conclusion(c, cuerpo.texto)


@router.get("/comparisons/{cid}/excel")
def descargar(s: Ses, cid: str):
    c = _comp(s, cid)
    if c.entrada is None:
        raise servicio.ComparacionError("ERR-CMP-005", "La comparación todavía no termina.")
    ruta = servicio.excel(s, c)
    return FileResponse(ruta, filename="papel_de_trabajo.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/samples/load", response_model=list[S.DocumentoOut])
def ejemplo(s: Ses):
    return servicio.cargar_ejemplo(s)


@router.get("/health", response_model=S.HealthOut)
def salud():
    """Estado + ping real al LLM (cacheado 60 s para no gastar tokens en cada sondeo)."""
    if _health["out"] is None or time.time() - _health["t"] > 60:
        estado = _cliente.ping()
        llm = bool(estado.get("llm", {}).get("ok")) and bool(estado.get("embeddings", {}).get("ok"))
        _health.update(t=time.time(), out=S.HealthOut(estado="ok" if llm else "degradado", stage=os.environ.get("STAGE", ""), llm=llm,
                                                      mensaje="" if llm else "No pudimos conectarnos al servicio de análisis."))
    return _health["out"]
