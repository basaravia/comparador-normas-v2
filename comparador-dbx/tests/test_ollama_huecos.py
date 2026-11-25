"""Huecos de los cuidados de Ollama (QA, 25 nov 2026): cupo bajo cancelación y con ERR-CMP-008, errores dentro del cupo, el guarda con el reintento de JSON,
Ollama primario / en medio de la cadena y la espera por turno frente a los timeouts del SDK.

Deterministas, como `test_ollama_cuidados.py`: solo se reemplaza el transporte. Dos formas:
- `falso(...)`: el objeto `chat.completions.create` del SDK (lo que se prueba es el cupo, la cadena y el guarda, no el juicio del modelo).
- `ServidorLento`: un servidor HTTP local contra el que el SDK `openai` REAL aplica su timeout y sus reintentos."""
import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from backend.core.errors import LLMOutputError, LLMUnavailableError
from backend.engine import juez
from backend.engine.juez import Cancelado, juzgar_par, juzgar_pares
from backend.llm import client
from backend.llm.client import ModelClient
from backend.models import Veredicto
from l3_ayudas import cfg
from tests.test_cancelar_comparacion import Palanca, par, seccion

CORTO = [{"role": "user", "content": "hola"}]
SECCIONES = {"A1": seccion("A1", "D1", "normativa"), "M1": seccion("M1", "D2", "manual_control")}
VEREDICTO = Veredicto(naturaleza_articulo="obligacion", cobertura="total", cita_norma="x", comentario="c", confianza=0.9).model_dump_json()


