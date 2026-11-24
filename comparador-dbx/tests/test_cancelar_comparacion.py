"""Cancelar una comparación mientras se juzgan los pares (corrección del 23 nov 2026). Deterministas: ningún modelo interviene.

Las llamadas lentas al modelo se simulan con un `juzgar_par` que espera un evento: se prueba la mecánica de concurrencia, no el juicio."""
import asyncio
import threading
import time
from dataclasses import replace

import pytest

from backend.api.schemas import JobOut
from backend.config import settings
from backend.core import sesiones
from backend.engine import ajustes, juez, servicio
from backend.engine.juez import Cancelado, Observador, juzgar_pares
from backend.models import Par, Seccion, Veredicto

DOS = replace(settings, LLM_CONCURRENCY=2)


def seccion(i: str, doc: str, tipo: str) -> Seccion:
    return Seccion(id=i, doc_id=doc, tipo_doc=tipo, nivel="articulo", identificador=i, ruta=[], texto_literal=f"Texto literal de {i} " * 20,
                   pagina_inicio=3, pagina_fin=3, seccionado_incierto=False, estrategia="patron", es_hoja=True)


def par(i: int) -> Par:
    return Par(id=f"P{i}", articulo_id="A1", seccion_id="M1", origen={"v1"}, score_v1=0.61)


class Palanca(Observador):
    def __init__(self):
        self.cancela = False

    def cancelado(self) -> bool:
        return self.cancela


@pytest.fixture
def llamada_lenta(monkeypatch):
    """`juzgar_par` que tarda hasta que el test suelta el evento (o 10 s). Devuelve (evento, lista de pares que arrancaron)."""
    suelta, arrancaron = threading.Event(), []

    def lento(p, articulo, sec, nombres, cliente, s=settings, obs=None):
        arrancaron.append(p.id)
        suelta.wait(10)
        obs.espera(p, 20, 1, 6)                    # lo que haría el juez real si le llega un 429 ya tarde
        p.veredicto = Veredicto(naturaleza_articulo="obligacion", cobertura="total", cita_norma="x", comentario="c", confianza=0.9)
        return p

    monkeypatch.setattr(juez, "juzgar_par", lento)
    yield suelta, arrancaron
    suelta.set()                                   # que los hilos no retengan el cierre de pytest


def test_cancelar_con_todos_los_pares_en_vuelo_corta_en_menos_de_2_s(llamada_lenta):
    suelta, arrancaron = llamada_lenta
    palanca = Palanca()
    pares = [par(1), par(2)]
    secciones = {"A1": seccion("A1", "D1", "normativa"), "M1": seccion("M1", "D2", "manual_control")}
    threading.Timer(0.5, lambda: setattr(palanca, "cancela", True)).start()
    t0 = time.perf_counter()
    with pytest.raises(Cancelado):
        asyncio.run(juzgar_pares(pares, secciones, {}, None, DOS, obs=palanca))
    segundos = time.perf_counter() - t0
    print(f"\nsegundos hasta Cancelado con 2 pares en vuelo: {segundos:.2f}")
    assert segundos < 2 and sorted(arrancaron) == ["P1", "P2"] and all(p.veredicto is None for p in pares)


def test_ningun_par_nuevo_se_lanza_tras_cancelar(llamada_lenta):
    suelta, arrancaron = llamada_lenta
    palanca = Palanca()
    pares = [par(i) for i in range(5)]
    secciones = {"A1": seccion("A1", "D1", "normativa"), "M1": seccion("M1", "D2", "manual_control")}
    threading.Timer(0.3, lambda: setattr(palanca, "cancela", True)).start()
    with pytest.raises(Cancelado):
        asyncio.run(juzgar_pares(pares, secciones, {}, None, DOS, obs=palanca))
    suelta.set()
    time.sleep(0.3)                                # los hilos huérfanos terminan; no deben arrancar otros
    assert len(arrancaron) == 2


# --- end to end por `comparar` (ejemplo precargado, sin Docling ni modelos) ---

@pytest.fixture
def comparacion(monkeypatch):
    s = sesiones.crear()
    servicio.cargar_ejemplo(s)
    todas = s.secciones()
    art = next(i for i, x in todas.items() if x.tipo_doc == "normativa" and x.es_hoja)
    sec = next(i for i, x in todas.items() if x.tipo_doc == "manual_control" and x.es_hoja)
    pares = [Par(id=f"P{i}", articulo_id=art, seccion_id=sec, origen={"v1"}, score_v1=0.6) for i in (1, 2)]
    monkeypatch.setattr(servicio, "asegurar_indices", lambda *a, **k: None)         # los embeddings no importan para la mecánica de cancelar
    monkeypatch.setattr(servicio, "construir_pares", lambda *a, **k: (pares, {}))
    monkeypatch.setattr(ajustes, "efectivos", lambda sesion, s_=settings: DOS)
    yield s, art, sec
    sesiones.reiniciar(s.id)


def esperar(cond, tope=5.0):
    t0 = time.perf_counter()
    while not cond() and time.perf_counter() - t0 < tope:
        time.sleep(0.05)
    return time.perf_counter() - t0


