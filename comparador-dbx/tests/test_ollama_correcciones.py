"""Revisión de las correcciones QA-O1 a QA-O4 del turno de Ollama (QA, 25 nov 2026): cancelación en la cola, el cupo si `cancelado()` falla, el tope de espera
frente a `LLM_CONCURRENCY` y los hilos huérfanos tras una caída (no una cancelación). Mismo criterio que `test_ollama_huecos.py`: solo se reemplaza el transporte del SDK."""
import asyncio
import threading
import time

import pytest

from backend.core.errors import LLMUnavailableError
from backend.engine import juez
from backend.engine.juez import Cancelado, juzgar_par, juzgar_pares
from backend.llm.client import CANCELADO_POR, TurnoCancelado
from tests.test_ollama_huecos import CORTO, SECCIONES, VEREDICTO, armar, en_hilos, esperar, falso, juez_con_ollama_lento
from backend.engine.juez import Observador
from tests.test_cancelar_comparacion import Palanca, par


def cupo_libre(mc) -> bool:
    ok = mc._cupos["ollama"].acquire(blocking=False)
    if ok:
        mc._cupos["ollama"].release()
    return ok


def con_cancelado(funcion):
    """Pone `CANCELADO_POR` como lo hace el juez y lo deja como estaba."""
    token = CANCELADO_POR.set(funcion)
    return token


# --- cancelación en la cola ---

def test_si_se_cancela_justo_al_obtener_el_turno_no_se_llama_al_modelo_y_el_cupo_queda_libre(monkeypatch):
    llamadas = []
    mc = armar(monkeypatch, {"ollama": falso("ollama", llamadas=llamadas)}, LLM_PROVIDER="ollama", LLM_FALLBACK="")
    token = con_cancelado(lambda: True)
    try:
        with pytest.raises(TurnoCancelado):
            mc._completar(CORTO)
    finally:
        CANCELADO_POR.reset(token)
    assert llamadas == [] and cupo_libre(mc) and mc._caidos == {} and mc.usos["ollama"] == 0


def test_un_turno_cancelado_con_ollama_en_medio_no_lo_marca_caido_ni_pasa_al_siguiente_proveedor(monkeypatch):
    llamadas = []
    c = {"groq": falso("groq", falla=ConnectionError("x")), "ollama": falso("ollama", llamadas=llamadas), "databricks": falso("databricks", llamadas=llamadas)}
    mc = armar(monkeypatch, c, LLM_FALLBACK="ollama,databricks")
    token = con_cancelado(lambda: True)
    try:
        with pytest.raises(TurnoCancelado):
            mc._completar(CORTO)
    finally:
        CANCELADO_POR.reset(token)
    assert llamadas == [] and set(mc._caidos) == {"groq"}                           # cancelar no es una caída de Ollama


def test_un_hilo_en_cola_se_retira_en_menos_de_dos_segundos_al_cancelar_sin_esperar_su_turno(monkeypatch):
    mc = armar(monkeypatch, {"ollama": falso("ollama", demora=6)}, LLM_PROVIDER="ollama", LLM_FALLBACK="")
    palanca = Palanca()
    errores = []

    def en_cola():
        CANCELADO_POR.set(palanca.cancelado)
        try:
            mc._completar(CORTO)
        except TurnoCancelado as e:
            errores.append((e, time.perf_counter()))

    ocupa = threading.Thread(target=mc._completar, args=(CORTO,), daemon=True)
    ocupa.start()
    assert esperar(lambda: not cupo_libre(mc))                                       # el primero tiene el cupo y tarda 6 s
    espera = threading.Thread(target=en_cola)
    espera.start()
    time.sleep(0.2)
    t0 = time.perf_counter()
    palanca.cancela = True
    espera.join(5)
    assert errores and errores[0][1] - t0 < 2.0                                       # la cola mira cada segundo


