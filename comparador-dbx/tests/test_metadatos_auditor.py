"""P-05 (docs/14, D0): los metadatos que edita el auditor ganan a los que sugirió el modelo, y el procesamiento posterior no los pisa. Deterministas:
la clasificación del PDF (que sugiere los metadatos) se sustituye por una respuesta fija; lo que se prueba es la prioridad entre «lo que sugirió el modelo» y «lo que escribió la persona»."""
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.api import rutas
from backend.api.schemas import DocumentoOut, Metadatos
from backend.config import settings
from backend.core import sesiones
from backend.core.sesiones import Doc
from backend.engine import servicio
from backend.main import app


@pytest.fixture(autouse=True)
def sin_sesiones_previas():
    def vaciar():
        for s in list(sesiones._SESIONES.values()):
            sesiones._borrar(s)
        sesiones._SESIONES.clear()
        sesiones._POR_HUELLA.clear()
    vaciar()
    yield
    vaciar()


@pytest.fixture
def web():
    with TestClient(app) as c:
        c.get("/api/session")
        yield c


def sugerencia_del_modelo(monkeypatch):
    def falsa(ruta: Path, cliente):
        return {"archivo": ruta.name, "ok": True, "paginas": 3, "tipo": "normativa", "sha256": "h",
                "metadatos": {"titulo_oficial": "Título que sugirió el modelo", "entidad_emisora": "Entidad que sugirió el modelo", "numero_norma": "N-1"}}
    monkeypatch.setattr(servicio, "ingerir", falsa)


def esperar(job, segundos=20):
    limite = time.time() + segundos
    while job.estado not in ("listo", "error", "cancelado") and time.time() < limite:
        time.sleep(0.05)
    return job


def test_la_ingesta_guarda_lo_que_sugirio_el_modelo(web, monkeypatch):
    sugerencia_del_modelo(monkeypatch)
    fila = web.post("/api/documents", files=[("archivos", ("n.pdf", b"x", "application/pdf"))]).json()[0]
    assert fila["metadatos"]["titulo_oficial"] == "Título que sugirió el modelo" and fila["metadatos"]["numero_norma"] == "N-1"


def test_lo_que_edita_el_auditor_gana_y_lo_no_editado_se_conserva(web, monkeypatch):
    sugerencia_del_modelo(monkeypatch)
    doc_id = web.post("/api/documents", files=[("archivos", ("n.pdf", b"x", "application/pdf"))]).json()[0]["id"]
    r = web.patch(f"/api/documents/{doc_id}", json={"metadatos": {"titulo_oficial": "Título corregido por la persona"}})
    meta = r.json()["metadatos"]
    assert r.status_code == 200
    assert meta["titulo_oficial"] == "Título corregido por la persona"                         # gana la persona
    assert meta["entidad_emisora"] == "Entidad que sugirió el modelo" and meta["numero_norma"] == "N-1"       # solo se cambia lo enviado


def test_un_campo_que_la_persona_deja_vacio_no_lo_repone_el_modelo(web, monkeypatch):
    sugerencia_del_modelo(monkeypatch)
    doc_id = web.post("/api/documents", files=[("archivos", ("n.pdf", b"x", "application/pdf"))]).json()[0]["id"]
    meta = web.patch(f"/api/documents/{doc_id}", json={"metadatos": {"numero_norma": None}}).json()["metadatos"]
    assert meta["numero_norma"] is None                                                      # vaciarlo es una edición: no vuelve el valor del modelo


def test_procesar_no_pisa_los_metadatos_editados(web, hacer_pdf, monkeypatch):
    s = sesiones.obtener(web.cookies["session_id"])
    carpeta = s.dir / "D1"
    carpeta.mkdir()
    destino = carpeta / "n.pdf"
    destino.write_bytes(hacer_pdf("n.pdf").read_bytes())
    editado = Metadatos(titulo_oficial="Escrito por la persona", entidad_emisora="Entidad de la persona")
    s.docs["D1"] = Doc(out=DocumentoOut(id="D1", nombre="n.pdf", paginas=1, tipo="normativa", metadatos=editado), ruta=destino, sha256="xD1")

    def leer_minimo(doc, job, base, peso):
        doc.secciones = []
        doc.clasificacion = {}

    monkeypatch.setattr(servicio, "_procesar_doc", leer_minimo)
    job = esperar(servicio.procesar(s, ["D1"], cliente=None))
    assert job.estado == "listo"
    assert s.docs["D1"].out.metadatos.titulo_oficial == "Escrito por la persona" and s.docs["D1"].out.metadatos.entidad_emisora == "Entidad de la persona"


def test_despues_de_procesar_ya_no_se_puede_editar_el_documento(web, hacer_pdf, monkeypatch):
    s = sesiones.obtener(web.cookies["session_id"])
    s.docs["D1"] = Doc(out=DocumentoOut(id="D1", nombre="n.pdf", paginas=1, tipo="normativa", estado="listo"))
    r = web.patch("/api/documents/D1", json={"metadatos": {"titulo_oficial": "tarde"}})
    assert r.json()["codigo"] == "ERR-DOC-003" and "ya se procesó" in r.json()["mensaje"]          # el PATCH solo vale antes de procesar: así lo editado no puede quedar a medias
