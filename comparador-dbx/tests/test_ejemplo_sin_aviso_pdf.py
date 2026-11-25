"""D-53 (decisión del usuario, 25 nov 2026): los documentos del ejemplo vienen marcados `es_ejemplo` para que la interfaz no les muestre el aviso «el PDF no queda guardado»."""
import pytest
from fastapi.testclient import TestClient

from backend.api.schemas import DocumentoOut
from backend.core import sesiones
from backend.engine import servicio
from backend.main import app


def test_los_documentos_del_ejemplo_vienen_marcados_como_ejemplo():
    s = sesiones.crear()
    try:
        docs = servicio.cargar_ejemplo(s)
        assert docs and all(d.es_ejemplo for d in docs)
        assert all(d.es_ejemplo for d in (x.out for x in s.docs.values()))      # también en lo que guarda la sesión, no solo en la respuesta
    finally:
        sesiones.reiniciar(s.id)


@pytest.fixture
def web():
    with TestClient(app) as c:
        c.get("/api/session")
        yield c


def test_la_api_real_entrega_es_ejemplo_al_cargar_el_ejemplo_y_en_la_sesion(web):
    cargados = web.post("/api/samples/load").json()
    assert cargados and all(d["es_ejemplo"] is True for d in cargados)
    assert all(d["es_ejemplo"] is True for d in web.post("/api/samples/load").json())                    # repetir la carga no pierde la marca
    en_sesion = web.get("/api/session").json()["documentos"]
    assert len(en_sesion) == len(cargados) and all(d["es_ejemplo"] is True for d in en_sesion)           # recargar la pantalla (GET de la sesión) conserva la marca


def test_la_api_real_un_pdf_subido_no_es_ejemplo_aunque_conviva_con_el_ejemplo(web, monkeypatch):
    # La clasificación del PDF usa el LLM (cubierta en integración); aquí solo importa la marca, así que se entrega un resultado de ingesta ya clasificado.
    monkeypatch.setattr(servicio, "ingerir", lambda ruta, cliente: {"archivo": ruta.name, "ok": True, "paginas": 3, "tipo": "normativa", "metadatos": {}, "sha256": "h"})
    web.post("/api/samples/load")
    r = web.post("/api/documents", files=[("archivos", ("mio.pdf", b"x", "application/pdf"))])
    assert r.status_code == 200 and r.json()[0]["es_ejemplo"] is False
    marcas = {d["nombre"]: d["es_ejemplo"] for d in web.get("/api/session").json()["documentos"]}
    assert marcas["mio.pdf"] is False and sum(marcas.values()) == len(marcas) - 1                          # solo el PDF del auditor lleva el aviso


def test_un_archivo_invalido_tampoco_se_marca_como_ejemplo(web):
    d = web.post("/api/documents", files=[("archivos", ("malo.pdf", b"no es pdf", "application/pdf"))]).json()[0]
    assert d["estado"] == "error" and d["es_ejemplo"] is False


def test_un_documento_normal_no_es_ejemplo_y_el_campo_viaja_en_la_api():
    d = DocumentoOut(id="D1", nombre="a.pdf")
    assert d.es_ejemplo is False
    assert "es_ejemplo" in d.model_dump()