def test_juzgar_par_convierte_el_turno_cancelado_en_cancelado_y_limpia_la_variable(monkeypatch):
    mc = armar(monkeypatch, {"ollama": falso("ollama", contenido=VEREDICTO)}, LLM_PROVIDER="ollama", LLM_FALLBACK="")
    palanca = Palanca()
    palanca.cancela = True
    with pytest.raises(Cancelado):
        juzgar_par(par(1), SECCIONES["A1"], SECCIONES["M1"], {}, mc, mc.s, obs=palanca)
    assert CANCELADO_POR.get() is None and cupo_libre(mc)                              # no queda la función del juez pegada al hilo


def test_juzgar_par_limpia_la_variable_tambien_si_el_juicio_falla(monkeypatch):
    mc = armar(monkeypatch, {"ollama": falso("ollama", falla=ConnectionError("x"))}, LLM_PROVIDER="ollama", LLM_FALLBACK="")
    with pytest.raises(LLMUnavailableError):
        juzgar_par(par(1), SECCIONES["A1"], SECCIONES["M1"], {}, mc, mc.s)
    assert CANCELADO_POR.get() is None


def test_sin_juez_nadie_cancela_y_el_turno_se_comporta_como_antes(monkeypatch):
    """El clasificador, el borrador y el ping no ponen `CANCELADO_POR`: la variable es `None` y no se rompe nada."""
    mc = armar(monkeypatch, {"ollama": falso("ollama")}, LLM_PROVIDER="ollama", LLM_FALLBACK="")
    assert CANCELADO_POR.get() is None and '"ollama"' in mc._completar(CORTO)


# --- el cupo si `cancelado()` falla ---

# QA-O5 (corregido el 25 nov 2026): el cupo se libera aunque falle la consulta de cancelación.
def test_si_cancelado_lanza_al_obtener_el_turno_el_cupo_no_se_pierde(monkeypatch):
    mc = armar(monkeypatch, {"ollama": falso("ollama")}, LLM_PROVIDER="ollama", LLM_FALLBACK="", OLLAMA_TIMEOUT_S=0.3, LLM_CONCURRENCY=1)

    def roto():
        raise RuntimeError("fallo del observador")

    token = con_cancelado(roto)
    try:
        with pytest.raises(Exception):
            mc._completar(CORTO)
    finally:
        CANCELADO_POR.reset(token)
    assert cupo_libre(mc)


def test_si_cancelado_lanza_mientras_espera_el_cupo_del_que_habla_no_se_toca(monkeypatch):
    mc = armar(monkeypatch, {"ollama": falso("ollama", demora=1.3)}, LLM_PROVIDER="ollama", LLM_FALLBACK="")
    ocupa = threading.Thread(target=mc._completar, args=(CORTO,), daemon=True)
    ocupa.start()
    assert esperar(lambda: not cupo_libre(mc))

    def roto():
        raise RuntimeError("fallo del observador")

    token = con_cancelado(roto)
    try:
        with pytest.raises(Exception):
            mc._completar(CORTO)
    finally:
        CANCELADO_POR.reset(token)
    ocupa.join(5)
    assert cupo_libre(mc)                                                              # el que hablaba soltó su cupo, el que falló no soltó uno ajeno


# --- el tope de espera frente a LLM_CONCURRENCY ---

def tiempo_hasta_agotar_el_turno(monkeypatch, **cambios) -> float:
    """Un hilo ocupa el cupo 5 s; otro pide turno y mide cuánto tarda en rendirse."""
    mc = armar(monkeypatch, {"ollama": falso("ollama", demora=5)}, LLM_PROVIDER="ollama", LLM_FALLBACK="", **cambios)
    threading.Thread(target=mc._completar, args=(CORTO,), daemon=True).start()
    assert esperar(lambda: not cupo_libre(mc))
    t0 = time.perf_counter()
    with pytest.raises(LLMUnavailableError, match="turno"):
        mc._completar(CORTO)
    return time.perf_counter() - t0


@pytest.mark.parametrize("hilos,esperado", [(1, 0.3), (3, 0.9)])
def test_el_tope_de_espera_es_el_timeout_por_los_hilos_del_juez(monkeypatch, hilos, esperado):
    t = tiempo_hasta_agotar_el_turno(monkeypatch, OLLAMA_TIMEOUT_S=0.3, LLM_CONCURRENCY=hilos)
    assert esperado - 0.05 <= t <= esperado + 0.6