def falso(nombre, demora=0.0, falla=None, contenido=None, llamadas=None):
    """Un `chat.completions.create` del SDK que tarda `demora`, falla con `falla` o responde `contenido` (por defecto `{"de": nombre}`)."""
    def create(**kw):
        if llamadas is not None:
            llamadas.append(nombre)
        time.sleep(demora)
        if falla is not None:
            raise falla
        texto = contenido(kw) if callable(contenido) else (contenido if contenido is not None else f'{{"de": "{nombre}"}}')
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=texto))])
    return SimpleNamespace(nombre=nombre, chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def armar(monkeypatch, clientes, **cambios):
    monkeypatch.setattr(client, "crear_cliente", lambda p, s, embeddings=False: (clientes[p], f"modelo-{p}"))
    base = dict(LLM_PROVIDER="groq", LLM_FALLBACK="ollama", OLLAMA_NUM_CTX=8192, OLLAMA_RESERVA_SALIDA=1500, OLLAMA_CONCURRENCIA=1, LLM_FALLBACK_REINTENTO_S=300)
    return ModelClient(cfg(**{**base, **cambios}))


def en_hilos(n, funcion, *args):
    hilos = [threading.Thread(target=funcion, args=args) for _ in range(n)]
    [h.start() for h in hilos]
    return hilos


def esperar(condicion, limite=5.0):
    t0 = time.perf_counter()
    while not condicion() and time.perf_counter() - t0 < limite:
        time.sleep(0.02)
    return condicion()


# --- el cupo bajo cancelación del juez y ERR-CMP-008 ---

def juez_con_ollama_lento(monkeypatch, n=4, demora=0.3):
    """`juzgar_pares` REAL con `juzgar_par` real y un cliente cuyo único proveedor es Ollama (cupo de 1) que tarda `demora` por llamada."""
    llamadas = []
    mc = armar(monkeypatch, {"ollama": falso("ollama", demora=demora, contenido=VEREDICTO, llamadas=llamadas)}, LLM_PROVIDER="ollama", LLM_FALLBACK="", LLM_CONCURRENCY=n)
    return mc, llamadas, [par(i) for i in range(n)]


def test_las_llamadas_en_cola_del_cupo_cuentan_como_vivas_para_err_cmp_008(monkeypatch):
    """Con 4 pares y un cupo de 1, los 4 hilos del juez viven aunque solo uno hable con Ollama: el contador (y el 409) los ve a todos."""
    mc, llamadas, pares = juez_con_ollama_lento(monkeypatch, demora=0.3)
    s = mc.s
    resultado = []
    hilo = threading.Thread(target=lambda: resultado.append(asyncio.run(juzgar_pares(pares, SECCIONES, {}, mc, s))))
    hilo.start()
    assert esperar(lambda: juez.llamadas_vivas() == 4)
    hilo.join(10)
    assert len(resultado[0]) == 4 and len(llamadas) == 4 and mc.usos["ollama"] == 4
    assert esperar(lambda: juez.llamadas_vivas() == 0)                      # al terminar todos, el contador vuelve a cero


def test_tras_cancelar_el_contador_y_el_cupo_vuelven_a_cero_aunque_haya_hilos_esperando_turno(monkeypatch):
    mc, llamadas, pares = juez_con_ollama_lento(monkeypatch, demora=0.2)
    palanca = Palanca()
    threading.Timer(0.1, lambda: setattr(palanca, "cancela", True)).start()
    with pytest.raises(Cancelado):
        asyncio.run(juzgar_pares(pares, SECCIONES, {}, mc, mc.s, obs=palanca))
    assert esperar(lambda: juez.llamadas_vivas() == 0, limite=5)             # los huérfanos terminan solos
    assert mc._cupos["ollama"].acquire(blocking=False)                        # y el cupo quedó libre (si no, la próxima comparación se colgaría)
    mc._cupos["ollama"].release()


# (corregido el 25 nov 2026: antes marcado como defecto conocido por QA)
def test_tras_cancelar_los_hilos_que_esperaban_turno_no_llaman_a_ollama(monkeypatch):
    mc, llamadas, pares = juez_con_ollama_lento(monkeypatch, n=4, demora=0.3)
    palanca = Palanca()
    threading.Timer(0.1, lambda: setattr(palanca, "cancela", True)).start()
    with pytest.raises(Cancelado):
        asyncio.run(juzgar_pares(pares, SECCIONES, {}, mc, mc.s, obs=palanca))
    esperar(lambda: juez.llamadas_vivas() == 0, limite=5)
    assert len(llamadas) <= 1, f"llamadas a Ollama tras cancelar: {len(llamadas)} (4 pares, cupo 1)"


# --- el error dentro del cupo ---

class ErrorRaro(BaseException):
    """No es un `Exception`: p. ej. una interrupción del hilo. El `with` debe soltar el cupo igual."""


def test_el_cupo_se_libera_aunque_el_error_no_sea_una_excepcion_normal(monkeypatch):
    mc = armar(monkeypatch, {"ollama": falso("ollama", falla=ErrorRaro())}, LLM_PROVIDER="ollama", LLM_FALLBACK="")
    with pytest.raises(ErrorRaro):
        mc._completar(CORTO)
    assert mc._cupos["ollama"].acquire(blocking=False)
    mc._cupos["ollama"].release()


def test_un_error_de_ollama_en_medio_de_la_cadena_pasa_al_siguiente_y_suelta_el_cupo(monkeypatch):
    c = {"groq": falso("groq", falla=ConnectionError("sin red")), "ollama": falso("ollama", falla=ConnectionError("cayó")), "databricks": falso("databricks")}
    mc = armar(monkeypatch, c, LLM_FALLBACK="ollama,databricks")
    assert '"databricks"' in mc._completar(CORTO)
    assert set(mc._caidos) == {"groq", "ollama"} and mc.usos == {"databricks": 1}
    assert mc._cupos["ollama"].acquire(blocking=False)
    mc._cupos["ollama"].release()


def test_con_ollama_en_medio_un_ollama_sano_atiende_y_no_toca_al_ultimo(monkeypatch):
    llamadas = []
    c = {"groq": falso("groq", falla=ConnectionError("x")), "ollama": falso("ollama", llamadas=llamadas), "databricks": falso("databricks", llamadas=llamadas)}
    mc = armar(monkeypatch, c, LLM_FALLBACK="ollama,databricks")
    assert '"ollama"' in mc._completar(CORTO) and llamadas == ["ollama"]


# (corregido el 25 nov 2026: antes marcado como defecto conocido por QA)
def test_si_ollama_cae_los_que_esperaban_turno_no_lo_vuelven_a_probar(monkeypatch):
    llamadas = []
    c = {"groq": falso("groq", falla=ConnectionError("x")), "ollama": falso("ollama", demora=0.2, falla=TimeoutError("colgado"), llamadas=llamadas), "databricks": falso("databricks")}
    mc = armar(monkeypatch, c, LLM_FALLBACK="ollama,databricks")
    resultados = []
    hilos = en_hilos(4, lambda: resultados.append(mc._completar(CORTO)))
    [h.join(10) for h in hilos]
    assert len(resultados) == 4 and all('"databricks"' in r for r in resultados)      # esto sí se cumple: ninguno se queda sin respuesta
    assert llamadas.count("ollama") == 1, f"Ollama recibió {llamadas.count('ollama')} llamadas a un servicio ya marcado como caído"


# --- Ollama como proveedor principal, con y sin respaldo ---

def test_ollama_principal_con_respaldo_vacio_se_reintenta_en_la_llamada_siguiente(monkeypatch):
    estado = {"cae": True}
    def create(**kw):
        if estado["cae"]:
            raise ConnectionError("apagado")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"de": "ollama"}'))])
    c = {"ollama": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))}
    mc = armar(monkeypatch, c, LLM_PROVIDER="ollama", LLM_FALLBACK="")
    with pytest.raises(LLMUnavailableError):
        mc._completar(CORTO)
    assert mc._caidos == {}                                                     # el último de la cadena no se queda marcado
    estado["cae"] = False
    assert '"ollama"' in mc._completar(CORTO)


