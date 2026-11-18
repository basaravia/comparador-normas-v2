"""Huecos de prueba de la sesión por usuario (docs/14 #37/#38, RF-01, RF-02, RF-16, RF-20, RF-22..RF-24, RNF-01, RNF-12). Sin modelos.

Igual que tests/test_sesion_usuario.py: solo se cambia `_procesar_doc` (la lectura con Docling, que no es un modelo de lenguaje) por una función
que espera una señal, para tener un trabajo "en curso" de forma determinista.
"""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend.api.schemas import DocumentoOut
from backend.core import sesiones
from backend.core.sesiones import Doc, SesionesLlenas
from backend.engine import servicio
from backend.main import app
from tests.test_sesion_usuario import CORREO_A, ajustar, de, esperar, leer_minimo, pdf_de_prueba, sin_sesiones_previas, web, web_id, identidad  # noqa: F401


def lectura_que_espera(senal: threading.Event, leidos: list):
    """Sustituye la lectura con Docling: anota el documento y espera la señal (como mucho 10 s)."""
    def leer(doc, job, base, peso):
        leidos.append(doc.out.id)
        senal.wait(10)
        doc.secciones, doc.clasificacion = [], {}
    return leer


# ───────────────────────── carreras con el lock ─────────────────────────

def test_dos_procesar_a_la_vez_solo_arranca_uno(web, hacer_pdf, monkeypatch):
    senal, leidos = threading.Event(), []
    monkeypatch.setattr(servicio, "_procesar_doc", lectura_que_espera(senal, leidos))
    s = sesiones.obtener(web.cookies["session_id"])
    pdf_de_prueba(hacer_pdf, s, "D1", nombre="a.pdf")
    pdf_de_prueba(hacer_pdf, s, "D2", nombre="b.pdf")
    barrera, resultados = threading.Barrier(2), []

    def lanzar(doc_id):
        barrera.wait()
        try:
            resultados.append(servicio.procesar(s, [doc_id], cliente=None))
        except servicio.ComparacionError as e:
            resultados.append(e.codigo)
    hilos = [threading.Thread(target=lanzar, args=(i,)) for i in ("D1", "D2")]
    try:
        [h.start() for h in hilos]
        [h.join(5) for h in hilos]
        jobs = [r for r in resultados if not isinstance(r, str)]
        assert len(jobs) == 1 and resultados.count("ERR-JOB-002") == 1
    finally:
        senal.set()
    assert esperar(jobs[0]).estado == "listo"


def test_una_subida_en_curso_reserva_su_cupo(web, monkeypatch):
    ajustar(monkeypatch, MAX_DOCS_SESION=1)
    s = sesiones.obtener(web.cookies["session_id"])
    s.docs["D1"] = Doc(out=DocumentoOut(id="D1", nombre="subiendo.pdf"), ingesta=True)
    with pytest.raises(servicio.ComparacionError) as e:
        servicio.subir(s, "otro.pdf", b"%PDF", cliente=None)
    assert e.value.codigo == "ERR-ING-004" and list(s.docs) == ["D1"]


def test_cargar_ejemplo_dos_veces_a_la_vez_no_duplica(web, monkeypatch):
    original = servicio.clasificar_secciones

    def lenta(secs):                                     # ensancha la ventana entre la comprobación y el alta (función determinista, no un modelo)
        time.sleep(0.2)
        return original(secs)
    monkeypatch.setattr(servicio, "clasificar_secciones", lenta)
    s = sesiones.obtener(web.cookies["session_id"])
    barrera = threading.Barrier(2)

    def cargar():
        barrera.wait()
        servicio.cargar_ejemplo(s)
    hilos = [threading.Thread(target=cargar) for _ in range(2)]
    [h.start() for h in hilos]
    [h.join(10) for h in hilos]
    assert len(s.docs) == 2, [d.out.nombre for d in s.docs.values()]


# ───────────────────────── reintento y cancelación ─────────────────────────