@pytest.mark.parametrize("hilos", [0, -4])
def test_con_llm_concurrency_en_cero_o_negativa_el_tope_no_se_anula(monkeypatch, hilos):
    t = tiempo_hasta_agotar_el_turno(monkeypatch, OLLAMA_TIMEOUT_S=0.3, LLM_CONCURRENCY=hilos)
    assert 0.25 <= t <= 1.0                                                            # `max(1, …)`: un hilo, no cero ni negativo


def test_el_tope_usa_el_ajuste_no_los_hilos_reales_y_con_pocos_pares_la_espera_teorica_es_la_del_ajuste(monkeypatch):
    """Caracterización: con `LLM_CONCURRENCY=6` y un solo hilo en cola, esperaría 6 × `OLLAMA_TIMEOUT_S` (1 800 s con los valores por defecto)
    aunque no haya nadie más delante; a escala: 6 × 0,2 s."""
    t = tiempo_hasta_agotar_el_turno(monkeypatch, OLLAMA_TIMEOUT_S=0.2, LLM_CONCURRENCY=6)
    assert 1.1 <= t <= 1.9


# --- huérfanos tras una CAÍDA (no una cancelación) ---

@pytest.mark.parametrize("pares", [4, 6])
def test_tras_abortar_por_una_caida_los_hilos_en_cola_se_retiran_sin_llamar_al_modelo_caido(monkeypatch, pares):
    """QA-O6 (acotado por `_ConAborto`): queda una llamada de más como máximo, la del hilo que ya tenía el turno cuando el primero falló (carrera inevitable:
    el evento de aborto se activa cuando el error llega al bucle de asyncio). Los demás hilos en cola se retiran sin llamar."""
    llamadas = []
    mc = armar(monkeypatch, {"ollama": falso("ollama", demora=0.15, falla=ConnectionError("cayó"), llamadas=llamadas)}, LLM_PROVIDER="ollama", LLM_FALLBACK="", LLM_CONCURRENCY=pares)
    with pytest.raises(LLMUnavailableError):
        asyncio.run(juzgar_pares([par(i) for i in range(pares)], SECCIONES, {}, mc, mc.s))
    assert esperar(lambda: juez.llamadas_vivas() == 0, limite=5)
    assert len(llamadas) <= 2, f"llamadas a Ollama: {len(llamadas)} ({pares} pares, cupo 1)"
    assert cupo_libre(mc)


def test_el_observador_de_los_hilos_delega_todo_y_solo_anade_el_aborto():
    """`_ConAborto` debe reenviar los seis eventos del observador del trabajo; si `Observador` gana un método y no se reenvía, el progreso en vivo se pierde en silencio."""
    eventos = []

    class Registro(Observador):
        def empieza(self, par): eventos.append("empieza")
        def espera(self, par, segundos, intento, maximo): eventos.append("espera")
        def reanuda(self, par): eventos.append("reanuda")
        def termina(self, par, hechos, total): eventos.append("termina")
        def avance_reciente(self, segundos): return True

    evento = threading.Event()
    o = juez._ConAborto(Registro(), evento)
    o.empieza(None); o.espera(None, 1, 1, 6); o.reanuda(None); o.termina(None, 1, 1)
    assert eventos == ["empieza", "espera", "reanuda", "termina"] and o.avance_reciente(1.0) is True
    assert o.cancelado() is False
    evento.set()
    assert o.cancelado() is True
    publicos = {n for n in vars(Observador) if not n.startswith("_")}
    assert publicos <= set(vars(juez._ConAborto)), f"métodos sin reenviar: {publicos - set(vars(juez._ConAborto))}"


def test_si_el_trabajo_ya_estaba_cancelado_el_observador_de_los_hilos_tambien_lo_esta():
    palanca = Palanca()
    palanca.cancela = True
    assert juez._ConAborto(palanca, threading.Event()).cancelado() is True
