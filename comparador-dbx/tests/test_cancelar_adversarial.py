"""Cancelar una comparación: casos adversariales (23 nov 2026). Deterministas: ningún modelo interviene.

Igual que tests/test_cancelar_comparacion.py: solo se sustituye `juzgar_par` por una función que espera, para probar la mecánica de
concurrencia (hilos, vigía, cierre del observador), no el juicio."""
import asyncio
import threading
import time

import pytest

from backend.core import sesiones
from backend.core.errors import LLMUnavailableError
from backend.engine import juez, servicio
from backend.engine.juez import Cancelado, juzgar_pares
from backend.models import Veredicto
from tests.test_cancelar_comparacion import DOS, Palanca, comparacion, esperar, llamada_lenta, par, seccion  # noqa: F401

SECCIONES = {"A1": seccion("A1", "D1", "normativa"), "M1": seccion("M1", "D2", "manual_control")}


def hilos_juez() -> int:
    return sum(t.name.startswith("juez") for t in threading.enumerate())


def veredicto() -> Veredicto:
    return Veredicto(naturaleza_articulo="obligacion", cobertura="total", cita_norma="x", comentario="c", confianza=0.9)


# --- cancelar y error del proveedor a la vez ---

def test_cancelar_y_caida_del_proveedor_a_la_vez_sube_una_de_las_dos_sin_colgarse(monkeypatch):
    palanca = Palanca()

    def cae_y_cancelan(p, *a, **k):
        palanca.cancela = True
        raise LLMUnavailableError("proveedor caído")

    monkeypatch.setattr(juez, "juzgar_par", cae_y_cancelan)
    t0 = time.perf_counter()
    with pytest.raises((Cancelado, LLMUnavailableError)):
        asyncio.run(juzgar_pares([par(1), par(2), par(3)], SECCIONES, {}, None, DOS, obs=palanca))
    assert time.perf_counter() - t0 < 2


def test_comparar_con_caida_y_cancelacion_simultaneas_nunca_termina_en_listo(comparacion, monkeypatch):
    s, art, sec = comparacion

    def cae_y_cancelan(p, *a, **k):
        servicio.cancelar(s, next(iter(s.jobs)))
        raise LLMUnavailableError("proveedor caído")

    monkeypatch.setattr(juez, "juzgar_par", cae_y_cancelan)
    job = servicio.comparar(s, [art], [sec], cliente=None)
    comp = s.comparaciones[job.comparacion_id]
    esperar(lambda: job.estado in ("cancelado", "listo", "error"))
    assert job.estado in ("cancelado", "error") and comp.entrada is None and comp.out.estado == job.estado
    assert job.pares_en_curso == [] and not job.cancelable


# --- cancelar justo cuando termina el último par ---

def test_cancelar_justo_al_terminar_el_ultimo_par_descarta_el_resultado(monkeypatch):
    palanca, hechos = Palanca(), []

    def termina_y_cancelan(p, *a, **k):
        p.veredicto = veredicto()
        palanca.cancela = True                     # el clic llega mientras vuelve la última llamada
        return p

    monkeypatch.setattr(juez, "juzgar_par", termina_y_cancelan)
    with pytest.raises(Cancelado):
        asyncio.run(juzgar_pares([par(1)], SECCIONES, {}, None, DOS, progreso=lambda h, t: hechos.append(h), obs=palanca))
    assert hechos == []                            # el par tardío no se cuenta como hecho


def test_comparar_cancelada_justo_al_terminar_el_ultimo_par_no_queda_lista(comparacion, monkeypatch):
    s, art, sec = comparacion

    def termina_y_cancelan(p, *a, **k):
        p.veredicto = veredicto()
        servicio.cancelar(s, next(iter(s.jobs)))
        return p

    monkeypatch.setattr(juez, "juzgar_par", termina_y_cancelan)
    job = servicio.comparar(s, [art], [sec], cliente=None)
    comp = s.comparaciones[job.comparacion_id]
    esperar(lambda: job.estado in ("cancelado", "listo", "error"))
    assert job.estado == "cancelado" and comp.out.estado == "cancelado" and comp.entrada is None
    assert job.pares_hechos == 0 and job.conteo_cobertura == {} and job.ultimos_veredictos == []


# --- cancelar durante asegurar_indices ---

def test_cancelar_durante_asegurar_indices_corta_en_el_siguiente_lote_y_no_juzga(comparacion, monkeypatch):
    s, art, sec = comparacion
    lotes, juzgo = [], []

    def indices_en_lotes(sesion, cliente, progreso):
        for h in (1, 2, 3):
            lotes.append(h)
            if h == 2:
                servicio.cancelar(sesion, next(iter(sesion.jobs)))     # el clic llega a mitad de los embeddings
            progreso(h, 3)

    async def no_debe_llamarse(*a, **k):
        juzgo.append(1)

    monkeypatch.setattr(servicio, "asegurar_indices", indices_en_lotes)
    monkeypatch.setattr(servicio, "juzgar_pares", no_debe_llamarse)
    job = servicio.comparar(s, [art], [sec], cliente=None)
    comp = s.comparaciones[job.comparacion_id]
    esperar(lambda: job.estado in ("cancelado", "listo", "error"))
    assert job.estado == "cancelado" and comp.out.estado == "cancelado" and comp.entrada is None
    assert lotes == [1, 2] and juzgo == []         # el lote 3 no se pidió ni se llegó al juez


