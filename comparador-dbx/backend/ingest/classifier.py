"""Clasificación del documento y extracción de metadatos con el LLM (docs/06 §3).

El LLM solo propone: la decisión de preseleccionar el tipo la toma el código (`tipo_sugerido`).
"""
import json
import logging
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.config import cargar_prompt, rellenar_prompt, settings
from backend.core.errors import LLMOutputError
from backend.ingest.pdf_metadata import metadatos_limpios, texto_primeras_paginas
from backend.ingest.validation import nombre_seguro, validar_pdf
from backend.llm.client import ModelClient


log = logging.getLogger(__name__)


class MetadatosLLM(BaseModel):
    tipo_documento: Literal["normativa", "manual_control", "desconocido"]
    confianza_tipo: float = Field(ge=0, le=1)
    entidad_emisora: str | None = None
    titulo_oficial: str | None = None
    libro: str | None = None
    titulo: str | None = None
    capitulo: str | None = None
    seccion: str | None = None
    numero_norma: str | None = None
    fecha_emision: date | None = None
    fecha_vigencia: date | None = None
    version: str | None = None
    area_responsable: str | None = None
    evidencia_tipo: str

    @field_validator("*", mode="before")
    @classmethod
    def acotar_texto(cls, v):
        """Lo que sale del modelo viene del PDF: se acota para que no crezca sin límite hacia la UI y el Excel."""
        return v[:500] if isinstance(v, str) else v

    @field_validator("fecha_emision", "fecha_vigencia", mode="before")
    @classmethod
    def fecha_invalida_es_none(cls, v):
        """Una fecha que no se puede leer queda vacía en lugar de invalidar toda la respuesta."""
        try:
            return date.fromisoformat(str(v)) if v else None
        except ValueError:
            return None


SIN_RESPUESTA = MetadatosLLM(tipo_documento="desconocido", confianza_tipo=0,
                             evidencia_tipo="El modelo no devolvió una respuesta válida")


def clasificar(cliente: ModelClient, nombre: str, nativos: dict, texto: str) -> MetadatosLLM:
    """Una llamada por documento. Si el JSON no es válido ni tras el reintento: todo vacío, sin bloquear."""
    sistema, plantilla = cargar_prompt("clasificador")
    usuario = rellenar_prompt(plantilla, nombre_archivo=nombre,
                              metadatos_nativos=json.dumps(nativos, ensure_ascii=False),
                              texto_primeras_paginas=texto)
    try:
        return cliente.chat_json(sistema, usuario, MetadatosLLM)
    except LLMOutputError:
        return SIN_RESPUESTA


def tipo_sugerido(r: MetadatosLLM) -> str | None:
    """Decisión del código: solo se preselecciona el tipo si el modelo está suficientemente seguro."""
    if r.tipo_documento != "desconocido" and r.confianza_tipo >= settings.TYPE_CONFIDENCE:
        return r.tipo_documento
    return None  # el auditor elige; la fila se resalta


def ingerir(ruta: Path, cliente: ModelClient) -> dict:
    """Valida un PDF y, si es válido, lo clasifica. Devuelve la fila que verá el auditor."""
    ruta = Path(ruta)
    nombre = nombre_seguro(ruta.name)
    v = validar_pdf(ruta)
    if not v.ok:
        return {"archivo": nombre, "ok": False, "codigo": v.codigo, "mensaje": v.mensaje}

    nativos = metadatos_limpios(v.metadatos)
    log.info("Ingesta: clasificando %s (%d págs)", nombre, v.paginas)
    r = clasificar(cliente, nombre, nativos, texto_primeras_paginas(ruta))
    log.info("Ingesta: %s → %s (confianza %.2f)", nombre, r.tipo_documento, r.confianza_tipo)
    excluir = {"tipo_documento", "confianza_tipo", "evidencia_tipo"}
    metadatos = {k: val for k, val in r.model_dump(mode="json", exclude=excluir).items() if val}  # fechas como texto
    # Prioridad: editado por el auditor (llega en la API) > LLM > nativo del PDF > vacío.
    metadatos.setdefault("titulo_oficial", nativos.get("title"))
    metadatos.setdefault("entidad_emisora", nativos.get("author"))
    return {"archivo": nombre, "ok": True, "paginas": v.paginas, "sha256": v.sha256, "advertencia": v.advertencia,
            "tipo": tipo_sugerido(r), "tipo_llm": r.tipo_documento, "confianza": r.confianza_tipo,
            "evidencia": r.evidencia_tipo, "metadatos": {k: v for k, v in metadatos.items() if v}}
