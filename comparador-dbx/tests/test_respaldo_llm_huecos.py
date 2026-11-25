"""Huecos de `test_respaldo_llm.py` (QA, 25 nov 2026): hilos, `ping()`, reintento de JSON que cambia de proveedor, nombres en `LLM_FALLBACK`,
tope de llamadas por solicitud, borde del umbral del límite diario y el juez con la cadena de respaldo.

Deterministas. Igual que en `test_respaldo_llm.py`, solo se reemplaza el transporte del SDK (cada cliente sigue un guion de respuestas fijas
o de fallos); ningún modelo ni embedding se imita: los reales se prueban en `test_integracion_modelos.py`."""
import asyncio
import json
import threading
import time
from types import SimpleNamespace

import pytest

from backend.core.errors import LLMOutputError, LLMUnavailableError, ProviderConfigError
from backend.engine import juez
from backend.engine.juez import Cancelado, juzgar_par, juzgar_pares, llamadas_vivas
from backend.llm import client
from backend.llm.client import ModelClient, _limite_de_tasa, espera_sugerida
from backend.models import Par, Veredicto
from l3_ayudas import cfg, seccion


class RateLimitError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class APIConnectionError(Exception):
    pass


DIARIO = RateLimitError("Error code: 429 - Rate limit reached (TPD). Please try again in 8m36.672s.")
MINUTO = RateLimitError("Error code: 429 - Rate limit reached (TPM). Please try again in 8.1075s.")
VEREDICTO = Veredicto(naturaleza_articulo="obligacion", cobertura="parcial", cita_norma="concilia diariamente los saldos", cita_manual=None,
                      comentario="c", elementos_faltantes=[], confianza=0.8)
TEXTO = "El área de tesorería concilia diariamente los saldos de caja."
INVALIDO = '{"ok": "no es un booleano"}'