# --- "Borrar todo" con la comparación en curso ---

def test_borrar_todo_con_pares_en_vuelo_los_hilos_huerfanos_no_tocan_la_sesion_borrada(comparacion, llamada_lenta):
    s, art, sec = comparacion
    suelta, arrancaron = llamada_lenta
    job = servicio.comparar(s, [art], [sec], cliente=None)
    comp = s.comparaciones[job.comparacion_id]
    esperar(lambda: len(arrancaron) == 2)
    with s.lock:                                   # lo mismo que hace DELETE /session
        s.cerrada = True
        activo = sesiones.trabajo_activo(s)
    servicio.cancelar(s, activo["id"])
    sesiones.reiniciar(s.id)
    esperar(lambda: job.estado == "cancelado")
    assert job.estado == "cancelado" and not s.dir.exists() and sesiones.existente(s.id) is None
    suelta.set()                                   # los hilos huérfanos terminan con la sesión ya borrada
    esperar(lambda: hilos_juez() == 0)
    assert hilos_juez() == 0 and not s.dir.exists()
    assert job.estado == "cancelado" and comp.entrada is None and job.pares_hechos == 0
    assert job.pares_en_curso == [] and job.ultimos_veredictos == [] and not job.espera_limite.activa
    with pytest.raises(sesiones.SesionPerdida):
        sesiones.obtener(s.id)


def test_con_la_sesion_cerrada_no_se_acepta_otra_comparacion(comparacion):
    s, art, sec = comparacion
    with s.lock:
        s.cerrada = True
    with pytest.raises(sesiones.SesionPerdida):
        servicio.comparar(s, [art], [sec], cliente=None)


# --- cancelar y recomparar muchas veces: los hilos no se acumulan ---

def test_cancelar_y_recomparar_varias_veces_no_acumula_hilos_tras_terminar_las_llamadas(comparacion, llamada_lenta):
    """Con el tope de llamadas vivas (ERR-CMP-008), recomparar mientras las huérfanas siguen en vuelo se rechaza; al terminar ellas, se puede."""
    s, art, sec = comparacion
    suelta, arrancaron = llamada_lenta
    antes, ciclos = hilos_juez(), 5                # 5 ciclos > los 2 hilos de la cola de comparaciones: si Cancelar no liberara la cola, el 3.º se colgaría
    for i in range(ciclos):
        suelta.clear()
        job = servicio.comparar(s, [art], [sec], cliente=None)
        esperar(lambda: len(arrancaron) == 2 * (i + 1))
        servicio.cancelar(s, job.job_id)
        esperar(lambda: job.estado == "cancelado")
        assert job.estado == "cancelado", f"ciclo {i + 1}: la cola de comparaciones quedó ocupada"
        with pytest.raises(servicio.ComparacionError) as e:          # las 2 llamadas huérfanas siguen vivas: no se apilan más
            servicio.comparar(s, [art], [sec], cliente=None)
        assert e.value.codigo == "ERR-CMP-008" and e.value.estado_http == 409
        assert hilos_juez() - antes <= DOS.LLM_CONCURRENCY           # crecimiento acotado: a lo más la concurrencia
        suelta.set()
        esperar(lambda: hilos_juez() == antes and juez.llamadas_vivas() == 0)
        assert hilos_juez() == antes and juez.llamadas_vivas() == 0
    # tras recuperar, una comparación nueva (llamadas rápidas) debe terminar normal
    suelta.set()
    job = servicio.comparar(s, [art], [sec], cliente=None)
    esperar(lambda: job.estado in ("cancelado", "listo", "error"), 10)
    assert job.estado != "en_curso"


# --- tiempos con llamadas de 5 s ---

def test_cancelar_con_llamadas_de_5_s_deja_cancelado_en_menos_de_2_s(comparacion, monkeypatch):
    s, art, sec = comparacion
    arrancaron = []

    def llamada_de_5_s(p, *a, **k):
        arrancaron.append(p.id)
        time.sleep(5)
        return p

    monkeypatch.setattr(juez, "juzgar_par", llamada_de_5_s)
    job = servicio.comparar(s, [art], [sec], cliente=None)
    esperar(lambda: len(arrancaron) == 2)
    servicio.cancelar(s, job.job_id)
    t0 = time.perf_counter()
    esperar(lambda: job.estado == "cancelado")
    segundos = time.perf_counter() - t0
    print(f"\nsegundos desde Cancelar hasta estado cancelado (llamadas de 5 s): {segundos:.2f}")
    assert job.estado == "cancelado" and segundos < 2
    esperar(lambda: hilos_juez() == 0, 8)           # que no queden hilos para la prueba siguiente