def test_nombrar_a_ollama_en_el_respaldo_siendo_el_principal_no_duplica_ni_multiplica_cupos(monkeypatch):
    c = {"ollama": falso("ollama"), "groq": falso("groq")}
    mc = armar(monkeypatch, c, LLM_PROVIDER="ollama", LLM_FALLBACK="ollama, groq,ollama")
    assert [p for p, *_ in mc._proveedores_llm()] == ["ollama", "groq"]
    assert list(mc._cupos) == ["ollama"]


@pytest.mark.parametrize("valor", [0, -3])
def test_una_concurrencia_de_ollama_en_cero_o_negativa_sigue_atendiendo_una_a_la_vez(monkeypatch, valor):
    llamadas = []
    mc = armar(monkeypatch, {"ollama": falso("ollama", demora=0.03, llamadas=llamadas)}, LLM_PROVIDER="ollama", LLM_FALLBACK="", OLLAMA_CONCURRENCIA=valor)
    hilos = en_hilos(3, mc._completar, CORTO)
    [h.join(10) for h in hilos]
    assert len(llamadas) == 3 and mc.usos["ollama"] == 3                         # no se bloquea con un cupo de 0


# --- el guarda con el reintento de JSON, cuyos mensajes crecen ---

def invalido_largo(caracteres):
    return "{" + "x" * caracteres                                                # JSON inválido que ocupa lo que dice


def prompt_que_apenas_cabe():
    """El prompt cabe en la primera llamada (con 1500 tokens de salida) pero no cabe el mismo más una respuesta mala de ~3000 caracteres y la corrección."""
    return "z" * (6692 * 3 - 1000)


def test_el_guarda_cuenta_la_conversacion_del_reintento_y_no_solo_el_prompt_original(monkeypatch):
    llamadas = []
    c = {"ollama": falso("ollama", contenido=invalido_largo(3000), llamadas=llamadas), "groq": falso("groq", contenido='{"a": 1}')}
    mc = armar(monkeypatch, c, LLM_PROVIDER="ollama", LLM_FALLBACK="groq")
    from pydantic import BaseModel

    class Esquema(BaseModel):
        a: int

    r = mc.chat_json("s", prompt_que_apenas_cabe(), Esquema)
    assert r.a == 1 and llamadas == ["ollama"]                                    # el reintento ya no cabía en Ollama: pasó al respaldo con la corrección adjunta
    assert "ollama" not in mc._caidos


