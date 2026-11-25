"""Huecos del proveedor `databricks` hallados por QA (25 nov 2026): host con puerto o mayúsculas, expiración y renovación del acceso OAuth,
`ModelClient` con `LLM_PROVIDER=databricks` (creación diferida) y el reintento de `chat_json` con «json» en el mensaje del usuario.
Deterministas. Los modelos reales de Databricks van en tests/test_integracion_modelos.py."""
import logging
import socket
import threading
import time

import httpx
import pytest
from pydantic import BaseModel

from backend import config
from backend.core.errors import LLMOutputError, LLMUnavailableError, ProviderConfigError
from backend.llm import client
from backend.llm.client import ModelClient, _host_databricks, _TokenDatabricks, crear_cliente
from l3_ayudas import cfg

HOST = "https://dbc-1234.cloud.databricks.com"
C = cfg(DATABRICKS_HOST=HOST, DATABRICKS_TOKEN="t-personal", DATABRICKS_CLIENT_ID="", DATABRICKS_CLIENT_SECRET="",
        DATABRICKS_LLM_ENDPOINT="databricks-gpt-oss-120b", DATABRICKS_EMB_ENDPOINT="databricks-qwen3-embedding-0-6b")


def con(**cambios):
    return cfg(**{**C.__dict__, **cambios})


class Ok(BaseModel):
    ok: bool


def puerto_cerrado() -> int:
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]


# --- host -----------------------------------------------------------------------------------

@pytest.mark.parametrize("host,esperado", [
    ("HTTPS://DBC-1.Cloud.Databricks.com:443", "https://DBC-1.Cloud.Databricks.com:443"),     # esquema en mayúsculas: se acepta y se normaliza
    ("dbc-1.cloud.databricks.com:8443", "https://dbc-1.cloud.databricks.com:8443"),           # sin esquema y con puerto
    ("  https://dbc-1.cloud.databricks.com", "https://dbc-1.cloud.databricks.com"),
    ("https://dbc-1.cloud.databricks.com?a=1#f", "https://dbc-1.cloud.databricks.com"),       # consulta y fragmento no viajan en la URL base
])
def test_host_con_puerto_mayusculas_o_cola_se_normaliza(host, esperado):
    assert _host_databricks(host) == esperado


@pytest.mark.parametrize("host", ["HTTP://dbc-1.cloud.databricks.com", "https://x.com\\@evil.com", "//dbc-1.cloud.databricks.com", "https:///ruta"])
def test_host_con_esquema_distinto_o_userinfo_disfrazado_se_rechaza(host):
    with pytest.raises(ProviderConfigError):
        _host_databricks(host)


def test_el_cliente_usa_el_host_normalizado_tambien_para_pedir_el_acceso_oauth():
    cli, _ = crear_cliente("databricks", con(DATABRICKS_HOST="dbc-1.cloud.databricks.com:8443"))
    auth = cli._client.auth
    assert isinstance(auth, _TokenDatabricks) and auth.host == "https://dbc-1.cloud.databricks.com:8443"
    assert str(cli.base_url).rstrip("/") == "https://dbc-1.cloud.databricks.com:8443/serving-endpoints"


def test_el_marcador_reemplazar_del_token_cuenta_como_ausente_y_pide_oauth():
    with pytest.raises(ProviderConfigError, match="DATABRICKS_CLIENT_ID"):
        crear_cliente("databricks", con(DATABRICKS_TOKEN="REEMPLAZAR-token"))
    assert crear_cliente("databricks", con(DATABRICKS_TOKEN="REEMPLAZAR-token", DATABRICKS_CLIENT_ID="id", DATABRICKS_CLIENT_SECRET="s"))[1]


def test_embeddings_sin_su_endpoint_aborta_aunque_el_del_llm_exista():
    with pytest.raises(ProviderConfigError, match="DATABRICKS_EMB_ENDPOINT"):
        crear_cliente("databricks", con(DATABRICKS_EMB_ENDPOINT=""), embeddings=True)
    assert crear_cliente("databricks", con(DATABRICKS_EMB_ENDPOINT=""))[1] == "databricks-gpt-oss-120b"


# --- expiración y renovación del acceso OAuth --------------------------------------------------

def oauth(monkeypatch, expires_in=3600, cuerpo=None, estado=200):
    """Reemplaza solo `httpx.post` (el endpoint OAuth del workspace, no un modelo) y pone un reloj manual."""
    reloj = {"t": 1000.0, "posts": 0}

    def post(url, **kw):
        reloj["posts"] += 1
        datos = cuerpo if cuerpo is not None else {"access_token": f"acc{reloj['posts']}", "expires_in": expires_in}
        return httpx.Response(estado, json=datos, request=httpx.Request("POST", url))

    monkeypatch.setattr(client.httpx, "post", post)
    monkeypatch.setattr(client.time, "monotonic", lambda: reloj["t"])
    return _TokenDatabricks(con(DATABRICKS_TOKEN="", DATABRICKS_CLIENT_ID="id-app", DATABRICKS_CLIENT_SECRET="clave-app"), HOST), reloj


