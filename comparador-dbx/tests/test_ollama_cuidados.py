"""Ollama como último respaldo del LLM (25 nov 2026): el modelo es pequeño y la máquina también (GPU de 4 GB, 4 núcleos), así que se cuidan el contexto, la concurrencia y la espera.
Deterministas: solo se reemplaza el transporte del SDK; el modelo real se probó aparte (implementacion/README.md)."""
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from dotenv import dotenv_values

from backend.config import RAIZ
from backend.core.errors import LLMOutputError, LLMUnavailableError
from backend.llm import client
from backend.llm.client import ModelClient, crear_cliente
from l3_ayudas import cfg

MODELFILE = RAIZ / "config" / "ollama" / "Modelfile.comparador"
CORTO = [{"role": "user", "content": "hola"}]


def falso(nombre, demora=0.0, falla=None, estado=None):
    def create(**kw):
        if estado is not None:
            estado["activas"] += 1
            estado["max"] = max(estado["max"], estado["activas"])
        try:
            time.sleep(demora)
            if falla is not None:
                raise falla
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f'{{"de": "{nombre}"}}'))])
        finally:
            if estado is not None:
                estado["activas"] -= 1
    return SimpleNamespace(nombre=nombre, chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def armar(monkeypatch, clientes, **cambios):
    monkeypatch.setattr(client, "crear_cliente", lambda p, s, embeddings=False: (clientes[p], f"modelo-{p}"))
    base = dict(LLM_PROVIDER="groq", LLM_FALLBACK="ollama", OLLAMA_NUM_CTX=8192, OLLAMA_RESERVA_SALIDA=1500, OLLAMA_CONCURRENCIA=1)
    return ModelClient(cfg(**{**base, **cambios}))


# --- el Modelfile y la configuración dicen lo mismo ---

def parametros_modelfile() -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r"^PARAMETER\s+(\w+)\s+(\S+)", MODELFILE.read_text(encoding="utf-8"), re.M)}


def test_el_modelfile_coincide_con_la_configuracion_para_que_el_guarda_de_contexto_no_mienta():
    from backend.config import settings
    p = parametros_modelfile()
    assert int(p["num_ctx"]) == settings.OLLAMA_NUM_CTX and int(p["num_predict"]) == settings.OLLAMA_RESERVA_SALIDA
    assert float(p["temperature"]) == settings.LLM_TEMPERATURE == 0
    assert re.search(r"^FROM\s+qwen3:4b-instruct", MODELFILE.read_text(encoding="utf-8"), re.M)


def test_el_stage_sandbox_usa_groq_databricks_y_ollama_sin_openrouter():
    v = dotenv_values(RAIZ / "config" / "stages" / "sandbox.env")
    assert [p.strip() for p in v["LLM_FALLBACK"].split(",")] == ["databricks", "ollama"]          # OpenRouter solo lo agrega el usuario (S-24)
    assert v["OLLAMA_LLM_MODEL"] == "comparador-qwen3-4b"
    assert dotenv_values(RAIZ / "config" / "defaults.env")["LLM_FALLBACK"] in ("", None)           # fuera de sandbox no hay respaldo


# --- el contexto ---

@pytest.mark.parametrize("caracteres,cabe", [(100, True), ((8192 - 1500) * 3, True), ((8192 - 1500) * 3 + 6, False), (60_000, False)])
def test_un_prompt_que_no_cabe_en_el_contexto_no_se_envia(monkeypatch, caracteres, cabe):
    mc = armar(monkeypatch, {"groq": falso("groq"), "ollama": falso("ollama")})
    assert mc._cabe_en_ollama([{"role": "user", "content": "x" * caracteres}]) is cabe


def test_si_el_texto_no_cabe_se_salta_ollama_y_pasa_al_siguiente_sin_marcarlo_caido(monkeypatch):
    c = {"groq": falso("groq", falla=ConnectionError("sin red")), "ollama": falso("ollama"), "databricks": falso("databricks")}
    mc = armar(monkeypatch, c, LLM_FALLBACK="ollama,databricks")
    largo = [{"role": "user", "content": "x" * 60_000}]
    assert '"databricks"' in mc._completar(largo)
    assert "ollama" not in mc._caidos                                  # no está caído: solo no sirve para este texto