def test_tras_cancelar_se_reintenta_el_que_quedo_sin_leer(web, hacer_pdf, monkeypatch):
    s = sesiones.obtener(web.cookies["session_id"])

    def lee_y_cancelan(doc, job, base, peso):
        servicio.cancelar(s, job.job_id)                 # la vía real de Cancelar (marca Docling para el resto)
    monkeypatch.setattr(servicio, "_procesar_doc", lee_y_cancelan)
    pdf_de_prueba(hacer_pdf, s, "D1", nombre="a.pdf")
    p2 = pdf_de_prueba(hacer_pdf, s, "D2", nombre="b.pdf")
    assert esperar(servicio.procesar(s, ["D1", "D2"], cliente=None)).estado == "cancelado"
    assert s.docs["D2"].out.estado == "cargado" and p2.exists()
    monkeypatch.setattr(servicio, "_procesar_doc", leer_minimo)
    job = esperar(servicio.procesar(s, ["D2"], cliente=None))
    assert job.estado == "listo" and s.docs["D2"].out.estado == "listo" and not p2.exists() and s.docs["D2"].ruta is None


def test_reprocesar_un_documento_ya_listo_sin_pdf_da_err_doc_001(web, hacer_pdf, monkeypatch):
    monkeypatch.setattr(servicio, "_procesar_doc", leer_minimo)
    s = sesiones.obtener(web.cookies["session_id"])
    pdf_de_prueba(hacer_pdf, s, "D1")
    esperar(servicio.procesar(s, ["D1"], cliente=None))
    r = web.post("/api/documents/process", json={"doc_ids": ["D1"]})
    assert r.json()["codigo"] == "ERR-DOC-001" and sesiones.trabajo_activo(s) is None


def test_cancelar_un_trabajo_ya_terminado_no_lo_cambia(web, hacer_pdf, monkeypatch):
    monkeypatch.setattr(servicio, "_procesar_doc", leer_minimo)
    s = sesiones.obtener(web.cookies["session_id"])
    pdf_de_prueba(hacer_pdf, s, "D1")
    job = esperar(servicio.procesar(s, ["D1"], cliente=None))
    r = web.post(f"/api/jobs/{job.job_id}/cancel")
    assert r.status_code == 200 and r.json()["estado"] == "listo" and job.job_id not in s.cancelados


def test_borrar_todo_durante_un_procesamiento_real_detiene_la_lectura_y_no_deja_archivos(web, hacer_pdf, monkeypatch):
    senal, leidos = threading.Event(), []
    monkeypatch.setattr(servicio, "_procesar_doc", lectura_que_espera(senal, leidos))
    s = sesiones.obtener(web.cookies["session_id"])
    pdf_de_prueba(hacer_pdf, s, "D1", nombre="a.pdf")
    pdf_de_prueba(hacer_pdf, s, "D2", nombre="b.pdf")
    job = servicio.procesar(s, ["D1", "D2"], cliente=None)
    try:
        limite = time.time() + 5
        while not leidos and time.time() < limite:
            time.sleep(0.02)
        assert web.delete("/api/session").status_code == 200
    finally:
        senal.set()
    assert esperar(job).estado == "cancelado" and leidos == ["D1"]                    # D2 no se llegó a leer
    assert not s.dir.exists() and sesiones.existente(s.id) is None


def test_quitar_un_documento_en_error_libera_cupo_y_borra_su_pdf(web, hacer_pdf, monkeypatch):
    def falla(doc, job, base, peso):
        raise servicio.ComparacionError("ERR-EXT-001", "No pudimos leer este documento.")
    monkeypatch.setattr(servicio, "_procesar_doc", falla)
    s = sesiones.obtener(web.cookies["session_id"])
    pdf = pdf_de_prueba(hacer_pdf, s, "D1")
    esperar(servicio.procesar(s, ["D1"], cliente=None))
    assert web.delete("/api/documents/D1").status_code == 200
    assert not pdf.parent.exists() and "D1" not in s.docs and servicio.ocupan_cupo(s) == 0