# (corregido el 25 nov 2026: antes marcado como defecto conocido por QA)
def test_si_el_reintento_de_json_no_cabe_en_el_ultimo_proveedor_el_par_queda_a_revision_no_aborta(monkeypatch):
    c = {"groq": falso("groq", falla=ConnectionError("sin red")), "ollama": falso("ollama", contenido=invalido_largo(3000))}
    mc = armar(monkeypatch, c, LLM_FALLBACK="ollama")
    from pydantic import BaseModel

    class Esquema(BaseModel):
        a: int

    with pytest.raises(LLMOutputError):
        mc.chat_json("s", prompt_que_apenas_cabe(), Esquema)


def test_un_par_cuyo_prompt_no_cabe_en_ollama_ultimo_queda_a_revision_y_no_aborta_la_comparacion(monkeypatch):
    """Antes un solo par largo abortaba toda la comparación (`LLMUnavailableError`); ahora el par queda a revisión, como un JSON inválido (docs/09 §4)."""
    c = {"groq": falso("groq", falla=ConnectionError("sin red")), "ollama": falso("ollama", contenido=VEREDICTO)}
    mc = armar(monkeypatch, c, LLM_FALLBACK="ollama")
    largo = seccion("M1", "D2", "manual_control")
    largo.texto_literal = "palabra " * 4000                                      # ~32 000 caracteres: más que el contexto de 8192 tokens
    p = juzgar_par(par(1), SECCIONES["A1"], largo, {}, mc, mc.s)
    assert p.requiere_revision and p.veredicto is None


def test_un_par_normal_con_ollama_ultimo_se_juzga_y_queda_registrado(monkeypatch):
    c = {"groq": falso("groq", falla=ConnectionError("sin red")), "ollama": falso("ollama", contenido=VEREDICTO)}
    mc = armar(monkeypatch, c, LLM_FALLBACK="ollama")
    p = juzgar_par(par(1), SECCIONES["A1"], SECCIONES["M1"], {}, mc, mc.s)
    assert p.veredicto is not None and mc.usos == {"ollama": 1}


# --- la espera por turno frente a los timeouts: el SDK real contra un servidor local lento ---