def guion(nombre: str, *pasos):
    """Cliente con la forma del SDK. Cada llamada consume un paso (texto = respuesta; excepción = fallo); el último se repite.
    Guarda una copia de los mensajes que recibió (`chat_json` añade mensajes a la misma lista después)."""
    llamadas: list[dict] = []
    lock = threading.Lock()

    def create(**kw):
        with lock:
            llamadas.append({**kw, "messages": list(kw["messages"])})
            paso = pasos[min(len(llamadas), len(pasos)) - 1] if pasos else json.dumps({"ok": True})
        if isinstance(paso, Exception):
            raise paso
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=paso))])

    return SimpleNamespace(nombre=nombre, llamadas=llamadas, chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def armar(monkeypatch, clientes: dict, **cambios) -> ModelClient:
    base = dict(LLM_PROVIDER="groq", LLM_FALLBACK="databricks,openrouter", LLM_FALLBACK_REINTENTO_S=300, LLM_ESPERA_LIMITE_S=20, LLM_INTENTOS_LIMITE=6)

    def crear(proveedor, s, embeddings=False):
        if embeddings:
            return SimpleNamespace(), "emb-sin-vectores"                        # sin `.embeddings`: la prueba solo mira que el LLM no dependa de ellos
        return clientes[proveedor], f"modelo-{proveedor}"

    monkeypatch.setattr(client, "crear_cliente", crear)
    return ModelClient(cfg(**{**base, **cambios}))


def tres(**pasos):
    return {n: guion(n, *pasos.get(n, ())) for n in ("groq", "databricks", "openrouter")}


MSJ = [{"role": "user", "content": "hola"}]


class Pong(client.BaseModel):
    ok: bool


# --- hilos ---

def test_varios_hilos_arman_la_cadena_una_sola_vez(monkeypatch):
    creados = []

    def crear(proveedor, s, embeddings=False):
        creados.append(proveedor)
        time.sleep(0.02)                                                         # ensancha la ventana de la carrera
        return guion(proveedor), f"modelo-{proveedor}"

    monkeypatch.setattr(client, "crear_cliente", crear)
    mc = ModelClient(cfg(LLM_PROVIDER="groq", LLM_FALLBACK="databricks,openrouter"))
    listas, barrera = [], threading.Barrier(8)

    def hilo():
        barrera.wait()
        listas.append(mc._proveedores_llm())

    hilos = [threading.Thread(target=hilo) for _ in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert sorted(creados) == ["databricks", "groq", "openrouter"]               # cada cliente se crea una vez, no 8
    assert len(listas) == 8 and all(l is listas[0] for l in listas)


def test_doce_hilos_con_el_principal_caido_reciben_todos_respuesta_del_respaldo(monkeypatch):
    c = tres(groq=(DIARIO,))
    mc = armar(monkeypatch, c)
    mc._proveedores_llm()
    resultados, errores, barrera = [], [], threading.Barrier(12)

    def hilo():
        barrera.wait()
        try:
            resultados.append(mc._completar(MSJ))
        except Exception as e:                                                   # noqa: BLE001
            errores.append(e)

    hilos = [threading.Thread(target=hilo) for _ in range(12)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert not errores and len(resultados) == 12
    assert 1 <= len(c["groq"].llamadas) <= 12 and len(c["databricks"].llamadas) == 12     # los hilos ya en vuelo pueden tocar a Groq; los demás no
    assert "groq" in mc._caidos and not c["openrouter"].llamadas


def test_si_cae_el_ultimo_proveedor_el_clear_de_un_hilo_no_rompe_a_los_otros(monkeypatch):
    c = tres(groq=(DIARIO,), databricks=(APIConnectionError("sin red"),), openrouter=(APIConnectionError("sin red 2"),))
    mc = armar(monkeypatch, c)
    mc._proveedores_llm()
    fallos, barrera = [], threading.Barrier(10)

    def hilo():
        barrera.wait()
        try:
            mc._completar(MSJ)
        except LLMUnavailableError:
            fallos.append(1)

    hilos = [threading.Thread(target=hilo) for _ in range(10)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert len(fallos) == 10                                                      # todos terminan con el error limpio, ninguno con KeyError ni otra cosa


def test_el_contador_de_usos_no_pierde_cuentas_con_hilos(monkeypatch):
    c = tres(groq=(DIARIO,))
    mc = armar(monkeypatch, c)
    mc._proveedores_llm()
    barrera = threading.Barrier(12)

    def hilo():
        barrera.wait()
        for _ in range(5):
            mc._completar(MSJ)

    hilos = [threading.Thread(target=hilo) for _ in range(12)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert mc.usos["databricks"] == 60 and mc.usos["groq"] == 0 and mc.usos["openrouter"] == 0       # 60 llamadas resueltas, ni una de más ni de menos


# --- ping ---

def test_ping_del_llm_usa_la_cadena_y_los_embeddings_no_se_mezclan(monkeypatch):
    c = tres(groq=(AuthenticationError("401 invalid api key"),))
    estado = armar(monkeypatch, c).ping()
    assert estado["llm"]["ok"] is True and len(c["databricks"].llamadas) == 1
    assert estado["embeddings"]["ok"] is False and "codigo" in estado["embeddings"]


def test_ping_con_todos_los_proveedores_caidos_no_filtra_el_detalle_tecnico(monkeypatch):
    c = tres(groq=(DIARIO,), databricks=(APIConnectionError("host interno dbc-1234.cloud.databricks.com"),), openrouter=(APIConnectionError("sk-or-v1-secreto"),))
    llm = armar(monkeypatch, c).ping()["llm"]
    assert llm["ok"] is False and set(llm) == {"ok", "codigo", "mensaje"}
    assert "dbc-1234" not in str(llm) and "sk-or" not in str(llm)


# --- reintento de JSON que cambia de proveedor ---

def test_el_reintento_de_json_puede_ir_a_otro_proveedor_con_la_correccion_adjunta(monkeypatch):
    c = tres(groq=(INVALIDO, DIARIO), databricks=(json.dumps({"ok": True}),))
    r = armar(monkeypatch, c).chat_json("sistema", "usuario", Pong)
    assert r.ok is True
    assert len(c["groq"].llamadas) == 2 and len(c["databricks"].llamadas) == 1
    recibido = c["databricks"].llamadas[0]["messages"]
    assert [m["role"] for m in recibido] == ["system", "user", "assistant", "user"]
    assert recibido[2]["content"] == INVALIDO and "no cumple el esquema" in recibido[3]["content"]


def test_el_json_invalido_en_los_dos_intentos_no_activa_el_respaldo(monkeypatch):
    c = tres(groq=(INVALIDO,))
    with pytest.raises(LLMOutputError):
        armar(monkeypatch, c).chat_json("s", "u", Pong)
    assert len(c["groq"].llamadas) == 2 and not c["databricks"].llamadas and not c["openrouter"].llamadas      # un JSON malo no es una caída


def test_el_json_invalido_no_deja_caido_al_proveedor(monkeypatch):
    mc = armar(monkeypatch, tres(groq=(INVALIDO,)))
    with pytest.raises(LLMOutputError):
        mc.chat_json("s", "u", Pong)
    assert mc._caidos == {}


def test_el_mensaje_del_respaldo_con_json_obligatorio_no_modifica_lo_que_se_guarda_para_el_reintento(monkeypatch):
    c = tres(groq=(DIARIO,), databricks=(INVALIDO, json.dumps({"ok": True})))
    armar(monkeypatch, c).chat_json("sistema", "pide el dato", Pong)             # el usuario no dice «json»: Databricks recibe la palabra añadida
    primera, segunda = c["databricks"].llamadas
    assert primera["messages"][-1]["content"].endswith("Responde en formato json.")
    assert [m["role"] for m in segunda["messages"]] == ["system", "user", "assistant", "user"]
    assert "Responde en formato json." not in segunda["messages"][1]["content"]   # la copia con la palabra no se arrastra a la conversación


# --- nombres en LLM_FALLBACK (con `crear_cliente` real: la configuración no toca la red) ---

REAL = dict(LLM_PROVIDER="groq", GROQ_API_KEY="gsk_ficticia", GROQ_LLM_MODEL="m", DATABRICKS_HOST="https://dbc-1.cloud.databricks.com", DATABRICKS_LLM_ENDPOINT="e",
            DATABRICKS_TOKEN="dapi-ficticio", OPENROUTER_API_KEY="sk-or-ficticia", OPENROUTER_BASE_URL="https://openrouter.ai/api/v1", OPENROUTER_LLM_MODEL="x/y:free")


def nombres(**cambios) -> list[str]:
    return [p for p, _, _ in ModelClient(cfg(**{**REAL, **cambios}))._proveedores_llm()]


def test_llm_fallback_con_espacios_se_normaliza():
    assert nombres(LLM_FALLBACK="  databricks ,\topenrouter  ") == ["groq", "databricks", "openrouter"]


@pytest.mark.parametrize("valor", ["", " ", ",", " , ,, "])
def test_llm_fallback_vacio_o_solo_comas_no_da_respaldo(valor):
    assert nombres(LLM_FALLBACK=valor) == ["groq"]


def test_llm_fallback_con_mayusculas_se_omite_con_aviso_no_se_adivina(caplog):
    assert nombres(LLM_FALLBACK="Databricks,OPENROUTER") == ["groq"]            # los nombres son en minúsculas (como LLM_PROVIDER); no se corrigen en silencio
    assert caplog.text.count("Respaldo del LLM") == 2 and "desconocido" in caplog.text


def test_llm_fallback_con_un_nombre_mal_escrito_se_omite_y_sigue_con_los_demas(caplog):
    assert nombres(LLM_FALLBACK="databrics,openrouter") == ["groq", "openrouter"]
    assert "databrics" in caplog.text


def test_llm_fallback_no_acepta_proveedores_locales_sin_motivo_pero_los_admite_si_estan_configurados():
    assert nombres(LLM_FALLBACK="ollama", OLLAMA_LLM_MODEL="qwen") == ["groq", "ollama"]          # `crear_cliente` los conoce: la lista es del operador


def test_el_aviso_de_un_respaldo_omitido_no_lleva_el_valor_de_ninguna_clave(caplog):
    nombres(LLM_FALLBACK="openrouter", OPENROUTER_API_KEY="")
    assert "OPENROUTER_API_KEY" in caplog.text and "sk-or-ficticia" not in caplog.text and "gsk_ficticia" not in caplog.text


def test_principal_databricks_con_respaldo_databricks_no_se_duplica(monkeypatch):
    assert nombres(LLM_PROVIDER="databricks", LLM_FALLBACK="databricks") == ["databricks"]
    c = tres(databricks=(APIConnectionError("sin red"),))
    mc = armar(monkeypatch, c, LLM_PROVIDER="databricks", LLM_FALLBACK="databricks")
    with pytest.raises(LLMUnavailableError):
        mc._completar(MSJ)
    assert len(c["databricks"].llamadas) == 1                                    # sin ciclo ni segundo intento al mismo proveedor


def test_principal_databricks_pasa_a_groq_y_luego_a_openrouter(monkeypatch):
    c = tres(databricks=(APIConnectionError("sin red"),), groq=(AuthenticationError("401"),))
    mc = armar(monkeypatch, c, LLM_PROVIDER="databricks", LLM_FALLBACK="groq,openrouter")
    assert json.loads(mc._completar(MSJ)) == {"ok": True}
    assert [len(c[n].llamadas) for n in ("databricks", "groq", "openrouter")] == [1, 1, 1]
    assert "json" in c["databricks"].llamadas[0]["messages"][-1]["content"].lower() and c["groq"].llamadas[0]["messages"][-1]["content"] == "hola"


def test_el_principal_mal_configurado_falla_aunque_haya_respaldo_sano():
    with pytest.raises(ProviderConfigError, match="GROQ_API_KEY"):
        nombres(GROQ_API_KEY="", LLM_FALLBACK="databricks")


# --- tope de llamadas por solicitud ---

def test_todos_caidos_hace_una_llamada_por_proveedor_y_no_mas(monkeypatch):
    c = tres(groq=(APIConnectionError("a"),), databricks=(APIConnectionError("b"),), openrouter=(APIConnectionError("c"),))
    with pytest.raises(LLMUnavailableError):
        armar(monkeypatch, c).chat_json("s", "u", Pong)
    assert [len(c[n].llamadas) for n in ("groq", "databricks", "openrouter")] == [1, 1, 1]       # una caída no activa el reintento de JSON


def test_un_nombre_repetido_en_el_respaldo_no_multiplica_las_llamadas(monkeypatch):
    c = tres(groq=(APIConnectionError("a"),), openrouter=(APIConnectionError("c"),))
    with pytest.raises(LLMUnavailableError):
        armar(monkeypatch, c, LLM_FALLBACK="openrouter,openrouter,groq,openrouter")._completar(MSJ)
    assert len(c["groq"].llamadas) == 1 and len(c["openrouter"].llamadas) == 1


def test_el_peor_caso_de_chat_json_no_pasa_de_dos_llamadas_por_proveedor(monkeypatch):
    c = tres(groq=(INVALIDO, DIARIO), databricks=(APIConnectionError("sin red"),), openrouter=(INVALIDO,))
    with pytest.raises(LLMOutputError):
        armar(monkeypatch, c).chat_json("s", "u", Pong)
    total = sum(len(x.llamadas) for x in c.values())
    assert total == 4 and total <= 2 * 3                                         # groq(inválido) + groq(cae) + databricks(cae) + openrouter(inválido): dos intentos de JSON, uno por vuelta


# --- borde del umbral del límite diario ---

@pytest.mark.parametrize("espera,cambia", [("2m0s", False), ("120s", False), ("2m0.5s", True), ("2m1s", True), ("1h", True), ("119.9s", False), ("1m30.5s", False)])
def test_el_borde_es_estricto_con_espera_por_intentos(espera, cambia):
    mc = ModelClient(cfg(LLM_ESPERA_LIMITE_S=20, LLM_INTENTOS_LIMITE=6))         # tope = 120 s
    assert mc._conviene_respaldo(RateLimitError(f"429 Please try again in {espera}.")) is cambia


def test_con_cero_intentos_cualquier_espera_sugerida_cambia_de_proveedor():
    assert ModelClient(cfg(LLM_ESPERA_LIMITE_S=20, LLM_INTENTOS_LIMITE=0))._conviene_respaldo(RateLimitError("429 try again in 250ms")) is True


def test_el_juez_reexporta_las_mismas_funciones_del_cliente():
    assert juez._limite_de_tasa is _limite_de_tasa and juez.espera_sugerida is espera_sugerida


def test_un_5xx_o_un_modelo_inexistente_cambian_de_proveedor_pero_no_tocan_la_clave():
    mc = ModelClient(cfg())
    for texto in ("Error code: 503 - service unavailable", "Error code: 404 - model not found", "Error code: 400 - bad request"):
        assert mc._conviene_respaldo(LLMUnavailableError(texto)) is True


# QA-R1 (corregido el 25 nov 2026): `_limite_de_tasa` ahora exige «429» como número entero.
def test_un_5xx_con_429_dentro_de_un_identificador_cambia_de_proveedor(monkeypatch):
    c = tres(groq=(APIConnectionError("Error code: 502 - Bad gateway, request id 7b4291ac"),))
    assert json.loads(armar(monkeypatch, c)._completar(MSJ)) == {"ok": True}


# --- el juez con la cadena (ERR-CMP-008 y tope de llamadas vivas no se alteran) ---

@pytest.fixture
def sin_dormir(monkeypatch):
    esperas = []

    def dormir(segundos, obs):
        if obs.cancelado():
            raise Cancelado()
        esperas.append(segundos)

    monkeypatch.setattr(juez, "_dormir", dormir)
    return esperas


def un_par():
    art, man = seccion("A", TEXTO, ident="ART-1", ruta=("ART-1",)), seccion("M", TEXTO, ident="CTRL-M")
    return Par(id="P", articulo_id="A", seccion_id="M", origen={"v1"}, score_v1=0.5), art, man


def test_el_juez_con_el_limite_diario_del_principal_obtiene_veredicto_sin_esperar(monkeypatch, sin_dormir):
    c = tres(groq=(DIARIO,), databricks=(VEREDICTO.model_dump_json(),))
    par, art, man = un_par()
    r = juzgar_par(par, art, man, {"D": "Doc"}, armar(monkeypatch, c), cfg(LLM_INTENTOS_LIMITE=6, LLM_ESPERA_LIMITE_S=20))
    assert r.veredicto is not None and r.veredicto.cobertura == "parcial" and sin_dormir == []
    assert r.cita_norma_verificada                                               # la cita sigue verificándose contra el texto fuente, venga del proveedor que venga


def test_el_juez_sigue_esperando_el_limite_corto_sin_cambiar_de_proveedor(monkeypatch, sin_dormir):
    c = tres(groq=(MINUTO, VEREDICTO.model_dump_json()))
    par, art, man = un_par()
    r = juzgar_par(par, art, man, {"D": "Doc"}, armar(monkeypatch, c), cfg(LLM_INTENTOS_LIMITE=6, LLM_ESPERA_LIMITE_S=20))
    assert r.veredicto is not None and len(sin_dormir) == 1 and 8 < sin_dormir[0] <= 120
    assert len(c["groq"].llamadas) == 2 and not c["databricks"].llamadas


def test_con_el_principal_caido_seis_pares_en_hilos_terminan_y_no_dejan_llamadas_vivas(monkeypatch, sin_dormir):
    c = tres(groq=(DIARIO,), databricks=(VEREDICTO.model_dump_json(),))
    mc = armar(monkeypatch, c)
    s = cfg(LLM_CONCURRENCY=3, LLM_INTENTOS_LIMITE=2, LLM_ESPERA_LIMITE_S=1)
    todas = {f"A{i}": seccion(f"A{i}", TEXTO, ident=f"ART-{i}", ruta=(f"ART-{i}",)) for i in range(6)} | {"M": seccion("M", TEXTO, ident="CTRL-M")}
    pares = [Par(id=f"P{i}", articulo_id=f"A{i}", seccion_id="M", origen={"v1"}, score_v1=0.5) for i in range(6)]
    antes = llamadas_vivas()
    hechos = asyncio.run(juzgar_pares(pares, todas, {"D": "Doc"}, mc, s))
    assert all(p.veredicto is not None for p in hechos) and len(c["databricks"].llamadas) == 6
    assert len(c["groq"].llamadas) <= s.LLM_CONCURRENCY                          # solo los pares ya en vuelo tocan a Groq; el resto va directo al respaldo
    assert llamadas_vivas() == antes                                             # el contador de ERR-CMP-008 cuenta pares en vuelo, no llamadas al SDK: vuelve a su valor
    assert sin_dormir == []


def test_si_todos_los_proveedores_caen_el_juez_propaga_el_error_y_libera_la_llamada_viva(monkeypatch, sin_dormir):
    c = tres(groq=(APIConnectionError("a"),), databricks=(APIConnectionError("b"),), openrouter=(APIConnectionError("c"),))
    par, art, man = un_par()
    antes = llamadas_vivas()
    with pytest.raises(LLMUnavailableError):
        asyncio.run(juzgar_pares([par], {"A": art, "M": man}, {"D": "Doc"}, armar(monkeypatch, c), cfg(LLM_CONCURRENCY=2)))
    assert llamadas_vivas() == antes and sin_dormir == []                        # no es un límite de tasa: no hay esperas


def test_el_ultimo_proveedor_con_limite_corto_sin_pista_se_trata_como_limite_de_tasa(monkeypatch, sin_dormir):
    c = tres(groq=(DIARIO,), databricks=(APIConnectionError("sin red"),), openrouter=(RateLimitError("Error code: 429 - Rate limit exceeded: free-models-per-min"),
                                                                                     VEREDICTO.model_dump_json()))
    par, art, man = un_par()
    r = juzgar_par(par, art, man, {"D": "Doc"}, armar(monkeypatch, c), cfg(LLM_INTENTOS_LIMITE=6, LLM_ESPERA_LIMITE_S=20))
    assert r.veredicto is not None and len(sin_dormir) == 1                      # OpenRouter gratuito limita por minuto sin decir cuánto: el juez espera y reintenta
    assert len(c["openrouter"].llamadas) == 2
