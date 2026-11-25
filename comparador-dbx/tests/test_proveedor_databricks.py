"""Proveedor `databricks` (modelos del propio workspace; Databricks Free no tiene Foundry). Deterministas: lo que se prueba es la configuración, el token y el
mensaje que el cliente le arma al servicio; los modelos reales se prueban en tests/test_integracion_modelos.py con LLM_PROVIDER=databricks."""
import httpx
import pytest

from backend.core.errors import ProviderConfigError
from backend.llm import client
from backend.llm.client import _TokenDatabricks, _con_json_en_el_usuario, _host_databricks, crear_cliente
from l3_ayudas import cfg

HOST = "https://dbc-1234.cloud.databricks.com"
C = cfg(DATABRICKS_HOST=HOST, DATABRICKS_TOKEN="t-personal", DATABRICKS_CLIENT_ID="", DATABRICKS_CLIENT_SECRET="",
        DATABRICKS_LLM_ENDPOINT="databricks-gpt-oss-120b", DATABRICKS_EMB_ENDPOINT="databricks-qwen3-embedding-0-6b")


def con(**cambios):
    return cfg(**{**C.__dict__, **cambios})


def test_crea_el_cliente_del_llm_y_el_de_embeddings_con_su_endpoint():
    cli, modelo = crear_cliente("databricks", C)
    assert modelo == "databricks-gpt-oss-120b" and str(cli.base_url).rstrip("/") == f"{HOST}/serving-endpoints"
    assert crear_cliente("databricks", C, embeddings=True)[1] == "databricks-qwen3-embedding-0-6b"


@pytest.mark.parametrize("cambios,falta", [({"DATABRICKS_HOST": ""}, "DATABRICKS_HOST"), ({"DATABRICKS_LLM_ENDPOINT": ""}, "DATABRICKS_LLM_ENDPOINT"),
                                           ({"DATABRICKS_HOST": "REEMPLAZAR-host"}, "DATABRICKS_HOST")])
def test_sin_configuracion_aborta_antes_de_llamar_y_dice_que_falta(cambios, falta):
    with pytest.raises(ProviderConfigError, match=falta):
        crear_cliente("databricks", con(**cambios))


def test_sin_token_personal_exige_las_credenciales_de_la_app():
    with pytest.raises(ProviderConfigError, match="DATABRICKS_CLIENT_ID"):
        crear_cliente("databricks", con(DATABRICKS_TOKEN=""))


@pytest.mark.parametrize("host,esperado", [("dbc-1.cloud.databricks.com", "https://dbc-1.cloud.databricks.com"), (HOST + "/", HOST), (HOST + "/ruta/otra", HOST)])
def test_el_host_se_normaliza_a_https(host, esperado):
    assert _host_databricks(host) == esperado


@pytest.mark.parametrize("host", ["http://dbc-1.cloud.databricks.com", "ftp://x", "https://", "https://dbc-1.cloud.databricks.com@evil.com", "https://usuario:clave@evil.com"])
def test_la_credencial_no_viaja_en_claro_ni_a_un_host_vacio(host):
    with pytest.raises(ProviderConfigError):
        _host_databricks(host)


def test_la_credencial_personal_se_usa_tal_cual_y_se_pone_en_la_cabecera():
    auth = _TokenDatabricks(C, HOST)
    peticion = next(auth.auth_flow(httpx.Request("POST", f"{HOST}/serving-endpoints/chat/completions")))
    assert peticion.headers["Authorization"] == "Bearer t-personal"


def test_en_una_app_pide_el_acceso_oauth_una_vez_y_lo_reutiliza_hasta_que_vence(monkeypatch):
    llamadas = []

    def post(url, **kw):
        llamadas.append((url, kw["data"], kw["auth"]))
        return httpx.Response(200, json={"access_token": f"acc{len(llamadas)}", "expires_in": 3600}, request=httpx.Request("POST", url))

    monkeypatch.setattr(client.httpx, "post", post)
    auth = _TokenDatabricks(con(DATABRICKS_TOKEN="", DATABRICKS_CLIENT_ID="id-app", DATABRICKS_CLIENT_SECRET="clave-app"), HOST)
    assert auth._obtener() == "acc1" and auth._obtener() == "acc1" and len(llamadas) == 1
    assert llamadas[0][0] == f"{HOST}/oidc/v1/token" and llamadas[0][1]["grant_type"] == "client_credentials" and llamadas[0][2] == ("id-app", "clave-app")
    auth._vence = 0                                              # vencido: pide uno nuevo
    assert auth._obtener() == "acc2"


def test_si_falla_la_obtencion_del_acceso_el_error_no_filtra_las_credenciales(monkeypatch):
    def post(url, **kw):
        raise httpx.ConnectError("no se pudo conectar usando clave-app-123")

    monkeypatch.setattr(client.httpx, "post", post)
    with pytest.raises(ProviderConfigError) as e:
        _TokenDatabricks(con(DATABRICKS_TOKEN="", DATABRICKS_CLIENT_ID="id-app", DATABRICKS_CLIENT_SECRET="clave-app-123"), HOST)._obtener()
    assert "clave-app-123" not in str(e.value) and "ConnectError" in str(e.value)


def test_databricks_exige_la_palabra_json_en_el_mensaje_del_usuario():
    sin = [{"role": "system", "content": "Responde en JSON."}, {"role": "user", "content": "Compara A con B."}]
    con_json = _con_json_en_el_usuario(sin)
    assert "json" in con_json[-1]["content"].lower() and con_json[-1]["content"].startswith("Compara A con B.") and sin[-1]["content"] == "Compara A con B."   # no toca el original
    ya = [{"role": "user", "content": "Devuelve un objeto JSON."}]
    assert _con_json_en_el_usuario(ya) == ya
    reintento = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "{"}, {"role": "user", "content": "corrige"}]
    assert "json" in _con_json_en_el_usuario(reintento)[-1]["content"].lower() and _con_json_en_el_usuario(reintento)[0]["content"] == "x"