def test_cancelar_la_comparacion_con_pares_en_vuelo_la_deja_cancelada_en_segundos_y_lo_tardio_se_descarta(comparacion, llamada_lenta):
    s, art, sec = comparacion
    suelta, arrancaron = llamada_lenta
    job = servicio.comparar(s, [art], [sec], cliente=None)
    comp = s.comparaciones[job.comparacion_id]
    esperar(lambda: len(arrancaron) == 2)
    time.sleep(0.05)                               # que ningún avance de los pares caiga después de esta marca de tiempo
    antes_de_cancelar = time.time()
    servicio.cancelar(s, job.job_id)
    t0 = time.perf_counter()
    tardo = esperar(lambda: job.estado == "cancelado")
    print(f"\nsegundos desde Cancelar hasta estado cancelado: {time.perf_counter() - t0:.2f}")
    assert job.estado == "cancelado" and tardo < 2 and comp.out.estado == "cancelado" and comp.entrada is None
    assert job.ultimo_evento_ts >= antes_de_cancelar     # el reloj de la pantalla se congela al cancelar, no en el último avance
    assert job.pares_en_curso == [] and not job.espera_limite.activa
    suelta.set()                                   # los hilos huérfanos terminan tarde, con resultado y un aviso de espera
    esperar(lambda: not any(t.name.startswith("juez") for t in threading.enumerate()))
    assert job.estado == "cancelado" and comp.out.estado == "cancelado" and comp.entrada is None
    assert job.pares_hechos == 0 and job.conteo_cobertura == {} and job.ultimos_veredictos == [] and not job.espera_limite.activa


def test_cancelar_despues_del_juicio_y_antes_de_armar_el_papel(comparacion, monkeypatch):
    s, art, sec = comparacion

    async def juicio_que_termina_y_cancelan(pares, *a, **k):
        servicio.cancelar(s, next(iter(s.jobs)))   # la cancelación llega justo al terminar el juicio
        return pares

    armo = []
    monkeypatch.setattr(servicio, "juzgar_pares", juicio_que_termina_y_cancelan)
    monkeypatch.setattr(servicio, "marca_articulo", lambda *a, **k: armo.append(1))      # si llegara a armar filas, esto lo delata
    job = servicio.comparar(s, [art], [sec], cliente=None)
    comp = s.comparaciones[job.comparacion_id]
    esperar(lambda: job.estado in ("cancelado", "listo", "error"))
    assert job.estado == "cancelado" and comp.out.estado == "cancelado" and comp.entrada is None and armo == []


def test_cancelar_dos_veces_es_idempotente_y_un_job_terminado_no_cambia():
    s = sesiones.crear()
    try:
        job = JobOut(job_id="J1", tipo="comparacion", estado="en_curso")
        s.jobs["J1"] = job
        servicio.cancelar(s, "J1"); servicio.cancelar(s, "J1")
        assert s.cancelados == {"J1"} and not job.cancelable and job.etapa.startswith("Cancelando")
        listo = JobOut(job_id="J2", tipo="comparacion", estado="listo", etapa="Comparación lista")
        s.jobs["J2"] = listo
        antes = listo.model_copy()
        assert servicio.cancelar(s, "J2") == antes and "J2" not in s.cancelados
    finally:
        sesiones.reiniciar(s.id)


def test_el_observador_cerrado_ignora_eventos_tardios():
    s = sesiones.crear()
    try:
        job = JobOut(job_id="J1", tipo="comparacion", estado="cancelado")
        todas = {"A1": seccion("A1", "D1", "normativa"), "M1": seccion("M1", "D2", "manual_control")}
        o = servicio._ObsJob(job, s, todas, {})
        o.cerrar()
        p = par(1)
        o.empieza(p); o.espera(p, 20, 1, 6); o.termina(p, 1, 2); o.reanuda(p)
        assert job.pares_en_curso == [] and job.pares_hechos == 0 and job.conteo_cobertura == {} and not job.espera_limite.activa
    finally:
        sesiones.reiniciar(s.id)


def test_sin_cancelar_el_juez_termina_normal_y_un_error_de_un_par_sube_sin_colgarse(monkeypatch):
    from backend.core.errors import LLMUnavailableError

    secciones = {"A1": seccion("A1", "D1", "normativa"), "M1": seccion("M1", "D2", "manual_control")}
    monkeypatch.setattr(juez, "juzgar_par", lambda p, *a, **k: p)
    hechos = []
    asyncio.run(juzgar_pares([par(1), par(2), par(3)], secciones, {}, None, DOS, progreso=lambda h, t: hechos.append(h)))
    assert hechos == [1, 2, 3]

    def cae(p, *a, **k):
        raise LLMUnavailableError("proveedor caído")

    monkeypatch.setattr(juez, "juzgar_par", cae)
    t0 = time.perf_counter()
    with pytest.raises(LLMUnavailableError):
        asyncio.run(juzgar_pares([par(1), par(2)], secciones, {}, None, DOS))
    assert time.perf_counter() - t0 < 2
