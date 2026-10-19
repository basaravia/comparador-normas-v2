"""Juez auditor normativo (docs/09 §3 y §4): 1 llamada al LLM por par único, concurrente, con verificación de citas.

El modelo devuelve campos (JSON validado con Pydantic); el código verifica cada cita contra el texto fuente y deja `requiere_revision`
cuando algo no cuadra. Una cita verificada se reemplaza por el texto real del documento: al Excel nunca llega texto del modelo.
"""
import asyncio
import logging
import time
from typing import Callable

from backend.config import Settings, cargar_prompt, rellenar_prompt, settings
from backend.core.errors import LLMOutputError, LLMUnavailableError
from backend.engine.verificacion import verificar_fragmento
from backend.llm.client import ModelClient
from backend.models import Par, Seccion, Veredicto

log = logging.getLogger(__name__)
ESPERA_LIMITE_S = 20            # espera base ante un límite de tasa del proveedor (429); crece con cada intento
INTENTOS_LIMITE = 6


def _ruta(s: Seccion) -> str:
    return " › ".join(s.ruta) or s.identificador


def _limite_de_tasa(e: Exception) -> bool:
    return "RateLimitError" in str(e) or "429" in str(e)


def _verificar_cita(cita: str | None, texto: str, s: Settings) -> tuple[str | None, bool]:
    """`(cita, verificada)`. Verificada: se devuelve el fragmento real del documento. No verificada: se conserva solo para el anexo."""
    if not cita:
        return None, True                           # sin cita no hay nada que verificar (cobertura nula)
    v = verificar_fragmento(cita, texto, s=s)
    if v.verificado:
        return v.texto_real, True
    return (v.texto_real or None), False            # `dudoso`: el fragmento real más cercano; `no_encontrado`: vacío


def juzgar_par(par: Par, articulo: Seccion, seccion: Seccion, nombres: dict[str, str], cliente: ModelClient, s: Settings = settings) -> Par:
    """Juzga un par y devuelve el mismo `Par` con veredicto, citas verificadas y `requiere_revision`. Un JSON inválido tras el reintento no aborta."""
    sistema, plantilla = cargar_prompt("juez")
    usuario = rellenar_prompt(plantilla, doc_norma=nombres.get(articulo.doc_id, articulo.doc_id), ruta_articulo=_ruta(articulo),
                              texto_articulo=articulo.texto_literal, doc_manual=nombres.get(seccion.doc_id, seccion.doc_id),
                              ruta_seccion=_ruta(seccion), texto_seccion=seccion.texto_literal)
    for intento in range(1, INTENTOS_LIMITE + 1):
        try:
            v: Veredicto = cliente.chat_json(sistema, usuario, Veredicto)
            break
        except LLMOutputError:
            par.requiere_revision = True
            log.warning("Par %s: el modelo no devolvió un JSON válido", par.id)
            return par
        except LLMUnavailableError as e:
            if _limite_de_tasa(e) and intento < INTENTOS_LIMITE:
                log.info("Par %s: límite de tasa del proveedor, espera %d s", par.id, ESPERA_LIMITE_S * intento)
                time.sleep(ESPERA_LIMITE_S * intento)
                continue
            raise
    cita_n, ok_n = _verificar_cita(v.cita_norma, articulo.texto_literal, s)
    cita_m, ok_m = _verificar_cita(v.cita_manual, seccion.texto_literal, s)
    par.veredicto = v.model_copy(update={"cita_norma": cita_n or "", "cita_manual": cita_m})
    par.cita_norma_verificada, par.cita_manual_verificada = ok_n, ok_m
    par.requiere_revision = not (ok_n and ok_m)
    return par


async def juzgar_pares(pares: list[Par], secciones: dict[str, Seccion], nombres: dict[str, str], cliente: ModelClient,
                       s: Settings = settings, progreso: Callable[[int, int], None] | None = None) -> list[Par]:
    """Juzga todos los pares con concurrencia `LLM_CONCURRENCY`. Si el proveedor cae (LLMUnavailableError) se cancela todo y la excepción sube."""
    sem, hechos, total = asyncio.Semaphore(s.LLM_CONCURRENCY), 0, len(pares)
    t0 = time.perf_counter()
    log.info("Juez: %d pares, concurrencia %d", total, s.LLM_CONCURRENCY)

    async def uno(p: Par) -> None:
        nonlocal hechos
        async with sem:
            await asyncio.to_thread(juzgar_par, p, secciones[p.articulo_id], secciones[p.seccion_id], nombres, cliente, s)
        hechos += 1
        if progreso:
            progreso(hechos, total)

    tareas = [asyncio.create_task(uno(p)) for p in pares]
    try:
        await asyncio.gather(*tareas)
    except BaseException:
        for t in tareas:
            t.cancel()
        raise
    log.info("Juez: %d pares en %.0f s (%d a revisión)", total, time.perf_counter() - t0, sum(p.requiere_revision for p in pares))
    return pares
