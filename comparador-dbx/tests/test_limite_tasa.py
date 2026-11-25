"""Límite de tasa del proveedor (P-36/P-04, hallado el 25 nov 2026 con Groq real): la comparación de 134 pares con 6 en paralelo chocó 98 veces con el
límite por minuto; un par agotó sus 6 intentos mientras los demás avanzaban y tumbó la comparación entera, sin resultado.

Deterministas: el modelo se reemplaza por un cliente que falla como lo hace Groq (mismo texto del error) y `_dormir` no duerme."""
import math
import time

import pytest

from backend.core.errors import LLMUnavailableError
from backend.engine import juez
from backend.engine.juez import Observador, espera_sugerida, juzgar_par
from backend.models import Par, Seccion, Veredicto
from l3_ayudas import cfg

C = cfg(LLM_INTENTOS_LIMITE=3, LLM_ESPERA_LIMITE_S=20)
TEXTO = "El área de tesorería concilia diariamente los saldos de caja."
MENSAJE_GROQ = "Error code: 429 - {'error': {'message': 'Rate limit reached for model `m` ... tokens per minute (TPM): Limit 8000 ... Please try again in %s. Need more tokens?'}}"
OK = Veredicto(naturaleza_articulo="obligacion", cobertura="parcial", cita_norma="concilia diariamente los saldos", cita_manual=None,
               comentario="c", elementos_faltantes=[], confianza=0.8)


def seccion(i: str) -> Seccion:
    return Seccion(id=i, doc_id="D", tipo_doc="normativa", nivel="articulo", identificador=i, ruta=["T", i], texto_literal=TEXTO,
                   pagina_inicio=1, pagina_fin=1, seccionado_incierto=False, estrategia="patron", es_hoja=True)


class Falla429:
    """Falla `fallos` veces con el 429 de Groq y después devuelve el veredicto. `sugerencia=None`: el proveedor no dice cuánto esperar."""

    def __init__(self, fallos: int, sugerencia: str | None = "8.1075s"):
        self.fallos, self.llamadas, self.sugerencia = fallos, 0, sugerencia

    def chat_json(self, sistema, usuario, modelo):
        self.llamadas += 1
        if self.llamadas <= self.fallos:
            raise LLMUnavailableError(MENSAJE_GROQ % self.sugerencia if self.sugerencia else "Error code: 429 - rate limit")
        return OK


class ConAvance(Observador):
    """Observador que dice si los demás pares avanzan y guarda cuánto esperó este."""

    def __init__(self, avanza: bool):
        self.avanza, self.esperas = avanza, []

    def espera(self, par, segundos, intento, maximo):
        self.esperas.append((segundos, intento, maximo))

    def avance_reciente(self, segundos):
        return self.avanza


@pytest.fixture(autouse=True)
def sin_dormir(monkeypatch):
    dormidos = []
    monkeypatch.setattr(juez, "_dormir", lambda segundos, obs: dormidos.append(segundos))
    return dormidos


def juzgar(cliente, obs=None):
    return juzgar_par(Par(id="P1", articulo_id="A", seccion_id="M", origen={"v1"}, score_v1=0.5), seccion("A"), seccion("M"), {}, cliente, C, obs)


# --- la espera que sugiere el proveedor ---

@pytest.mark.parametrize("texto,esperado", [("Please try again in 8.1075s.", 8.1075), ("try again in 1m30.5s. Need more", 90.5),
                                            ("try again in 250ms", 0.25), ("try again in 2h1m", 7260.0), ("rate limit sin dato", None), ("", None)])
def test_espera_sugerida_lee_el_formato_de_groq(texto, esperado):
    assert espera_sugerida(Exception(texto)) == esperado


def test_usa_la_espera_que_sugiere_el_proveedor_en_vez_de_20_segundos_a_ciegas(sin_dormir):
    juzgar(Falla429(fallos=1, sugerencia="8.1075s"))
    assert sin_dormir == [math.ceil(8.1075) + 1]               # 10 s, no 20


def test_sin_sugerencia_vuelve_a_la_espera_creciente_de_siempre(sin_dormir):
    juzgar(Falla429(fallos=2, sugerencia=None))
    assert sin_dormir == [20, 40]


def test_una_sugerencia_mayor_que_el_maximo_aborta_sin_esperar(sin_dormir):
    """El límite diario de Groq pide 5-8 min: esperar 120 s y reintentar no sirve, el par aborta ya (aunque los demás avancen)."""
    cliente = Falla429(fallos=10**6, sugerencia="8m36.672s")
    with pytest.raises(LLMUnavailableError):
        juzgar(cliente, ConAvance(avanza=True))
    assert cliente.llamadas == 1 and sin_dormir == []