class ServidorLento:
    """Un «Ollama» local que contesta `{"ok": 1}` a cada POST tras `demora` segundos y cuenta las peticiones. El SDK y su timeout son los reales."""

    def __init__(self, demora):
        self.demora, self.peticiones = demora, 0
        dueno = self

        class Manejador(BaseHTTPRequestHandler):
            def do_POST(self):
                dueno.peticiones += 1
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                time.sleep(dueno.demora)
                cuerpo = json.dumps({"id": "x", "object": "chat.completion", "created": 0, "model": "m",
                                     "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"ok": 1}'}}]}).encode()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(cuerpo)))
                    self.end_headers()
                    self.wfile.write(cuerpo)
                except OSError:
                    pass                                                        # el cliente ya se fue por su timeout

            def log_message(self, *a):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.http.daemon_threads = True
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.http.server_port}/v1"

    def cerrar(self):
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture
def ollama_local(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    servidores = []

    def crear(demora):
        servidores.append(ServidorLento(demora))
        return servidores[-1]

    yield crear
    [s.cerrar() for s in servidores]


def cliente_real(servidor, **cambios):
    base = dict(LLM_PROVIDER="ollama", LLM_FALLBACK="", OLLAMA_LLM_MODEL="m", OLLAMA_BASE_URL=servidor.url, OLLAMA_CONCURRENCIA=1, OLLAMA_TIMEOUT_S=0.4, LLM_TIMEOUT_S=0.05)
    return ModelClient(cfg(**{**base, **cambios}))


def test_la_espera_de_turno_tiene_tope_y_no_llama_al_modelo_ni_desbalancea_el_cupo(ollama_local):
    """4 hilos, cupo 1, 0,3 s por llamada, espera máxima de 0,5 s: atienden 2 y los otros 2 salen por «turno agotado» (LLMUnavailableError) sin hablar con el servidor."""
    servidor = ollama_local(0.3)
    mc = cliente_real(servidor, OLLAMA_TIMEOUT_S=0.5, LLM_CONCURRENCY=1)          # el tope de la cola es OLLAMA_TIMEOUT_S × LLM_CONCURRENCY
    resultados, errores = [], []

    def uno():
        try:
            resultados.append(mc._completar(CORTO))
        except Exception as e:
            errores.append(e)

    [h.join(15) for h in en_hilos(4, uno)]
    assert len(resultados) == 2 and len(errores) == 2 and servidor.peticiones == 2
    assert all(isinstance(e, LLMUnavailableError) for e in errores)
    assert mc._cupos["ollama"].acquire(blocking=False)                             # el cupo quedó con su valor (un `release` de más lanzaría ValueError)
    assert not mc._cupos["ollama"].acquire(blocking=False)
    mc._cupos["ollama"].release()


def test_si_ollama_en_medio_esta_ocupado_y_vence_el_turno_se_marca_caido_aunque_este_sano(monkeypatch):
    """Caracterización: el turno agotado se trata como una caída de Ollama (se usa el siguiente proveedor y Ollama se salta `LLM_FALLBACK_REINTENTO_S`)."""
    c = {"groq": falso("groq", falla=ConnectionError("x")), "ollama": falso("ollama", demora=0.4), "databricks": falso("databricks")}
    mc = armar(monkeypatch, c, LLM_FALLBACK="ollama,databricks", OLLAMA_TIMEOUT_S=0.1, LLM_CONCURRENCY=1)
    resultados = []
    [h.join(10) for h in en_hilos(2, lambda: resultados.append(mc._completar(CORTO)))]
    assert sorted(('"ollama"' in r, '"databricks"' in r) for r in resultados) == [(False, True), (True, False)]
    assert "ollama" in mc._caidos


# (corregido el 25 nov 2026: antes marcado como defecto conocido por QA)
def test_seis_pares_con_ollama_como_unico_proveedor_se_juzgan_todos_aunque_la_cola_dure_mas_que_el_timeout(monkeypatch):
    """Misma proporción que la real a escala: 6 pares, cupo 1, 0,1 s por llamada (el 6.º espera 0,5 s) y espera máxima de 0,35 s."""
    mc, llamadas, pares = juez_con_ollama_lento(monkeypatch, n=6, demora=0.1)
    mc.s = cfg(**{**mc.s.__dict__, "OLLAMA_TIMEOUT_S": 0.35})
    resultado = asyncio.run(juzgar_pares(pares, SECCIONES, {}, mc, mc.s))
    assert len(resultado) == 6 and len(llamadas) == 6


def test_con_ollama_el_timeout_es_el_propio_y_no_el_de_llm_timeout_s(ollama_local):
    """`LLM_TIMEOUT_S` (0,05 s aquí) no se aplica al LLM local: una llamada de 0,2 s sale bien con `OLLAMA_TIMEOUT_S=0,4`."""
    servidor = ollama_local(0.2)
    assert '"ok"' in cliente_real(servidor)._completar(CORTO)


def test_un_servidor_colgado_cuesta_dos_intentos_y_se_informa_como_servicio_no_disponible(ollama_local):
    """timeout 0,3 s y `max_retries=1`: el servidor recibe 2 peticiones (no 4 como con `LLM_RETRIES=3`) y el error es el de negocio, sin filtrar la URL del servidor."""
    servidor = ollama_local(1.5)
    mc = cliente_real(servidor, OLLAMA_TIMEOUT_S=0.3, LLM_RETRIES=3)
    t0 = time.perf_counter()
    with pytest.raises(LLMUnavailableError):
        mc._completar(CORTO)
    assert servidor.peticiones == 2
    assert time.perf_counter() - t0 < 4
    assert mc._cupos["ollama"].acquire(blocking=False)                             # el cupo se soltó tras el timeout
    mc._cupos["ollama"].release()


def test_si_se_sube_llm_timeout_s_para_un_modelo_lento_no_cambia_el_timeout_de_ollama():
    """Observación (BAJA): `config/.env.example` sugiere `LLM_TIMEOUT_S=600` para un modelo lento; con Ollama de LLM solo manda `OLLAMA_TIMEOUT_S`."""
    from backend.llm.client import crear_cliente
    llm, _ = crear_cliente("ollama", cfg(OLLAMA_LLM_MODEL="m", OLLAMA_TIMEOUT_S=300.0, LLM_TIMEOUT_S=600.0))
    assert llm.timeout == 300.0
