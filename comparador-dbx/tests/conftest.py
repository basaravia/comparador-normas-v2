"""Configuración común de las pruebas.

- DeepEval sin telemetría: nada sale a Confident AI (va antes de cualquier import).
- `comparador-dbx/` en el sys.path para importar `backend`.
- `cliente`: el ModelClient REAL del stage, solo para las pruebas de integración.
- `hacer_pdf`: genera PDFs pequeños en tmp_path con pymupdf (como notebooks/01_ingesta.ipynb).
"""
import os

os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent  # comparador-dbx/
sys.path.insert(0, str(RAIZ))

import pymupdf
import pytest

TEXTO = "Procedimiento 1.1: el area de tesoreria concilia diariamente los saldos de caja."  # > 50 caracteres


@pytest.fixture(scope="session")
def cliente():
    """ModelClient real del stage de config/.env (sandbox: Groq + Ollama). Nunca simulado."""
    from backend.llm.client import ModelClient
    return ModelClient()


@pytest.fixture
def hacer_pdf(tmp_path):
    """Crea un PDF con una página por texto ("" = página sin texto, como un escaneo)."""
    def _hacer(nombre="doc.pdf", textos=(TEXTO,), metadatos=None, **opciones_guardar):
        ruta = tmp_path / nombre
        doc = pymupdf.open()
        for texto in textos:
            pagina = doc.new_page()
            if texto:
                pagina.insert_text((40, 40), texto, fontsize=6)
        if metadatos:
            doc.set_metadata(metadatos)
        doc.save(ruta, **opciones_guardar)
        doc.close()
        return ruta
    return _hacer
