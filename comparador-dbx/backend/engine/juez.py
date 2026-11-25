"""Juez auditor normativo (docs/09 §3 y §4): 1 llamada al LLM por par único, concurrente, con verificación de citas.

El modelo devuelve campos (JSON validado con Pydantic); el código verifica cada cita contra el texto fuente y deja `requiere_revision`
cuando algo no cuadra. Una cita verificada se reemplaza por el texto real del documento: al Excel nunca llega texto del modelo.
"""
import asyncio
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from backend.config import Settings, cargar_prompt, rellenar_prompt, settings
from backend.core.errors import LLMOutputError, LLMUnavailableError
from backend.engine.verificacion import verificar_fragmento
from backend.llm.client import ModelClient, _limite_de_tasa, espera_sugerida  # noqa: F401  (se usan aquí y las pruebas las importan de este módulo)
from backend.models import Par, Seccion, Veredicto

log = logging.getLogger(__name__)


class Observador:
    """Recibe los eventos reales del juez (por defecto no hace nada). `servicio.py` lo usa para el progreso en vivo (docs/ux/mejora-experiencia-v1.md)."""

    def empieza(self, par: Par) -> None: ...
    def espera(self, par: Par, segundos: int, intento: int, maximo: int) -> None: ...
    def reanuda(self, par: Par) -> None: ...
    def termina(self, par: Par, hechos: int, total: int) -> None: ...
    def cancelado(self) -> bool:
        return False

    def avance_reciente(self, segundos: float) -> bool:
        """¿Algún par se resolvió hace menos de `segundos`? Sin observador no se sabe: un par que agota sus intentos aborta como siempre."""
        return False


class Cancelado(Exception):
    """El auditor canceló la comparación: no se lanzan más llamadas y las que van en vuelo se abandonan (terminan solas y se descartan)."""


def _dormir(segundos: int, obs: Observador) -> None:
    """Espera de a 1 s para poder cancelar sin quedarse dormido."""
    for _ in range(segundos):
        if obs.cancelado():
            raise Cancelado()
        time.sleep(1)


def _ruta(s: Seccion) -> str:
    return " › ".join(s.ruta) or s.identificador


def _verificar_cita(cita: str | None, texto: str, s: Settings) -> tuple[str | None, bool]:
    """`(cita, verificada)`. Verificada: se devuelve el fragmento real del documento. No verificada: se conserva solo para el anexo."""
    if not cita:
        return None, True                           # sin cita no hay nada que verificar (cobertura nula)
    v = verificar_fragmento(cita, texto, s=s)
    if v.verificado:
        return v.texto_real, True
    return (v.texto_real or None), False            # `dudoso`: el fragmento real más cercano; `no_encontrado`: vacío


def juzgar_par(par: Par, articulo: Seccion, seccion: Seccion, nombres: dict[str, str], cliente: ModelClient, s: Settings = settings,
               obs: Observador | None = None) -> Par:
    """Juzga un par y devuelve el mismo `Par` con veredicto, citas verificadas y `requiere_revision`. Un JSON inválido tras el reintento no aborta."""
    obs = obs or Observador()
    sistema, plantilla = cargar_prompt("juez")
    usuario = rellenar_prompt(plantilla, doc_norma=nombres.get(articulo.doc_id, articulo.doc_id), ruta_articulo=_ruta(articulo),
                              texto_articulo=articulo.texto_literal, doc_manual=nombres.get(seccion.doc_id, seccion.doc_id),
                              ruta_seccion=_ruta(seccion), texto_seccion=seccion.texto_literal)
    intento, vueltas = 0, 0
    while True:
        intento += 1
        try:
            v: Veredicto = cliente.chat_json(sistema, usuario, Veredicto)
            break
        except LLMOutputError:
            par.requiere_revision = True
            log.warning("Par %s: el modelo no devolvió un JSON válido", par.id)
            return par
        except LLMUnavailableError as e:
            if not _limite_de_tasa(e):
                raise
            sugerida = espera_sugerida(e)
            tope = s.LLM_ESPERA_LIMITE_S * s.LLM_INTENTOS_LIMITE
            if sugerida is not None and sugerida > tope:
                raise                       # el proveedor pide esperar más de lo que esta app espera (p. ej. el límite diario, no el del minuto): seguir es inútil
            if intento >= s.LLM_INTENTOS_LIMITE:
                # El límite por minuto lo comparten todos los pares: a uno le puede tocar esperar más que a otros. Se aborta la comparación solo si
                # nadie avanza (el proveedor no da paso) o si este par ya esperó demasiadas vueltas; si los demás progresan, espera su turno.
                if vueltas >= s.LLM_VUELTAS_LIMITE or not obs.avance_reciente(s.LLM_ESPERA_LIMITE_S * s.LLM_INTENTOS_LIMITE):
                    raise
                intento, vueltas = 1, vueltas + 1
            espera = min(max(math.ceil(sugerida) + 1, 2), tope) if sugerida is not None else s.LLM_ESPERA_LIMITE_S * intento
            log.info("Par %s: límite de tasa del proveedor, espera %d s", par.id, espera)
            obs.espera(par, espera, intento, s.LLM_INTENTOS_LIMITE)
            _dormir(espera, obs)
            obs.reanuda(par)
    cita_n, ok_n = _verificar_cita(v.cita_norma, articulo.texto_literal, s)
    cita_m, ok_m = _verificar_cita(v.cita_manual, seccion.texto_literal, s)
    par.veredicto = v.model_copy(update={"cita_norma": cita_n or "", "cita_manual": cita_m})
    par.cita_norma_verificada, par.cita_manual_verificada = ok_n, ok_m
    par.requiere_revision = not (ok_n and ok_m)
    return par