# ───────────────────────── expulsión (valores límite) ─────────────────────────

def test_expulsion_en_el_limite_exacto_si_y_un_poco_antes_no(monkeypatch):
    ajustar(monkeypatch, MAX_SESIONES=1, SESION_EXPULSABLE_MIN=60)
    a = sesiones.crear()
    a.ultimo_uso = time.time() - 60 * 60 + 30                                           # 59,5 min sin uso: aún no
    with pytest.raises(SesionesLlenas):
        sesiones.crear()
    a.ultimo_uso = time.time() - 60 * 60                                                # justo el umbral: sí
    b = sesiones.crear()
    assert a.id not in sesiones._SESIONES and b.id in sesiones._SESIONES


def test_con_el_servidor_lleno_el_mismo_usuario_vuelve_a_entrar_a_su_sesion(identidad, monkeypatch):
    ajustar(monkeypatch, TRUST_PROXY_IDENTITY=True, MAX_SESIONES=1, SESION_EXPULSABLE_MIN=60)
    with TestClient(app) as c:
        c.post("/api/samples/load", headers=de(CORREO_A))
        r = c.get("/api/session", headers=de(CORREO_A))
        assert r.status_code == 200 and len(r.json()["documentos"]) == 2
        assert c.get("/api/session", headers=de("otro@banco.test")).status_code == 503
    assert len(sesiones._SESIONES) == 1


# ───────────────────────── reenganche ─────────────────────────

def test_otra_pestana_del_mismo_usuario_se_reengancha_al_trabajo_en_curso(web_id, hacer_pdf, monkeypatch):
    senal, leidos = threading.Event(), []
    monkeypatch.setattr(servicio, "_procesar_doc", lectura_que_espera(senal, leidos))
    s = sesiones.crear(sesiones.huella_de(CORREO_A))
    pdf_de_prueba(hacer_pdf, s, "D1")
    job = servicio.procesar(s, ["D1"], cliente=None)
    try:
        with TestClient(app) as pestana:                                                # sin cookie: solo la identidad del proxy
            activo = pestana.get("/api/session", headers=de(CORREO_A)).json()["trabajo_activo"]
            assert activo == {"id": job.job_id, "tipo": "procesamiento", "comparacion_id": None}
            assert pestana.get(f"/api/jobs/{job.job_id}", headers=de(CORREO_A)).status_code == 200
            assert pestana.post("/api/documents/process", json={"doc_ids": ["D1"]}, headers=de(CORREO_A)).status_code == 409
    finally:
        senal.set()
    esperar(job)
    assert web_id.get("/api/session", headers=de(CORREO_A)).json()["trabajo_activo"] is None


def test_con_cookie_un_cliente_nuevo_con_la_misma_cookie_ve_el_trabajo(web, hacer_pdf, monkeypatch):
    senal, leidos = threading.Event(), []
    monkeypatch.setattr(servicio, "_procesar_doc", lectura_que_espera(senal, leidos))
    s = sesiones.obtener(web.cookies["session_id"])
    pdf_de_prueba(hacer_pdf, s, "D1")
    job = servicio.procesar(s, ["D1"], cliente=None)
    try:
        with TestClient(app, cookies={"session_id": s.id}) as recarga:
            assert recarga.get("/api/session").json()["trabajo_activo"]["id"] == job.job_id
    finally:
        senal.set()
    esperar(job)


# ───────────────────────── protección de origen ─────────────────────────

def test_patch_de_otro_origen_da_403_y_no_cambia_el_tipo(web):
    web.post("/api/samples/load")
    r = web.patch("/api/documents/D1", json={"tipo": "manual_control"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and r.json()["codigo"] == "ERR-SEG-001"
    assert web.get("/api/session").json()["documentos"][0]["tipo"] == "normativa"
