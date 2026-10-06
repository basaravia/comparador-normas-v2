"""Validación de PDFs antes de procesarlos (docs/06 §1, docs/05 mensajes de error).

Orden pensado para no gastar recursos con archivos hostiles: primero tamaño y cabecera
(sin abrir el archivo), después páginas y, al final, detección de escaneo.
"""
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from backend.config import settings


@dataclass
class Validacion:
    ok: bool
    codigo: str | None = None       # ERR-ING-001..003, solo si no es ok
    mensaje: str | None = None      # mensaje de negocio para el auditor
    paginas: int = 0
    sha256: str = ""                # clave de caché por sesión
    advertencia: str | None = None  # el PDF se acepta, pero el auditor debe saberlo
    metadatos: dict = field(default_factory=dict)  # metadatos nativos del PDF


def rechazo(codigo: str, mensaje: str) -> Validacion:
    return Validacion(ok=False, codigo=codigo, mensaje=mensaje)


def nombre_seguro(nombre: str) -> str:
    """Solo el nombre del archivo, sin rutas ni caracteres raros (evita path traversal).
    Si es largo, se acorta el nombre y se conserva la extensión."""
    limpio = Path(re.sub(r"[^\w.\- ]", "_", Path(nombre).name))
    if not limpio.stem.strip("."):  # vacío, ".." o "..."
        return "documento.pdf"
    return limpio.stem[:100] + limpio.suffix[:10]


def validar_pdf(ruta: Path) -> Validacion:
    ruta = Path(ruta)
    s = settings

    if ruta.stat().st_size > s.MAX_MB * 1024**2:
        return rechazo("ERR-ING-002", f"El archivo supera el máximo de {s.MAX_PAGES} páginas o {s.MAX_MB} MB. "
                                      "Divídelo o consulta con el equipo de soporte.")

    with open(ruta, "rb") as f:  # un PDF real empieza por %PDF-, sea cual sea la extensión
        cabecera = f.read(5)
    no_abre = rechazo("ERR-ING-003", "No pudimos abrir este archivo. Verifica que sea un PDF válido y sin contraseña.")
    if cabecera != b"%PDF-":
        return no_abre

    try:
        with pymupdf.open(ruta) as doc:
            if doc.needs_pass or doc.page_count == 0:
                return no_abre
            if doc.page_count > s.MAX_PAGES:
                return rechazo("ERR-ING-002", f"El archivo supera el máximo de {s.MAX_PAGES} páginas o {s.MAX_MB} MB. "
                                              "Divídelo o consulta con el equipo de soporte.")
            # Escaneo: proporción de páginas con texto útil.
            con_texto = sum(len(p.get_text("text").strip()) >= 50 for p in doc)
            if con_texto / doc.page_count < s.SCAN_TEXT_RATIO:
                # Reparado y con poco texto: probablemente truncado, no escaneado.
                if doc.is_repaired:
                    return no_abre
                return rechazo("ERR-ING-001", "Este documento parece ser una imagen escaneada. "
                                              "Por ahora solo podemos leer PDFs con texto seleccionable.")
            # Muchos PDFs no traen su tabla interna de referencias y MuPDF los repara al abrirlos:
            # si el texto alcanza, se aceptan con advertencia (docs/14 #21).
            aviso = ("El PDF tenía su estructura interna incompleta y se reparó al abrirlo. "
                     "Revisa que estén todas las páginas.") if doc.is_repaired else None
            return Validacion(ok=True, paginas=doc.page_count, sha256=hashlib.sha256(ruta.read_bytes()).hexdigest(),
                              metadatos=dict(doc.metadata or {}), advertencia=aviso)
    except Exception:  # PDF corrupto o malformado: pymupdf lanza varios tipos de error
        return no_abre