def test_una_sugerencia_exacta_al_maximo_todavia_espera(sin_dormir):
    juzgar(Falla429(fallos=1, sugerencia="1m"))                 # tope = 3 × 20 = 60 s
    assert sin_dormir == [C.LLM_ESPERA_LIMITE_S * C.LLM_INTENTOS_LIMITE]


def test_un_numero_gigante_en_el_mensaje_no_desborda_y_aborta_como_error_del_servicio():
    cliente = Falla429(fallos=1, sugerencia="9" * 400 + "s")      # float('inf'): math.ceil(inf) lanzaría OverflowError
    with pytest.raises(LLMUnavailableError):
        juzgar(cliente)


def test_una_sugerencia_de_milisegundos_no_deja_una_espera_de_cero(sin_dormir):
    juzgar(Falla429(fallos=1, sugerencia="250ms"))
    assert sin_dormir[0] >= 2


# --- agotar los intentos ---

def test_si_nadie_avanza_agotar_los_intentos_sigue_abortando_como_antes():
    cliente = Falla429(fallos=99)
    with pytest.raises(LLMUnavailableError):
        juzgar(cliente)                                        # observador por defecto: no sabe de otros pares
    assert cliente.llamadas == C.LLM_INTENTOS_LIMITE


def test_si_los_demas_pares_avanzan_el_par_espera_su_turno_en_vez_de_tumbar_la_comparacion():
    cliente, obs = Falla429(fallos=C.LLM_INTENTOS_LIMITE + 2), ConAvance(avanza=True)
    par = juzgar(cliente, obs)
    assert par.veredicto is not None and cliente.llamadas == C.LLM_INTENTOS_LIMITE + 3
    assert [i for _, i, _ in obs.esperas] == [1, 2, 1, 2, 1]   # al agotar los 3 intentos la cuenta empieza otra vez (la espera vuelve a ser la corta)


def test_la_espera_por_turno_tiene_un_tope_de_vueltas():
    cliente = Falla429(fallos=10**6)
    with pytest.raises(LLMUnavailableError):
        juzgar(cliente, ConAvance(avanza=True))
    assert cliente.llamadas == C.LLM_INTENTOS_LIMITE + C.LLM_VUELTAS_LIMITE * (C.LLM_INTENTOS_LIMITE - 1)     # 1.ª ronda completa + (intentos-1) por vuelta


def test_si_dejan_de_avanzar_a_mitad_de_la_espera_se_aborta():
    class DejaDeAvanzar(ConAvance):
        def avance_reciente(self, segundos):
            return len(self.esperas) < 4

    cliente = Falla429(fallos=10**6)
    with pytest.raises(LLMUnavailableError):
        juzgar(cliente, DejaDeAvanzar(avanza=True))
    assert cliente.llamadas < C.LLM_INTENTOS_LIMITE + C.LLM_VUELTAS_LIMITE * (C.LLM_INTENTOS_LIMITE - 1)


def test_un_error_que_no_es_limite_de_tasa_aborta_sin_esperar(sin_dormir):
    class Cae:
        llamadas = 0

        def chat_json(self, *a):
            self.llamadas += 1
            raise LLMUnavailableError("Error code: 401 - invalid api key")

    cliente = Cae()
    with pytest.raises(LLMUnavailableError):
        juzgar(cliente, ConAvance(avanza=True))                # aunque los demás avancen, una clave inválida no se reintenta
    assert cliente.llamadas == 1 and sin_dormir == []


# --- el observador real del trabajo ---

def test_el_observador_del_trabajo_cuenta_como_avance_un_par_resuelto_y_olvida_el_pasado():
    from backend.api.schemas import JobOut
    from backend.core import sesiones
    from backend.engine import servicio

    s = sesiones.crear()
    try:
        job = JobOut(job_id="J", tipo="comparacion", estado="en_curso")
        todas = {"A": seccion("A"), "M": seccion("M")}
        o = servicio._ObsJob(job, s, todas, {"D": "Doc"})
        assert o.avance_reciente(5)                            # recién arrancado: aún no hay por qué abortar
        o._ultimo_par = time.monotonic() - 100
        assert not o.avance_reciente(60)                       # 100 s sin ningún par resuelto: nadie avanza
        p = Par(id="P1", articulo_id="A", seccion_id="M", origen={"v1"}, score_v1=0.5)
        o.empieza(p)
        juzgar_par(p, todas["A"], todas["M"], {}, Falla429(fallos=0), C)
        o.termina(p, 1, 10)
        assert o.avance_reciente(60)                           # resolver un par cuenta como avance
        o.cerrar()
    finally:
        sesiones.reiniciar(s.id)
