"""Huecos de `test_limite_tasa.py` (QA, 25 nov 2026): el límite de tasa con hilos reales, el observador real del trabajo y la cancelación.

Deterministas. El cliente solo reproduce el 429 de Groq (mismo texto del error) según un guion de la prueba; no imita al modelo.
`_dormir` espera 10 ms en vez de segundos, pero sigue revisando `cancelado()` como el real."""
import asyncio
import threading
import time

import pytest

from backend.api.schemas import JobOut
from backend.config import settings
from backend.core import sesiones
from backend.core.errors import LLMUnavailableError
from backend.engine import juez, servicio
from backend.engine.juez import Cancelado, Observador, espera_sugerida, juzgar_pares, juzgar_par
from backend.models import Par, Veredicto
from l3_ayudas import cfg, seccion

C = cfg(LLM_CONCURRENCY=3, LLM_INTENTOS_LIMITE=2, LLM_ESPERA_LIMITE_S=1)      # ventana de avance = 2 s
TEXTO = "El área de tesorería concilia diariamente los saldos de caja."
GROQ = "Error code: 429 - {'error': {'message': 'Rate limit reached ... Please try again in 0.5s. Need more tokens?'}}"
OK = Veredicto(naturaleza_articulo="obligacion", cobertura="parcial", cita_norma="concilia diariamente los saldos", cita_manual=None,
               comentario="c", elementos_faltantes=[], confianza=0.8)


@pytest.fixture(autouse=True)
def dormir_poco(monkeypatch):
    def dormir(segundos, obs):
        if obs.cancelado():
            raise Cancelado()
        time.sleep(0.01)
    monkeypatch.setattr(juez, "_dormir", dormir)


@pytest.fixture
def trabajo():
    """Un `_ObsJob` real (el de la comparación) con 6 pares A0..A5 contra el manual M."""
    s = sesiones.crear()
    todas = {f"A{i}": seccion(f"A{i}", TEXTO, ident=f"ART-{i}", ruta=(f"ART-{i}",)) for i in range(6)} | {"M": seccion("M", TEXTO, ident="CTRL-M")}
    pares = [Par(id=f"P{i}", articulo_id=f"A{i}", seccion_id="M", origen={"v1"}, score_v1=0.5) for i in range(6)]
    job = JobOut(job_id="J", tipo="comparacion", estado="en_curso")
    yield servicio._ObsJob(job, s, todas, {"D": "Doc"}), job, todas, pares
    sesiones.reiniciar(s.id)


class Guion:
    """Cliente con el 429 de Groq: `esperar_a` dice qué par se ve afectado (ART-0) y hasta cuándo (`libre()`); los demás pares responden bien."""

    def __init__(self, libre, mensaje=GROQ):
        self.libre, self.mensaje, self.llamadas, self.ok, self.lock = libre, mensaje, {}, 0, threading.Lock()

    def chat_json(self, sistema, usuario, modelo):
        par = "ART-0" if "ART-0" in usuario else "otro"
        with self.lock:
            self.llamadas[par] = self.llamadas.get(par, 0) + 1
            if par == "ART-0" and not self.libre(self):
                raise LLMUnavailableError(self.mensaje)
            if par == "otro":
                self.ok += 1
        return OK


def correr(pares, todas, cliente, obs):
    return asyncio.run(juzgar_pares(pares, todas, {"D": "Doc"}, cliente, C, obs=obs))


# --- concurrencia real: un par que espera su turno mientras otros avanzan ---

def test_el_par_rezagado_espera_su_turno_y_la_comparacion_termina_con_los_seis(trabajo):
    o, job, todas, pares = trabajo
    cliente = Guion(libre=lambda c: c.ok >= 5 and c.llamadas["ART-0"] > C.LLM_INTENTOS_LIMITE)    # 429 hasta que los otros cinco terminan y ART-0 agota una ronda
    correr(pares, todas, cliente, o)
    assert all(p.veredicto is not None for p in pares) and job.pares_hechos == 6
    assert cliente.llamadas["ART-0"] > C.LLM_INTENTOS_LIMITE   # agotó una ronda completa y siguió: no tumbó la comparación


