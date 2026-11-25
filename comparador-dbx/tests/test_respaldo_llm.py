"""Respaldo del LLM (decisión del usuario, 25 nov 2026): Groq → Databricks → OpenRouter. Deterministas: se reemplaza solo el transporte del SDK (los clientes de
prueba devuelven una respuesta fija o fallan como lo hace cada proveedor); los modelos reales se prueban en tests/test_integracion_modelos.py."""
from types import SimpleNamespace

import pytest

from backend.core.errors import LLMUnavailableError, ProviderConfigError
from backend.llm import client
from backend.llm.client import ModelClient, crear_cliente
from l3_ayudas import cfg


class RateLimitError(Exception):          # el SDK las llama así; `clasificar` solo mira el nombre del tipo
    pass


class AuthenticationError(Exception):
    pass


class APIConnectionError(Exception):
    pass


GROQ_DIARIO = RateLimitError("Error code: 429 - Rate limit reached for model (TPD): Limit 200000. Please try again in 8m36.672s.")
GROQ_MINUTO = RateLimitError("Error code: 429 - Rate limit reached for model (TPM): Limit 8000. Please try again in 8.1075s.")


def falso(nombre: str, falla: Exception | None = None):
    """Cliente con la forma del SDK: `.chat.completions.create(**kw)`; cuenta sus llamadas y guarda lo último que recibió."""
    llamadas: list[dict] = []

    def create(**kw):
        llamadas.append(kw)
        if falla is not None:
            raise falla
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=f'{{"de": "{nombre}"}}'))])

    return SimpleNamespace(nombre=nombre, llamadas=llamadas, chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.fixture
def armar(monkeypatch):
    """Devuelve `(ModelClient, clientes)` con groq → databricks → openrouter; `fallas` dice cuáles fallan y con qué."""
    def _armar(fallas: dict[str, Exception] | None = None, **cambios):
        fallas = fallas or {}
        clientes = {n: falso(n, fallas.get(n)) for n in ("groq", "databricks", "openrouter")}
        monkeypatch.setattr(client, "crear_cliente", lambda proveedor, s, embeddings=False: (clientes[proveedor], f"modelo-{proveedor}"))
        base = dict(LLM_PROVIDER="groq", LLM_FALLBACK="databricks,openrouter", LLM_FALLBACK_REINTENTO_S=300, LLM_ESPERA_LIMITE_S=20, LLM_INTENTOS_LIMITE=6)
        s = cfg(**{**base, **cambios})
        return ModelClient(s), clientes
    return _armar


def de_quien(mc: ModelClient) -> str:
    import json
    return json.loads(mc._completar([{"role": "user", "content": "hola"}]))["de"]


def test_con_el_principal_sano_los_respaldos_ni_se_tocan(armar):
    mc, c = armar()
    assert de_quien(mc) == "groq"
    assert len(c["groq"].llamadas) == 1 and not c["databricks"].llamadas and not c["openrouter"].llamadas


def test_el_limite_diario_pasa_al_respaldo_y_el_principal_se_salta_un_rato(armar):
    mc, c = armar({"groq": GROQ_DIARIO})
    assert de_quien(mc) == "databricks"
    assert len(c["groq"].llamadas) == 1
    assert de_quien(mc) == "databricks"                         # dentro de la espera de reintento no se vuelve a molestar al principal
    assert len(c["groq"].llamadas) == 1 and len(c["databricks"].llamadas) == 2


def test_pasado_el_plazo_se_vuelve_a_probar_el_principal(armar):
    mc, c = armar({"groq": GROQ_DIARIO})
    de_quien(mc)
    c["groq"].llamadas.clear()
    mc._caidos["groq"] = 0.0                                    # el plazo ya pasó
    de_quien(mc)
    assert len(c["groq"].llamadas) == 1                         # lo volvió a intentar (y, como sigue caído, usó el respaldo)


def test_un_limite_de_tasa_corto_no_cambia_de_proveedor_lo_espera_el_juez(armar):
    mc, c = armar({"groq": GROQ_MINUTO})
    with pytest.raises(LLMUnavailableError, match="RateLimitError"):
        de_quien(mc)
    assert not c["databricks"].llamadas and not c["openrouter"].llamadas and "groq" not in mc._caidos


def test_un_limite_sin_tiempo_sugerido_tampoco_cambia_de_proveedor(armar):
    mc, c = armar({"groq": RateLimitError("Error code: 429 - rate limit")})
    with pytest.raises(LLMUnavailableError):
        de_quien(mc)
    assert not c["databricks"].llamadas


@pytest.mark.parametrize("falla", [AuthenticationError("401 invalid api key"), APIConnectionError("Connection error."), TimeoutError("timed out")])
def test_una_clave_invalida_o_una_caida_pasan_al_respaldo(armar, falla):
    mc, c = armar({"groq": falla})
    assert de_quien(mc) == "databricks"


def test_si_tambien_cae_el_primer_respaldo_se_llega_a_openrouter(armar):
    mc, c = armar({"groq": GROQ_DIARIO, "databricks": APIConnectionError("sin red")})
    assert de_quien(mc) == "openrouter"
    assert [len(c[n].llamadas) for n in ("groq", "databricks", "openrouter")] == [1, 1, 1]


def test_si_caen_todos_se_lanza_el_ultimo_error_sin_ciclos(armar):
    mc, c = armar({"groq": GROQ_DIARIO, "databricks": APIConnectionError("sin red"), "openrouter": APIConnectionError("sin red 2")})
    with pytest.raises(LLMUnavailableError, match="sin red 2"):
        de_quien(mc)
    assert [len(c[n].llamadas) for n in ("groq", "databricks", "openrouter")] == [1, 1, 1]
    with pytest.raises(LLMUnavailableError):
        de_quien(mc)                                            # todos caídos: se prueban de nuevo en vez de quedarse sin nada
    assert [len(c[n].llamadas) for n in ("groq", "databricks", "openrouter")] == [2, 2, 2]


def test_sin_llm_fallback_no_hay_respaldo(armar):
    mc, c = armar({"groq": GROQ_DIARIO}, LLM_FALLBACK="")
    with pytest.raises(LLMUnavailableError):
        de_quien(mc)
    assert not c["databricks"].llamadas and len(mc._proveedores_llm()) == 1


def test_el_proveedor_principal_repetido_en_el_respaldo_se_ignora(armar):
    mc, _ = armar(LLM_FALLBACK="groq, databricks ,databricks,,openrouter")
    assert [p for p, _, _ in mc._proveedores_llm()] == ["groq", "databricks", "openrouter"]


def test_un_respaldo_sin_configurar_se_omite_pero_el_principal_mal_configurado_falla(monkeypatch, caplog):
    def crear(proveedor, s, embeddings=False):
        if proveedor == "openrouter":
            raise ProviderConfigError("Faltan variables de configuración: OPENROUTER_API_KEY")
        return falso(proveedor), f"modelo-{proveedor}"

    monkeypatch.setattr(client, "crear_cliente", crear)
    mc = ModelClient(cfg(LLM_PROVIDER="groq", LLM_FALLBACK="databricks,openrouter"))
    assert [p for p, _, _ in mc._proveedores_llm()] == ["groq", "databricks"]
    assert "OPENROUTER_API_KEY" in caplog.text                  # el aviso nombra la variable que falta

    monkeypatch.setattr(client, "crear_cliente", lambda *a, **k: (_ for _ in ()).throw(ProviderConfigError("Faltan variables de configuración: GROQ_API_KEY")))
    with pytest.raises(ProviderConfigError):
        ModelClient(cfg(LLM_PROVIDER="groq", LLM_FALLBACK="databricks"))._proveedores_llm()


def test_databricks_recibe_la_palabra_json_y_openrouter_no_se_toca(armar):
    mc, c = armar({"groq": GROQ_DIARIO, "databricks": APIConnectionError("sin red")})
    de_quien(mc)
    assert "json" in c["databricks"].llamadas[0]["messages"][-1]["content"].lower()
    assert c["openrouter"].llamadas[0]["messages"][-1]["content"] == "hola"
    assert c["openrouter"].llamadas[0]["model"] == "modelo-openrouter" and c["openrouter"].llamadas[0]["response_format"] == {"type": "json_object"}


def test_el_aviso_de_cambio_no_lleva_el_mensaje_del_proveedor(armar, caplog):
    mc, _ = armar({"groq": RateLimitError("Error code: 429 ... org_01XXXXXXXXXXXXXXXXXXXXXXXX ... Please try again in 8m36s.")})
    caplog.set_level("WARNING")
    de_quien(mc)
    avisos = [r.getMessage() for r in caplog.records if "se usa" in r.getMessage()]
    assert avisos and "org_01" not in avisos[0] and "groq" in avisos[0] and "databricks" in avisos[0]


# --- OpenRouter como proveedor ---

OR = dict(OPENROUTER_API_KEY="clave-or-ficticia", OPENROUTER_BASE_URL="https://openrouter.ai/api/v1", OPENROUTER_LLM_MODEL="google/gemma-4-31b-it:free")


def test_openrouter_crea_el_cliente_del_llm_con_su_modelo():
    cli, modelo = crear_cliente("openrouter", cfg(**OR))
    assert modelo == "google/gemma-4-31b-it:free" and str(cli.base_url).rstrip("/") == "https://openrouter.ai/api/v1"


@pytest.mark.parametrize("cambio,falta", [({"OPENROUTER_API_KEY": ""}, "OPENROUTER_API_KEY"), ({"OPENROUTER_LLM_MODEL": ""}, "OPENROUTER_LLM_MODEL"),
                                          ({"OPENROUTER_API_KEY": "REEMPLAZAR-clave"}, "OPENROUTER_API_KEY")])
def test_openrouter_sin_clave_o_modelo_dice_que_falta(cambio, falta):
    with pytest.raises(ProviderConfigError, match=falta):
        crear_cliente("openrouter", cfg(**{**OR, **cambio}))


def test_la_clave_de_openrouter_no_viaja_en_claro():
    with pytest.raises(ProviderConfigError, match="https"):
        crear_cliente("openrouter", cfg(**{**OR, "OPENROUTER_BASE_URL": "http://openrouter.ai/api/v1"}))


def test_openrouter_no_sirve_para_embeddings():
    with pytest.raises(ProviderConfigError, match="embeddings"):
        crear_cliente("openrouter", cfg(**OR), embeddings=True)


def test_la_clave_de_openrouter_se_oculta_del_registro_y_de_los_repr():
    from backend.config import es_secreto, redact
    assert es_secreto("OPENROUTER_API_KEY") and "clave-or-ficticia" not in repr(cfg(**OR))            # repr=False
    clave = "sk-or-v1-" + "ab12cd34" * 8                                                              # el formato real de OpenRouter
    assert clave not in redact(f"401 con la clave {clave} en la cabecera")


# --- barrera de OpenRouter y registro de quién juzgó (appsec, 25 nov 2026) ---

def test_openrouter_no_se_admite_en_el_stage_mvp_sin_una_decision_explicita(monkeypatch):
    monkeypatch.setenv("STAGE", "mvp")
    with pytest.raises(ProviderConfigError, match="mvp"):
        crear_cliente("openrouter", cfg(**OR))
    cli, _ = crear_cliente("openrouter", cfg(**{**OR, "PERMITIR_OPENROUTER": True}))             # con la bandera sí
    assert cli is not None


@pytest.mark.parametrize("stage", ["dev", "sandbox", ""])
def test_openrouter_si_se_admite_fuera_de_mvp(monkeypatch, stage):
    monkeypatch.setenv("STAGE", stage)
    assert crear_cliente("openrouter", cfg(**OR))[1] == OR["OPENROUTER_LLM_MODEL"]


@pytest.mark.parametrize("url", ["https://openrouter.ai@otro-host.test/api/v1", "https://usuario:clave@otro-host.test/api/v1", "https://", "ftp://openrouter.ai/api/v1"])
def test_la_direccion_de_openrouter_no_puede_llevar_usuario_ni_otro_esquema(url):
    with pytest.raises(ProviderConfigError):
        crear_cliente("openrouter", cfg(**{**OR, "OPENROUTER_BASE_URL": url}))


def test_el_cliente_cuenta_cuantas_llamadas_resolvio_cada_proveedor(armar):
    mc, _ = armar({"groq": GROQ_DIARIO})
    for _ in range(3):
        de_quien(mc)
    assert dict(mc.usos) == {"databricks": 3}                 # el que cayó no suma
    mc._caidos["groq"] = 0.0
    mc._cadena[0][1].llamadas.clear()
    de_quien(mc)
    assert mc.usos["databricks"] == 4 and "groq" not in mc.usos


def test_si_todo_va_por_el_principal_solo_cuenta_el_principal(armar):
    mc, _ = armar()
    de_quien(mc)
    de_quien(mc)
    assert dict(mc.usos) == {"groq": 2}
