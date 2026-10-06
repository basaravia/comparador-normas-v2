"""backend/ingest/classifier.py — lo determinista: esquema MetadatosLLM, tipo_sugerido y el rechazo de ingerir.

`clasificar` y el camino feliz de `ingerir` llaman al LLM: se prueban con el modelo real en
tests/test_integracion_modelos.py.
"""
from dataclasses import replace
from datetime import date

import pytest
from pydantic import ValidationError

from backend.config import settings
from backend.ingest.classifier import SIN_RESPUESTA, MetadatosLLM, ingerir, tipo_sugerido
from backend.llm.client import ModelClient


def metadatos(**campos) -> MetadatosLLM:
    base = {"tipo_documento": "manual_control", "confianza_tipo": 0.9, "evidencia_tipo": "procedimientos internos"}
    return MetadatosLLM.model_validate({**base, **campos})


# --- Fechas -------------------------------------------------------------------------

@pytest.mark.parametrize("valor, esperado", [
    ("2026-10-06", date(2026, 10, 6)),
    ("2026-13-01", None),        # mes inválido
    ("2026-02-30", None),        # día inválido
    ("31/12/2026", None),        # formato no ISO
    ("diciembre de 2026", None),
    ("", None),
    (None, None),
    (20261006, date(2026, 10, 6)),  # número: se lee como texto ISO básico
    (12345, None),
])
def test_fecha_invalida_queda_vacia_sin_invalidar_la_respuesta(valor, esperado):
    r = metadatos(fecha_emision=valor, fecha_vigencia=valor)
    assert r.fecha_emision == esperado and r.fecha_vigencia == esperado


# --- Acotar textos a 500 --------------------------------------------------------------

@pytest.mark.parametrize("campo", ["entidad_emisora", "titulo_oficial", "libro", "titulo", "capitulo", "seccion",
                                   "numero_norma", "version", "area_responsable", "evidencia_tipo"])
def test_textos_del_modelo_se_acotan_a_500(campo):
    assert len(getattr(metadatos(**{campo: "a" * 5000}), campo)) == 500


def test_texto_de_500_queda_igual():
    assert metadatos(titulo="b" * 500).titulo == "b" * 500


# --- Esquema estricto -------------------------------------------------------------------

@pytest.mark.parametrize("campos", [
    {"tipo_documento": "contrato"},
    {"tipo_documento": "manual_control" + " " * 600},  # el acotado no lo vuelve válido
    {"confianza_tipo": 1.01},
    {"confianza_tipo": -0.01},
    {"evidencia_tipo": None},
])
def test_respuesta_fuera_del_esquema_no_valida(campos):
    with pytest.raises(ValidationError):
        metadatos(**campos)


def test_confianza_en_los_extremos_valida():
    assert metadatos(confianza_tipo=0).confianza_tipo == 0
    assert metadatos(confianza_tipo=1).confianza_tipo == 1


def test_valida_el_json_tal_como_llega_del_modelo():
    r = MetadatosLLM.model_validate_json('{"tipo_documento": "normativa", "confianza_tipo": 0.8, '
                                         '"fecha_emision": "no sé", "evidencia_tipo": "art. 1"}')
    assert r.tipo_documento == "normativa" and r.fecha_emision is None and r.libro is None


# --- tipo_sugerido (decisión del código, umbral TYPE_CONFIDENCE) -------------------------

def test_tipo_sugerido_en_el_umbral_se_preselecciona():
    assert tipo_sugerido(metadatos(tipo_documento="normativa", confianza_tipo=settings.TYPE_CONFIDENCE)) == "normativa"


def test_tipo_sugerido_bajo_el_umbral_lo_elige_el_auditor():
    assert tipo_sugerido(metadatos(confianza_tipo=settings.TYPE_CONFIDENCE - 0.01)) is None


def test_tipo_sugerido_con_confianza_total():
    assert tipo_sugerido(metadatos(tipo_documento="manual_control", confianza_tipo=1)) == "manual_control"


def test_desconocido_nunca_se_preselecciona():
    assert tipo_sugerido(metadatos(tipo_documento="desconocido", confianza_tipo=1)) is None


def test_sin_respuesta_queda_desconocido_y_sin_preseleccion():
    assert SIN_RESPUESTA.tipo_documento == "desconocido" and SIN_RESPUESTA.confianza_tipo == 0
    assert tipo_sugerido(SIN_RESPUESTA) is None


# --- ingerir: un PDF inválido se rechaza ANTES de llamar al modelo --------------------------

def test_ingerir_rechaza_sin_llamar_al_modelo(tmp_path):
    ruta = tmp_path / "mal<nombre>.pdf"
    ruta.write_text("no es un pdf")
    # Cliente real sin proveedor válido: si ingerir lo usara, lanzaría ProviderConfigError.
    sin_modelo = ModelClient(replace(settings, LLM_PROVIDER="ninguno", EMB_PROVIDER="ninguno"))
    fila = ingerir(ruta, sin_modelo)
    assert fila == {"archivo": "mal_nombre_.pdf", "ok": False, "codigo": "ERR-ING-003",
                    "mensaje": "No pudimos abrir este archivo. Verifica que sea un PDF válido y sin contraseña."}
