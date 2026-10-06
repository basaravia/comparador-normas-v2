"""Texto de las primeras páginas y metadatos nativos, listos para el clasificador (docs/06 §2-3)."""
from pathlib import Path

import pymupdf

MAX_CARACTERES = 6000  # el clasificador solo necesita la portada
MAX_VALOR = 200        # tope por metadato nativo: lo controla quien sube el archivo


def texto_primeras_paginas(ruta: Path, paginas: int = 2) -> str:
    with pymupdf.open(ruta) as doc:
        texto = "\n".join(p.get_text("text") for p in doc[:paginas])
    return texto.strip()[:MAX_CARACTERES]


def metadatos_limpios(nativos: dict) -> dict:
    """Metadatos nativos sin vacíos, sin caracteres de control y con longitud acotada."""
    limpios = {}
    for clave, valor in nativos.items():
        valor = "".join(c for c in str(valor or "") if c.isprintable()).strip()[:MAX_VALOR]
        if valor and clave != "format":
            limpios[clave] = valor
    return limpios