def test_el_acceso_se_renueva_dos_minutos_antes_de_vencer(monkeypatch):
    auth, reloj = oauth(monkeypatch, expires_in=3600)
    assert auth._obtener() == "acc1"
    reloj["t"] += 3600 - 121                                     # un segundo antes del margen: se reutiliza
    assert auth._obtener() == "acc1" and reloj["posts"] == 1
    reloj["t"] += 2                                              # pasó el margen de 120 s: renueva
    assert auth._obtener() == "acc2" and reloj["posts"] == 2


@pytest.mark.parametrize("expires_in", [30, 100, 0])
def test_un_acceso_de_vida_corta_dura_al_menos_60_segundos(monkeypatch, expires_in):
    auth, reloj = oauth(monkeypatch, expires_in=expires_in)
    auth._obtener()
    reloj["t"] += 59
    assert auth._obtener() == "acc1"                             # piso de 60 s: no se pide uno nuevo por cada petición
    reloj["t"] += 2
    assert auth._obtener() == "acc2"


def test_sin_expires_in_se_asume_una_hora(monkeypatch):
    auth, reloj = oauth(monkeypatch, cuerpo={"access_token": "abc"})
    auth._obtener()
    reloj["t"] += 3000
    assert auth._obtener() == "abc" and reloj["posts"] == 1


@pytest.mark.parametrize("estado,cuerpo", [(401, {"error": "invalid_client"}), (200, {"sin": "token"}), (200, {"access_token": "x", "expires_in": "no-es-numero"})])
def test_un_acceso_invalido_es_error_de_configuracion_sin_filtrar_la_respuesta_y_no_se_guarda(monkeypatch, estado, cuerpo):
    auth, reloj = oauth(monkeypatch, cuerpo=cuerpo, estado=estado)
    with pytest.raises(ProviderConfigError) as e:
        auth._obtener()
    assert "clave-app" not in str(e.value) and "invalid_client" not in str(e.value) and e.value.__cause__ is None
    assert auth._token == ""                                     # no se guarda nada: el siguiente intento vuelve a pedirlo
    with pytest.raises(ProviderConfigError):
        auth._obtener()
    assert reloj["posts"] == 2