_VIVAS = 0                       # llamadas del juez que siguen corriendo en este proceso, también las huérfanas de una comparación cancelada
_LOCK_VIVAS = threading.Lock()


def llamadas_vivas() -> int:
    """Cuántas llamadas del juez siguen en vuelo. `servicio.comparar` no lanza otra comparación mientras haya `LLM_CONCURRENCY` o más: así las huérfanas no se apilan."""
    with _LOCK_VIVAS:
        return _VIVAS


def _juzgar_contado(*args) -> Par:
    """Corre `juzgar_par` en el hilo del pool contándolo mientras vive (suma al empezar y resta siempre al terminar, aunque falle)."""
    global _VIVAS
    with _LOCK_VIVAS:
        _VIVAS += 1
    try:
        return juzgar_par(*args)
    finally:
        with _LOCK_VIVAS:
            _VIVAS -= 1


PERIODO_VIGIA_S = 0.5            # cada cuánto se mira si el auditor canceló


async def juzgar_pares(pares: list[Par], secciones: dict[str, Seccion], nombres: dict[str, str], cliente: ModelClient,
                       s: Settings = settings, progreso: Callable[[int, int], None] | None = None,
                       obs: Observador | None = None) -> list[Par]:
    """Juzga todos los pares con concurrencia `LLM_CONCURRENCY`. Si el proveedor cae (LLMUnavailableError) se cancela todo y la excepción sube.

    Cancelación: una tarea vigía mira `obs.cancelado()` cada `PERIODO_VIGIA_S` y lanza `Cancelado` sin esperar a las llamadas al modelo en vuelo
    (un hilo no se puede interrumpir): corren en un pool propio que se suelta con `shutdown(wait=False)`, así `asyncio.run` no las espera.
    Esas llamadas terminan solas en segundo plano y su resultado se descarta."""
    obs = obs or Observador()
    sem, hechos, total = asyncio.Semaphore(s.LLM_CONCURRENCY), 0, len(pares)
    pool = ThreadPoolExecutor(max_workers=s.LLM_CONCURRENCY, thread_name_prefix="juez")
    loop = asyncio.get_running_loop()
    t0 = time.perf_counter()
    log.info("Juez: %d pares, concurrencia %d", total, s.LLM_CONCURRENCY)

    async def uno(p: Par) -> None:
        nonlocal hechos
        async with sem:
            if obs.cancelado():
                raise Cancelado()
            obs.empieza(p)
            await loop.run_in_executor(pool, _juzgar_contado, p, secciones[p.articulo_id], secciones[p.seccion_id], nombres, cliente, s, obs)
        if obs.cancelado():                          # llegó tarde: el resultado se descarta
            raise Cancelado()
        hechos += 1
        obs.termina(p, hechos, total)
        if progreso:
            progreso(hechos, total)

    async def vigia() -> None:
        while not obs.cancelado():
            await asyncio.sleep(PERIODO_VIGIA_S)
        raise Cancelado()

    tareas = [asyncio.create_task(uno(p)) for p in pares]
    async def todos() -> None:
        await asyncio.gather(*tareas)

    trabajo, guardia = asyncio.create_task(todos()), asyncio.create_task(vigia())
    try:
        await asyncio.wait({trabajo, guardia}, return_when=asyncio.FIRST_COMPLETED)
        if guardia.done():
            guardia.result()                         # lanza Cancelado
        trabajo.result()                             # lanza la primera excepción de un par, si hubo
    finally:
        for t in (trabajo, guardia, *tareas):
            t.cancel()
        pool.shutdown(wait=False, cancel_futures=True)      # sin esperar a los hilos en vuelo
    log.info("Juez: %d pares en %.0f s (%d a revisión)", total, time.perf_counter() - t0, sum(p.requiere_revision for p in pares))
    return pares
