"""backend/core/errors.py — clasificación de excepciones y mensajes de negocio, sin modelo.

Las excepciones son las clases reales del SDK `openai`, construidas a mano: no se simula
ninguna respuesta del modelo, solo se comprueba a qué error del dominio se traduce cada tipo.
"""
import httpx2 as httpx  # el transporte HTTP que usa openai 3.x (dependencia del propio SDK)
import openai
import pytest

from backend.core.errors import (ComparadorError, LLMOutputError, LLMUnavailableError, ProviderConfigError,
                                 clasificar)

PETICION = httpx.Request("POST", "https://api.ejemplo.test/v1/chat/completions")


def error_http(clase, estado: int):
    return clase(f"error {estado}", response=httpx.Response(estado, request=PETICION), body=None)


@pytest.mark.parametrize("clase, estado", [
    (openai.AuthenticationError, 401),
    (openai.PermissionDeniedError, 403),
    (openai.NotFoundError, 404),
])
def test_errores_de_configuracion_abortan_como_provider_config(clase, estado):
    err = clasificar(error_http(clase, estado))
    assert type(err) is ProviderConfigError
    assert isinstance(err, LLMUnavailableError)  # también aborta la corrida
    assert clase.__name__ in str(err)            # el detalle técnico queda para el log


@pytest.mark.parametrize("exc", [
    error_http(openai.RateLimitError, 429),
    error_http(openai.InternalServerError, 500),
    openai.APIConnectionError(request=PETICION),
    openai.APITimeoutError(request=PETICION),
    ValueError("algo desconocido"),
])
def test_resto_de_errores_es_servicio_no_disponible(exc):
    err = clasificar(exc)
    assert type(err) is LLMUnavailableError
    assert type(exc).__name__ in str(err)


@pytest.mark.parametrize("err", [LLMOutputError("x"), ProviderConfigError("y"), ComparadorError("z")])
def test_un_error_del_dominio_se_devuelve_tal_cual(err):
    assert clasificar(err) is err


@pytest.mark.parametrize("clase, codigo", [
    (ComparadorError, "ERR-GEN-001"),
    (LLMUnavailableError, "ERR-LLM-001"),
    (ProviderConfigError, "ERR-CFG-001"),
    (LLMOutputError, "ERR-LLM-010"),
])
def test_para_usuario_da_codigo_y_mensaje_de_negocio_sin_detalle_tecnico(clase, codigo):
    salida = clase("Traceback: AuthenticationError gsk_secreto en https://host").para_usuario()
    assert set(salida) == {"codigo", "mensaje"}
    assert salida["codigo"] == codigo
    assert salida["mensaje"] == clase.mensaje_negocio
    assert "gsk_" not in salida["mensaje"] and "Traceback" not in salida["mensaje"]


def test_mensaje_de_servicio_no_disponible_es_el_de_docs05():
    assert LLMUnavailableError.mensaje_negocio == ("No pudimos conectarnos al servicio de análisis. "
                                                   "Intenta de nuevo en un momento.")


def test_los_codigos_son_unicos():
    clases = [ComparadorError, LLMUnavailableError, ProviderConfigError, LLMOutputError]
    assert len({c.codigo for c in clases}) == len(clases)