def test_si_ollama_es_el_ultimo_y_el_texto_no_cabe_se_lanza_un_error_claro_sin_llamarlo(monkeypatch):
    llamadas = []
    ollama = falso("ollama")
    original = ollama.chat.completions.create
    ollama.chat.completions.create = lambda **kw: (llamadas.append(kw), original(**kw))[1]
    mc = armar(monkeypatch, {"groq": falso("groq", falla=ConnectionError("sin red")), "ollama": ollama})
    with pytest.raises(LLMOutputError, match="no cabe"):                     # el par queda a revisión: no es una caída
        mc._completar([{"role": "user", "content": "x" * 60_000}])
    assert llamadas == []


def test_un_prompt_normal_si_llega_a_ollama(monkeypatch):
    mc = armar(monkeypatch, {"groq": falso("groq", falla=ConnectionError("sin red")), "ollama": falso("ollama")})
    assert '"ollama"' in mc._completar(CORTO)


def test_ollama_como_proveedor_principal_tambien_tiene_el_guarda(monkeypatch):
    mc = armar(monkeypatch, {"ollama": falso("ollama")}, LLM_PROVIDER="ollama", LLM_FALLBACK="")
    with pytest.raises(LLMOutputError, match="no cabe"):
        mc._completar([{"role": "user", "content": "x" * 60_000}])


# --- la concurrencia ---

def test_el_juez_lanza_seis_llamadas_pero_ollama_atiende_una_a_la_vez(monkeypatch):
    estado = {"activas": 0, "max": 0}
    mc = armar(monkeypatch, {"groq": falso("groq"), "ollama": falso("ollama", demora=0.05, estado=estado)}, LLM_PROVIDER="ollama", LLM_FALLBACK="")
    hilos = [threading.Thread(target=mc._completar, args=(CORTO,)) for _ in range(6)]
    [h.start() for h in hilos]
    [h.join(10) for h in hilos]
    assert estado["max"] == 1 and mc.usos["ollama"] == 6


def test_con_dos_cupos_atiende_dos_a_la_vez_pero_no_mas(monkeypatch):
    estado = {"activas": 0, "max": 0}
    mc = armar(monkeypatch, {"ollama": falso("ollama", demora=0.05, estado=estado)}, LLM_PROVIDER="ollama", LLM_FALLBACK="", OLLAMA_CONCURRENCIA=2)
    hilos = [threading.Thread(target=mc._completar, args=(CORTO,)) for _ in range(6)]
    [h.start() for h in hilos]
    [h.join(10) for h in hilos]
    assert estado["max"] == 2


def test_los_otros_proveedores_no_se_limitan(monkeypatch):
    estado = {"activas": 0, "max": 0}
    mc = armar(monkeypatch, {"groq": falso("groq", demora=0.05, estado=estado)}, LLM_FALLBACK="")
    hilos = [threading.Thread(target=mc._completar, args=(CORTO,)) for _ in range(6)]
    [h.start() for h in hilos]
    [h.join(10) for h in hilos]
    assert estado["max"] > 1


def test_el_cupo_se_libera_aunque_la_llamada_falle(monkeypatch):
    mc = armar(monkeypatch, {"ollama": falso("ollama", falla=ConnectionError("cayó"))}, LLM_PROVIDER="ollama", LLM_FALLBACK="")
    for _ in range(3):
        with pytest.raises(LLMUnavailableError):
            mc._completar(CORTO)                                         # si no se liberara, la 2.ª llamada se quedaría esperando para siempre


# --- espera y reintentos ---

def test_el_cliente_de_ollama_espera_mas_y_no_reintenta_tres_veces_un_timeout():
    s = cfg(OLLAMA_LLM_MODEL="comparador-qwen3-4b", OLLAMA_TIMEOUT_S=300.0, LLM_TIMEOUT_S=120.0, LLM_RETRIES=3)
    llm, modelo = crear_cliente("ollama", s)
    assert modelo == "comparador-qwen3-4b" and llm.timeout == 300.0 and llm.max_retries == 1


def test_los_embeddings_de_ollama_conservan_la_espera_y_los_reintentos_de_siempre():
    s = cfg(OLLAMA_EMB_MODEL="bge-m3", OLLAMA_TIMEOUT_S=300.0, LLM_TIMEOUT_S=120.0, LLM_RETRIES=3)
    emb, modelo = crear_cliente("ollama", s, embeddings=True)
    assert modelo == "bge-m3" and emb.timeout == 120.0 and emb.max_retries == 3