def test_seis_hilos_a_la_vez_piden_el_acceso_una_sola_vez(monkeypatch):
    auth, reloj = oauth(monkeypatch)
    resultados = []
    hilos = [threading.Thread(target=lambda: resultados.append(auth._obtener())) for _ in range(6)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert resultados == ["acc1"] * 6 and reloj["posts"] == 1


def test_la_cabecera_usa_el_acceso_renovado_en_cada_peticion(monkeypatch):
    auth, reloj = oauth(monkeypatch, expires_in=200)             # vive 200 - 120 = 80 s
    pedir = lambda: next(auth.auth_flow(httpx.Request("POST", f"{HOST}/serving-endpoints/chat/completions"))).headers["Authorization"]
    assert pedir() == "Bearer acc1"
    reloj["t"] += 100
    assert pedir() == "Bearer acc2"


def test_las_credenciales_de_databricks_se_ocultan_en_el_registro(monkeypatch):
    monkeypatch.setattr(config, "settings", con(DATABRICKS_TOKEN="dapi-personal-12345", DATABRICKS_CLIENT_SECRET="clave-app-98765"))
    texto = config.redact("fallo con dapi-personal-12345 y clave-app-98765, host https://id:pwd@dbc.com")
    assert "personal-12345" not in texto and "clave-app-98765" not in texto and "id:pwd" not in texto
    assert config.es_secreto("DATABRICKS_CLIENT_SECRET") and config.es_secreto("DATABRICKS_TOKEN") and not config.es_secreto("DATABRICKS_HOST")
    assert "personal-12345" not in repr(config.settings) and "clave-app-98765" not in repr(config.settings)


# --- ModelClient con LLM_PROVIDER=databricks -------------------------------------------------

def test_modelclient_databricks_se_construye_sin_validar_y_crea_el_cliente_en_el_primer_uso():
    mc = ModelClient(con(LLM_PROVIDER="databricks", EMB_PROVIDER="databricks", DATABRICKS_HOST=""))     # construir no valida
    assert mc._llm is None and mc._emb is None
    with pytest.raises(ProviderConfigError, match="DATABRICKS_HOST"):                                    # falla recién al usarlo
        mc.llm()
    mc = ModelClient(con(LLM_PROVIDER="databricks", EMB_PROVIDER="databricks"))
    assert mc._llm is None and mc.llm() is mc.llm() and mc.llm()[1] == "databricks-gpt-oss-120b"
    assert mc.emb() is mc.emb() and mc.emb()[1] == "databricks-qwen3-embedding-0-6b" and mc.llm()[0] is not mc.emb()[0]


def test_modelclient_databricks_solo_embeddings_no_exige_el_endpoint_del_llm():
    mc = ModelClient(con(LLM_PROVIDER="databricks", EMB_PROVIDER="databricks", DATABRICKS_LLM_ENDPOINT=""))
    assert mc.emb()[1] == "databricks-qwen3-embedding-0-6b"
    with pytest.raises(ProviderConfigError, match="DATABRICKS_LLM_ENDPOINT"):
        mc.llm()


class Registro:
    """Reemplaza solo `chat.completions.create` del SDK: anota lo que el cliente envía y devuelve el texto que la prueba dicta.
    NO imita un modelo: verifica los mensajes y el reintento (código nuestro). El LLM real va en test_integracion_modelos.py."""

    def __init__(self, respuestas):
        self.respuestas, self.enviados = list(respuestas), []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.enviados.append({**kw, "messages": [dict(m) for m in kw["messages"]]})
        mensaje = type("M", (), {"content": self.respuestas.pop(0)})()
        return type("R", (), {"choices": [type("C", (), {"message": mensaje})()]})()


def con_registro(proveedor, respuestas):
    mc = ModelClient(con(LLM_PROVIDER=proveedor, LLM_TEMPERATURE=0.0))
    registro = Registro(respuestas)
    mc._llm = (registro, "modelo-x")
    return mc, registro


def test_chat_json_databricks_agrega_json_al_usuario_en_la_primera_llamada_y_en_el_reintento():
    mc, reg = con_registro("databricks", ['{"ok": "no-es-bool"}', '{"ok": true}'])
    assert mc.chat_json("Eres un auditor.", "Compara A con B.", Ok) == Ok(ok=True)
    primero, segundo = reg.enviados
    assert [m["role"] for m in primero["messages"]] == ["system", "user"] and primero["messages"][0]["content"] == "Eres un auditor."
    assert primero["messages"][1]["content"].startswith("Compara A con B.") and "json" in primero["messages"][1]["content"].lower()
    assert [m["role"] for m in segundo["messages"]] == ["system", "user", "assistant", "user"]       # el reintento conserva el hilo
    assert "json" in segundo["messages"][3]["content"].lower()                                         # el último usuario también lleva «json»
    assert primero["response_format"] == segundo["response_format"] == {"type": "json_object"}
    assert primero["model"] == "modelo-x" and primero["temperature"] == 0.0


def test_chat_json_databricks_no_duplica_json_si_el_prompt_ya_lo_trae():
    mc, reg = con_registro("databricks", ['{"ok": true}'])
    mc.chat_json("s", "Devuelve el JSON pedido.", Ok)
    assert reg.enviados[0]["messages"][1]["content"] == "Devuelve el JSON pedido."


def test_chat_json_con_otro_proveedor_no_toca_el_mensaje_del_usuario():
    mc, reg = con_registro("groq", ['{"ok": true}'])
    mc.chat_json("s", "Compara A con B.", Ok)
    assert reg.enviados[0]["messages"][1]["content"] == "Compara A con B."


def test_chat_json_databricks_dos_respuestas_invalidas_abortan_como_salida_invalida():
    mc, reg = con_registro("databricks", ["no es json", "{}"])
    with pytest.raises(LLMOutputError):
        mc.chat_json("s", "u", Ok)
    assert len(reg.enviados) == 2


def test_databricks_sin_servicio_aborta_como_no_disponible_y_el_token_no_llega_al_registro(caplog):
    s = con(LLM_PROVIDER="databricks", DATABRICKS_HOST=f"https://127.0.0.1:{puerto_cerrado()}", DATABRICKS_TOKEN="dapi-personal-12345678",
            LLM_RETRIES=0, LLM_TIMEOUT_S=5.0)
    with caplog.at_level(logging.INFO):
        with pytest.raises(LLMUnavailableError) as e:
            ModelClient(s).chat_json("s", "u", Ok)
    assert "dapi-personal-12345678" not in str(e.value) and "dapi-personal-12345678" not in caplog.text


def test_databricks_en_una_app_con_oauth_inalcanzable_aborta_sin_filtrar_las_credenciales(caplog):
    s = con(LLM_PROVIDER="databricks", DATABRICKS_HOST=f"https://127.0.0.1:{puerto_cerrado()}", DATABRICKS_TOKEN="", DATABRICKS_CLIENT_ID="id-app",
            DATABRICKS_CLIENT_SECRET="clave-app-98765", LLM_RETRIES=0, LLM_TIMEOUT_S=5.0)
    t0 = time.time()
    with caplog.at_level(logging.INFO):
        with pytest.raises((LLMUnavailableError, ProviderConfigError)) as e:
            ModelClient(s).chat_json("s", "u", Ok)
    assert "clave-app-98765" not in str(e.value) and "clave-app-98765" not in caplog.text and time.time() - t0 < 30