def test_un_par_que_nunca_avanza_mientras_los_otros_si_aborta_tras_las_vueltas_maximas(trabajo):
    o, _, todas, pares = trabajo
    cliente = Guion(libre=lambda c: False)
    with pytest.raises(LLMUnavailableError):
        correr(pares, todas, cliente, o)
    assert cliente.llamadas["ART-0"] == C.LLM_INTENTOS_LIMITE + C.LLM_VUELTAS_LIMITE * (C.LLM_INTENTOS_LIMITE - 1)


def test_si_ningun_par_avanza_desde_hace_rato_el_primero_que_agota_intentos_aborta(trabajo):
    o, _, todas, pares = trabajo
    o._ultimo_par = time.monotonic() - 3600                    # sin progreso hace una hora (ventana de 2 s)
    cliente = Guion(libre=lambda c: False)
    with pytest.raises(LLMUnavailableError):
        correr(pares[:1], todas, cliente, o)                   # solo ART-0, que nunca recibe respuesta
    assert cliente.llamadas["ART-0"] == C.LLM_INTENTOS_LIMITE  # sin vueltas extra


def test_el_avance_se_mide_con_pares_resueltos_y_no_con_el_arranque_de_la_comparacion(trabajo):
    o, _, todas, pares = trabajo
    o._ultimo_par = time.monotonic() - 3600
    assert not o.avance_reciente(2)
    o.empieza(pares[1])
    o.termina(pares[1], 1, 6)                                  # un par resuelto reabre la ventana
    assert o.avance_reciente(2)


# --- cancelación durante la espera por turno ---

class Cancela(Observador):
    """Los demás avanzan; el auditor cancela al empezar la espera número `cuando`."""

    def __init__(self, cuando):
        self.cuando, self.esperas = cuando, 0

    def espera(self, par, segundos, intento, maximo):
        self.esperas += 1

    def avance_reciente(self, segundos):
        return True

    def cancelado(self):
        return self.esperas >= self.cuando


def test_cancelar_durante_la_espera_por_turno_corta_sin_otra_llamada_al_proveedor():
    cliente = Guion(libre=lambda c: False)
    par = Par(id="P0", articulo_id="A0", seccion_id="M", origen={"v1"}, score_v1=0.5)
    with pytest.raises(Cancelado):
        juzgar_par(par, seccion("A0", TEXTO, ident="ART-0", ruta=("ART-0",)), seccion("M", TEXTO, ident="CTRL-M"), {}, cliente, C, Cancela(cuando=3))
    assert cliente.llamadas["ART-0"] == 3                      # 2.ª ronda: 429, vuelta, espera 3 (turno) -> cancelado antes de llamar de nuevo


def test_cancelar_con_pares_esperando_turno_corta_la_comparacion_en_menos_de_2_s(trabajo, monkeypatch):
    o, _, todas, pares = trabajo
    monkeypatch.setattr(juez, "_dormir", lambda segundos, obs: (obs.cancelado() and (_ for _ in ()).throw(Cancelado())) or time.sleep(0.05))
    job_id = o.job.job_id
    cliente = Guion(libre=lambda c: False)
    threading.Timer(0.05, lambda: o.sesion.cancelados.add(job_id)).start()
    t0 = time.perf_counter()
    with pytest.raises(Cancelado):
        correr(pares, todas, cliente, o)
    assert time.perf_counter() - t0 < 2


# --- la espera visible en pantalla (espera_limite) ---

def test_la_espera_visible_nunca_muestra_un_intento_mayor_que_el_maximo(trabajo):
    o, job, todas, pares = trabajo
    vistos = []
    espera = o.espera
    o.espera = lambda p, s, i, m: (espera(p, s, i, m), vistos.append((job.espera_limite.intento, job.espera_limite.max)))
    correr(pares, todas, Guion(libre=lambda c: c.ok >= 5), o)
    assert vistos and all(1 <= i <= m for i, m in vistos)
    assert not job.espera_limite.activa                        # al terminar no queda un aviso de espera colgado