# --- observaciones de appsec (25 nov 2026) ---

def test_la_espera_de_turno_tiene_tope_y_el_hilo_en_cola_no_llama_al_modelo(monkeypatch):
    llamadas = []
    ollama = falso("ollama", demora=0.6, estado={"activas": 0, "max": 0})
    original = ollama.chat.completions.create
    ollama.chat.completions.create = lambda **kw: (llamadas.append(1), original(**kw))[1]
    mc = armar(monkeypatch, {"groq": falso("groq", falla=ConnectionError("sin red")), "ollama": ollama}, OLLAMA_TIMEOUT_S=0.2, LLM_CONCURRENCY=1)
    resultados = []

    def llamar():
        try:
            resultados.append(mc._completar(CORTO))
        except LLMUnavailableError as e:
            resultados.append(e)

    hilos = [threading.Thread(target=llamar) for _ in range(3)]
    [h.start() for h in hilos]
    [h.join(10) for h in hilos]
    errores = [r for r in resultados if isinstance(r, LLMUnavailableError)]
    assert len(errores) == 2 and len(llamadas) == 1               # uno atendido; los otros dos se rindieron tras 0,2 s sin llamar al modelo
    assert all("espera de turno" in str(e) for e in errores)


def test_tras_agotar_la_espera_de_turno_el_cupo_no_queda_perdido(monkeypatch):
    mc = armar(monkeypatch, {"ollama": falso("ollama", demora=0.3)}, LLM_PROVIDER="ollama", LLM_FALLBACK="", OLLAMA_TIMEOUT_S=0.1, LLM_CONCURRENCY=1)
    primero = threading.Thread(target=lambda: mc._completar(CORTO))
    primero.start()
    time.sleep(0.05)
    with pytest.raises(LLMUnavailableError):
        mc._completar(CORTO)                                       # el segundo se rinde mientras el primero sigue
    primero.join(5)
    assert '"ollama"' in mc._completar(CORTO)                      # el cupo volvió: no se "perdió" por el que se rindió


@pytest.mark.parametrize("url,avisa", [("http://localhost:11434/v1", False), ("http://127.0.0.1:11434/v1", False), ("http://[::1]:11434/v1", False),
                                       ("http://192.168.1.50:11434/v1", True), ("http://gpu.interna.test:11434/v1", True)])
def test_si_ollama_apunta_fuera_de_la_maquina_se_avisa(caplog, url, avisa):
    caplog.set_level("WARNING")
    crear_cliente("ollama", cfg(OLLAMA_BASE_URL=url, OLLAMA_LLM_MODEL="comparador-qwen3-4b"))
    assert ("saldrán de ella" in caplog.text) is avisa


# --- si un par aborta la comparación, los hilos que quedan se retiran (appsec, 25 nov 2026) ---

def test_si_un_par_aborta_la_comparacion_los_hilos_en_cola_no_siguen_llamando_al_modelo(monkeypatch):
    import asyncio
    from backend.engine import juez
    from backend.models import Veredicto
    from tests.test_cancelar_comparacion import par, seccion

    llamadas = []

    def create(**kw):
        llamadas.append(1)
        time.sleep(0.25)
        if len(llamadas) == 1:
            raise ConnectionError("el modelo local se cayó")           # el primero falla: la comparación se aborta
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=Veredicto(naturaleza_articulo="obligacion", cobertura="total", cita_norma="x", comentario="c", confianza=0.9).model_dump_json()))])

    ollama = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    mc = armar(monkeypatch, {"ollama": ollama}, LLM_PROVIDER="ollama", LLM_FALLBACK="", LLM_CONCURRENCY=6)
    secciones = {"A1": seccion("A1", "D1", "normativa"), "M1": seccion("M1", "D2", "manual_control")}
    with pytest.raises(LLMUnavailableError):
        asyncio.run(juez.juzgar_pares([par(i) for i in range(6)], secciones, {}, mc, mc.s))
    time.sleep(3)                                                      # tiempo de sobra para que los 5 hilos restantes hubieran llamado (0,25 s cada uno)
    assert len(llamadas) <= 2                                          # el que ya estaba en vuelo como mucho; los demás se retiraron
    assert juez.llamadas_vivas() == 0