def test_la_espera_visible_sigue_activa_mientras_otro_par_aun_espera(trabajo):
    o, job, _, pares = trabajo
    o.espera(pares[0], 10, 1, 2)
    o.espera(pares[1], 30, 1, 2)
    o.reanuda(pares[0])
    assert job.espera_limite.activa
    o.reanuda(pares[1])
    assert not job.espera_limite.activa


def test_un_hilo_tardio_no_cambia_la_espera_visible_tras_cerrar_el_trabajo(trabajo):
    o, job, _, pares = trabajo
    o.cerrar()
    o.espera(pares[0], 10, 1, 2)
    assert not job.espera_limite.activa


# --- carrera entre hilos en el observador real ---

def test_avance_reciente_y_termina_desde_muchos_hilos_no_pierden_pares_ni_fallan(trabajo):
    o, job, _, _ = trabajo
    errores, n_hilos, por_hilo = [], 8, 100

    def hilo(k):
        try:
            for i in range(por_hilo):
                p = Par(id=f"H{k}-{i}", articulo_id="A1", seccion_id="M", origen={"v1"}, score_v1=0.5)
                o.empieza(p)
                o.avance_reciente(60)
                o.termina(p, k * por_hilo + i + 1, n_hilos * por_hilo)
        except Exception as e:                                 # noqa: BLE001 - se reporta abajo
            errores.append(e)

    hilos = [threading.Thread(target=hilo, args=(k,)) for k in range(n_hilos)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert errores == [] and o.seq == n_hilos * por_hilo
    assert sum(job.conteo_cobertura.values()) == n_hilos * por_hilo and job.pares_en_curso == [] and o.avance_reciente(60)


# --- valores límite de la configuración y del texto del proveedor ---

def test_un_solo_intento_configurado_con_los_demas_avanzando_espera_solo_las_vueltas_maximas():
    class Avanzan(Observador):
        def avance_reciente(self, segundos):
            return True

    cliente = Guion(libre=lambda c: False)
    par = Par(id="P0", articulo_id="A0", seccion_id="M", origen={"v1"}, score_v1=0.5)
    with pytest.raises(LLMUnavailableError):
        juzgar_par(par, seccion("A0", TEXTO, ident="ART-0", ruta=("ART-0",)), seccion("M", TEXTO, ident="CTRL-M"), {}, cliente, cfg(LLM_INTENTOS_LIMITE=1, LLM_ESPERA_LIMITE_S=1), Avanzan())
    assert cliente.llamadas["ART-0"] == 1 + settings.LLM_VUELTAS_LIMITE


def test_espera_configurada_en_cero_no_se_cuelga_ni_espera_para_siempre():
    cliente = Guion(libre=lambda c: False, mensaje="Error code: 429 - rate limit")      # sin sugerencia (con ella y tope 0 aborta al primer 429)
    par = Par(id="P0", articulo_id="A0", seccion_id="M", origen={"v1"}, score_v1=0.5)
    with pytest.raises(LLMUnavailableError):
        juzgar_par(par, seccion("A0", TEXTO, ident="ART-0", ruta=("ART-0",)), seccion("M", TEXTO, ident="CTRL-M"), {}, cliente, cfg(LLM_INTENTOS_LIMITE=2, LLM_ESPERA_LIMITE_S=0))
    assert cliente.llamadas["ART-0"] == 2                      # ventana 0: nadie "avanzó hace menos de 0 s"


@pytest.mark.parametrize("texto,esperado", [("try again in 0s", 0.0), ("try again in 0.5s", 0.5), ("try again in 1m 30s", 60.0),
                                            ("Try Again In 5s", None), ("try again in s", None), ("try again in -3s", None)])
def test_espera_sugerida_con_formatos_raros_no_falla_ni_inventa(texto, esperado):
    assert espera_sugerida(Exception(texto)) == esperado
