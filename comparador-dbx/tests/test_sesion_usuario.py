"""Sesión por usuario, PDF efímero y multicarga (docs/14 #37 y #38). Todo determinista: ningún modelo de lenguaje ni de embeddings interviene.

La orquestación de `procesar()` se prueba cambiando solo `_procesar_doc` (la lectura con Docling, que no es un modelo de lenguaje) por una función mínima;
la prueba con Docling real va aparte y marcada `integracion`.
"""
import logging
import os
import tempfile
import time
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.api import rutas
from backend.api.schemas import ComparacionOut, DocumentoOut, JobOut
from backend.config import settings
from backend.core import sesiones
from backend.core.errors import ComparadorError
from backend.core.sesiones import Comparacion, Doc, SesionesLlenas
from backend.engine import servicio
from backend.main import app

CORREO_A, CORREO_B = "auditora.a@banco.test", "auditor.b@banco.test"


def de(correo: str) -> dict:
    return {"x-forwarded-email": correo}


@pytest.fixture(autouse=True)
def sin_sesiones_previas():
    """Cada prueba parte sin sesiones vivas (el estado es global del proceso)."""
    def vaciar():
        for s in list(sesiones._SESIONES.values()):
            sesiones._borrar(s)
        sesiones._SESIONES.clear()
        sesiones._POR_HUELLA.clear()
    vaciar()
    yield
    vaciar()


def ajustar(monkeypatch, **cambios):
    """Cambia valores de configuración en todos los módulos que los leen."""
    nuevo = replace(settings, **cambios)
    for modulo in (rutas, main, sesiones, servicio):
        monkeypatch.setattr(modulo, "settings", nuevo)
    return nuevo


@pytest.fixture
def identidad(monkeypatch):
    monkeypatch.setenv("DATABRICKS_APP_NAME", "comparador-test")
    return ajustar(monkeypatch, TRUST_PROXY_IDENTITY=True)


@pytest.fixture
def web():
    with TestClient(app) as c:
        c.get("/api/session")
        yield c


@pytest.fixture
def web_id(identidad):
    with TestClient(app) as c:
        yield c


def sesion_de(correo: str):
    return sesiones.crear(sesiones.huella_de(correo))


# ───────────────────────── identidad ─────────────────────────

def test_dos_correos_no_se_ven_documentos_trabajos_comparaciones_excel_ni_miniaturas(web_id):
    assert len(web_id.post("/api/samples/load", headers=de(CORREO_A)).json()) == 2
    a = sesion_de(CORREO_A)
    job = servicio._job(a, "procesamiento")
    a.comparaciones["c1"] = Comparacion(out=ComparacionOut(id="c1", estado="listo"), entrada=object())
    id_seccion = a.docs["D1"].secciones[0].id
    assert web_id.get("/api/comparisons/c1", headers=de(CORREO_A)).status_code == 200
    assert web_id.get("/api/session", headers=de(CORREO_B)).json()["documentos"] == []
    for ruta, codigo in ((f"/api/jobs/{job.job_id}", "ERR-JOB-404"), ("/api/comparisons/c1", "ERR-CMP-404"), ("/api/comparisons/c1/excel", "ERR-CMP-404"),
                         (f"/api/sections/{id_seccion}", "ERR-SEC-404"), ("/api/documents/D1/pages/1/thumb", "ERR-DOC-001")):
        r = web_id.get(ruta, headers=de(CORREO_B))
        assert r.status_code in (404, 422) and r.json()["codigo"] == codigo, ruta
    assert web_id.post(f"/api/jobs/{job.job_id}/cancel", headers=de(CORREO_B)).json()["codigo"] == "ERR-JOB-404"
    assert web_id.get("/api/sections/tree", params={"tipo": "normativa"}, headers=de(CORREO_B)).json() == []
    assert len(web_id.get("/api/session", headers=de(CORREO_A)).json()["documentos"]) == 2          # lo de A sigue intacto


def test_mismo_correo_con_mayusculas_y_espacios_es_la_misma_sesion(web_id):
    web_id.post("/api/samples/load", headers=de(CORREO_A))
    ts = web_id.get("/api/session", headers=de(CORREO_A)).json()["iniciada_ts"]
    for variante in (" AUDITORA.A@Banco.Test ", "Auditora.A@banco.test"):
        s = web_id.get("/api/session", headers=de(variante)).json()
        assert len(s["documentos"]) == 2 and s["iniciada_ts"] == ts and s["usuario"] == CORREO_A
    assert len(sesiones._SESIONES) == 1


@pytest.mark.parametrize("cabeceras", [
    {},                                                                       # ausente
    {"x-forwarded-email": ""},                                                # vacía
    {"x-forwarded-email": "sin-arroba"},
    {"x-forwarded-email": "a@b@c.com"},
    {"x-forwarded-email": "a b@c.com"},
    {"x-forwarded-email": "a@\x07c.com"},                                     # carácter de control
    {"x-forwarded-email": "a" * 250 + "@b.com"},                              # más de 254 caracteres
    [("x-forwarded-email", "a@b.com"), ("x-forwarded-email", "c@d.com")],     # duplicada
])
def test_sin_identidad_valida_responde_401_sin_repetir_el_valor(web_id, cabeceras):
    for metodo, ruta in (("get", "/api/session"), ("post", "/api/samples/load"), ("get", "/api/settings")):
        r = getattr(web_id, metodo)(ruta, headers=cabeceras)
        assert r.status_code == 401 and r.json()["codigo"] == "ERR-SES-003" and "identificar tu cuenta" in r.json()["mensaje"]
        assert "sin-arroba" not in r.text and "c@d.com" not in r.text and "a@b.com" not in r.text
    assert not sesiones._SESIONES


def test_con_la_bandera_apagada_la_cabecera_falsificada_se_ignora(web):
    s = web.get("/api/session", headers=de("falso@banco.test")).json()
    assert s["usuario"] == "Sesión local" and not sesiones._POR_HUELLA and "falso@banco.test" not in str(s)


def test_con_la_bandera_encendida_la_cookie_de_otra_sesion_se_ignora(monkeypatch, web):
    web.post("/api/samples/load")
    cookie = web.cookies.get("session_id")
    ajustar(monkeypatch, TRUST_PROXY_IDENTITY=True)
    monkeypatch.setenv("DATABRICKS_APP_NAME", "comparador-test")
    r = web.get("/api/session", headers=de(CORREO_A))
    assert r.json()["documentos"] == [] and r.json()["usuario"] == CORREO_A         # la sesión con documentos era de la cookie, no del usuario
    assert "set-cookie" not in r.headers                                            # no se emite session_id
    assert sesiones._SESIONES[sesiones._POR_HUELLA[sesiones.huella_de(CORREO_A)]].id != cookie


def test_bandera_encendida_sin_databricks_app_name_no_arranca(monkeypatch):
    ajustar(monkeypatch, TRUST_PROXY_IDENTITY=True)
    monkeypatch.delenv("DATABRICKS_APP_NAME", raising=False)
    import asyncio

    async def arrancar():
        async with main.ciclo_de_vida(app):                                          # el evento de arranque de FastAPI
            pass
    with pytest.raises(RuntimeError, match="DATABRICKS_APP_NAME"):
        asyncio.run(arrancar())
    monkeypatch.setenv("DATABRICKS_APP_NAME", "x")
    with TestClient(app) as c:
        assert c.get("/api/session", headers=de(CORREO_A)).status_code == 200


def test_borrar_todo_con_identidad_solo_borra_la_sesion_del_usuario(web_id):
    web_id.post("/api/samples/load", headers=de(CORREO_A))
    web_id.post("/api/samples/load", headers=de(CORREO_B))
    assert web_id.delete("/api/session", headers=de(CORREO_A)).status_code == 200
    assert web_id.get("/api/session", headers=de(CORREO_A)).json()["documentos"] == []
    assert len(web_id.get("/api/session", headers=de(CORREO_B)).json()["documentos"]) == 2


def test_ni_el_correo_ni_su_hash_aparecen_en_los_logs(web_id, caplog):
    caplog.set_level(logging.DEBUG)
    web_id.post("/api/samples/load", headers=de(CORREO_A))
    web_id.get("/api/session", headers=de("malo"))
    web_id.get("/api/session", headers=de(CORREO_B))
    s = sesion_de(CORREO_A)
    s.ultimo_uso = 0
    sesiones.limpiar_expiradas()                                                    # expira y registra
    web_id.delete("/api/session", headers=de(CORREO_B))
    for secreto in (CORREO_A, CORREO_B, sesiones.huella_de(CORREO_A), sesiones.huella_de(CORREO_B), "malo"):
        assert secreto not in caplog.text
    assert "Sesión expirada" in caplog.text                                        # sí se registró el evento, sin datos del usuario


def test_la_carpeta_de_la_sesion_no_lleva_el_correo_ni_el_hash(web_id):
    web_id.get("/api/session", headers=de(CORREO_A))
    s = sesion_de(CORREO_A)
    assert CORREO_A.split("@")[0] not in str(s.dir) and sesiones.huella_de(CORREO_A) not in str(s.dir) and s.id != sesiones.huella_de(CORREO_A)


# ───────────────────────── protección de origen ─────────────────────────

@pytest.mark.parametrize("sitio", ["cross-site", "same-site", "Cross-Site"])
def test_post_y_delete_de_otro_origen_dan_403(web, sitio):
    for metodo, ruta in (("post", "/api/samples/load"), ("delete", "/api/session"), ("put", "/api/settings")):
        r = getattr(web, metodo)(ruta, headers={"Sec-Fetch-Site": sitio})
        assert r.status_code == 403 and r.json()["codigo"] == "ERR-SEG-001" and "origen" in r.json()["mensaje"]
        assert r.headers["x-content-type-options"] == "nosniff"
    assert web.get("/api/session").json()["documentos"] == []                       # el POST bloqueado no cargó nada
    assert web.get("/api/session", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200           # GET no cambia estado


@pytest.mark.parametrize("cabeceras", [{"Sec-Fetch-Site": "same-origin"}, {"Sec-Fetch-Site": "none"}, {}])
def test_post_del_mismo_origen_o_sin_cabecera_pasa(web, cabeceras):
    assert web.post("/api/samples/load", headers=cabeceras).status_code == 200


# ───────────────────────── quitar documento ─────────────────────────

def poner_doc_con_pdf(s, doc_id="D50", estado="listo", tipo="normativa"):
    carpeta = s.dir / doc_id
    carpeta.mkdir()
    pdf = carpeta / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    s.docs[doc_id] = Doc(out=DocumentoOut(id=doc_id, nombre="a.pdf", paginas=1, tipo=tipo, estado=estado), ruta=pdf)
    return pdf


def test_quitar_documento_procesado_descarta_comparacion_excel_indices_y_miniaturas(web):
    web.post("/api/samples/load")
    s = sesiones.obtener(web.cookies["session_id"])
    pdf = poner_doc_con_pdf(s)
    excel = s.dir / "papel_c1xxxxxx.xlsx"
    excel.write_bytes(b"x")
    s.comparaciones["c1xxxxxxzz"] = Comparacion(out=ComparacionOut(id="c1xxxxxxzz", estado="listo"), entrada=object())
    s.indexados, s.indice_norma, s.indice_manual = {"D1", "D2", "D50"}, object(), object()
    servicio._MINIATURAS[(s.id, "D50", 1)] = b"png"
    assert web.get("/api/session").json()["comparacion_id"] == "c1xxxxxxzz"

    r = web.delete("/api/documents/D50")
    assert r.status_code == 200 and [d["id"] for d in r.json()["documentos"]] == ["D1", "D2"] and r.json()["comparacion_id"] is None
    assert not pdf.exists() and not pdf.parent.exists() and not excel.exists()
    assert (s.id, "D50", 1) not in servicio._MINIATURAS
    assert s.indexados == set() and s.indice_norma is None and s.indice_manual is None
    assert web.get("/api/comparisons/c1xxxxxxzz/excel").json()["codigo"] == "ERR-CMP-404"          # el Excel anterior ya no se descarga
    assert web.get("/api/comparisons/c1xxxxxxzz").status_code == 422


def test_quitar_un_documento_sin_procesar_no_toca_la_comparacion_vigente(web):
    web.post("/api/samples/load")
    s = sesiones.obtener(web.cookies["session_id"])
    pdf = poner_doc_con_pdf(s, estado="cargado")
    s.comparaciones["c1"] = Comparacion(out=ComparacionOut(id="c1", estado="listo"), entrada=object())
    assert web.delete("/api/documents/D50").status_code == 200
    assert not pdf.parent.exists() and web.get("/api/session").json()["comparacion_id"] == "c1"


def test_quitar_con_trabajo_activo_o_en_ingesta_da_409_y_no_borra(web):
    web.post("/api/samples/load")
    s = sesiones.obtener(web.cookies["session_id"])
    pdf = poner_doc_con_pdf(s, estado="cargado")
    s.jobs["J1"] = JobOut(job_id="J1", tipo="comparacion", estado="en_curso")
    r = web.delete("/api/documents/D50")
    assert r.status_code == 409 and r.json()["codigo"] == "ERR-DOC-006" and pdf.exists() and "D50" in s.docs
    s.jobs["J1"].estado = "listo"
    s.docs["D50"].ingesta = True
    assert web.delete("/api/documents/D50").status_code == 409 and pdf.exists()
    s.docs["D50"].ingesta = False
    assert web.delete("/api/documents/D50").status_code == 200 and not pdf.exists()


@pytest.mark.parametrize("ruta", ["D1/../x", "..", "%2e%2e", "D1%2f..%2f..", "D99", "D1x", "d1", "D1234567", "%2e%2e%2fD1"])
def test_quitar_con_ids_raros_o_ajenos_se_rechaza_y_no_borra_nada_fuera(web, ruta):
    web.post("/api/samples/load")
    s = sesiones.obtener(web.cookies["session_id"])
    afuera = s.dir.parent / "comparador_sesion_vecina_test"
    afuera.mkdir(exist_ok=True)
    (afuera / "dato.txt").write_text("x")
    (s.dir / "sentinela.txt").write_text("x")
    try:
        r = web.delete(f"/api/documents/{ruta}")
        assert r.status_code in (404, 405, 422) and r.status_code != 200
        assert len(web.get("/api/session").json()["documentos"]) == 2
        assert (afuera / "dato.txt").exists() and (s.dir / "sentinela.txt").exists()
    finally:
        import shutil
        shutil.rmtree(afuera, ignore_errors=True)


def test_quitar_el_documento_de_otra_sesion_da_el_mismo_error_que_uno_inexistente():
    with TestClient(app) as a, TestClient(app) as b:
        a.get("/api/session"), b.get("/api/session")
        a.post("/api/samples/load")
        ajeno, inexistente = b.delete("/api/documents/D1"), b.delete("/api/documents/D77")
        assert ajeno.status_code == inexistente.status_code == 404 and ajeno.json() == inexistente.json() and ajeno.json()["codigo"] == "ERR-DOC-001"
        assert len(a.get("/api/session").json()["documentos"]) == 2


# ───────────────────────── expulsión, expiración, limpieza ─────────────────────────

def test_expulsion_no_cae_una_con_trabajo_ni_una_reciente_y_sin_candidatas_es_503(monkeypatch):
    ajustar(monkeypatch, MAX_SESIONES=2, SESION_EXPULSABLE_MIN=60)
    vieja, reciente = sesiones.crear(), sesiones.crear()
    vieja.ultimo_uso = time.time() - 3 * 3600
    reciente.ultimo_uso = time.time() - 10 * 60
    servicio._job(vieja, "procesamiento")                                           # la vieja tiene un trabajo en cola
    with pytest.raises(SesionesLlenas):
        sesiones.crear()
    assert vieja.id in sesiones._SESIONES and reciente.id in sesiones._SESIONES and vieja.dir.exists()
    vieja.jobs.clear()
    vieja.docs["D1"] = Doc(out=DocumentoOut(id="D1", nombre="x.pdf"), ingesta=True)         # ingesta en curso también protege
    with pytest.raises(SesionesLlenas):
        sesiones.crear()
    vieja.docs.clear()
    nueva = sesiones.crear()
    assert vieja.id not in sesiones._SESIONES and not vieja.dir.exists() and reciente.id in sesiones._SESIONES and nueva.id in sesiones._SESIONES


def test_se_expulsa_la_mas_inactiva_entre_las_candidatas(monkeypatch):
    ajustar(monkeypatch, MAX_SESIONES=3, SESION_EXPULSABLE_MIN=60)
    a, b, c = sesiones.crear(), sesiones.crear(), sesiones.crear()
    a.ultimo_uso, b.ultimo_uso, c.ultimo_uso = time.time() - 2 * 3600, time.time() - 5 * 3600, time.time() - 4 * 3600
    sesiones.crear()
    assert b.id not in sesiones._SESIONES and a.id in sesiones._SESIONES and c.id in sesiones._SESIONES


def test_el_503_por_servidor_lleno_sale_por_la_api(monkeypatch):
    ajustar(monkeypatch, MAX_SESIONES=1, SESION_EXPULSABLE_MIN=60)
    with TestClient(app) as a, TestClient(app) as b:
        assert a.get("/api/session").status_code == 200
        r = b.get("/api/session")
        assert r.status_code == 503 and r.json()["codigo"] == "ERR-SES-002"


def test_la_expiracion_respeta_el_trabajo_activo_y_usa_48_horas(monkeypatch):
    assert settings.SESSION_TTL_HOURS == 48
    ocupada, ociosa, reciente = sesiones.crear(), sesiones.crear(), sesiones.crear()
    ocupada.ultimo_uso = ociosa.ultimo_uso = time.time() - 49 * 3600
    reciente.ultimo_uso = time.time() - 47 * 3600
    servicio._job(ocupada, "comparacion")
    sesiones.limpiar_expiradas()
    assert ocupada.id in sesiones._SESIONES and reciente.id in sesiones._SESIONES and ociosa.id not in sesiones._SESIONES and not ociosa.dir.exists()


def test_la_cookie_dura_lo_que_la_retencion(web):
    web.cookies.clear()
    r = web.get("/api/session")
    assert f"Max-Age={48 * 3600}" in r.headers["set-cookie"]


def test_limpieza_de_arranque_no_toca_enlaces_simbolicos_ni_otros_prefijos(monkeypatch, tmp_path):
    base, afuera = tmp_path / "tmp", tmp_path / "afuera"
    base.mkdir(), afuera.mkdir()
    (afuera / "valioso.txt").write_text("x")
    huerfana = base / f"{sesiones.PREFIJO}abc"
    huerfana.mkdir()
    (huerfana / "a.pdf").write_text("x")
    enlace = base / f"{sesiones.PREFIJO}enlace"
    enlace.symlink_to(afuera, target_is_directory=True)
    otro = base / "otro_prefijo_abc"
    otro.mkdir()
    archivo = base / f"{sesiones.PREFIJO}archivo"
    archivo.write_text("x")
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    assert sesiones.limpiar_tmp_huerfanos() == 1
    assert not huerfana.exists() and enlace.is_symlink() and (afuera / "valioso.txt").exists() and otro.exists() and archivo.exists()


def test_la_limpieza_corre_al_arrancar_solo_con_la_bandera(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    huerfana = tmp_path / f"{sesiones.PREFIJO}vieja"
    huerfana.mkdir()
    with TestClient(app):                                                           # bandera apagada (por defecto): no toca nada
        assert huerfana.exists()
    ajustar(monkeypatch, LIMPIAR_TMP_AL_ARRANCAR=True)
    with TestClient(app):
        assert not huerfana.exists()


# ───────────────────────── PDF efímero ─────────────────────────

def pdf_de_prueba(hacer_pdf, s, doc_id, tipo="normativa", nombre="a.pdf"):
    """Un PDF real de una página dentro de la carpeta de la sesión, como lo deja `subir`."""
    origen = hacer_pdf(nombre)
    carpeta = s.dir / doc_id
    carpeta.mkdir()
    destino = carpeta / nombre
    destino.write_bytes(origen.read_bytes())
    s.docs[doc_id] = Doc(out=DocumentoOut(id=doc_id, nombre=nombre, paginas=1, tipo=tipo), ruta=destino, sha256="x" + doc_id)
    return destino


def esperar(job, segundos=20):
    limite = time.time() + segundos
    while job.estado not in ("listo", "error", "cancelado") and time.time() < limite:
        time.sleep(0.05)
    return job


def leer_minimo(doc, job, base, peso):
    """Sustituye solo la lectura con Docling: deja una sección y el documento listo para comparar."""
    doc.secciones = []
    doc.clasificacion = {}


def test_el_pdf_se_borra_al_quedar_listo_y_la_miniatura_da_err_doc_001(web, hacer_pdf, monkeypatch):
    monkeypatch.setattr(servicio, "_procesar_doc", leer_minimo)
    s = sesiones.obtener(web.cookies["session_id"])
    pdf = pdf_de_prueba(hacer_pdf, s, "D1")
    servicio._MINIATURAS[(s.id, "D1", 1)] = b"png"
    assert web.get("/api/documents/D1/pages/1/thumb").status_code == 200                # antes de procesar hay PDF
    job = esperar(servicio.procesar(s, ["D1"], cliente=None))
    assert job.estado == "listo" and s.docs["D1"].out.estado == "listo"
    assert s.docs["D1"].ruta is None and not pdf.exists() and not pdf.parent.exists()
    assert (s.id, "D1", 1) not in servicio._MINIATURAS
    r = web.get("/api/documents/D1/pages/1/thumb")
    assert r.status_code == 404 and r.json() == {"codigo": "ERR-DOC-001", "mensaje": "El PDF de «a.pdf» ya no está en la aplicación; solo se conserva su contenido preparado."}
    assert sesiones.trabajo_activo(s) is None


def test_el_pdf_se_conserva_si_falla_y_se_puede_reintentar(web, hacer_pdf, monkeypatch):
    def falla(doc, job, base, peso):
        raise servicio.ComparacionError("ERR-EXT-001", "No pudimos leer este documento.")
    monkeypatch.setattr(servicio, "_procesar_doc", falla)
    s = sesiones.obtener(web.cookies["session_id"])
    pdf = pdf_de_prueba(hacer_pdf, s, "D1")
    job = esperar(servicio.procesar(s, ["D1"], cliente=None))
    d = s.docs["D1"]
    assert job.estado == "error" and d.out.estado == "error" and d.ruta == pdf and pdf.exists()
    assert sesiones.trabajo_activo(s) is None
    monkeypatch.setattr(servicio, "_procesar_doc", leer_minimo)                      # reintento: acepta el documento en error con su PDF en disco
    job2 = esperar(servicio.procesar(s, ["D1"], cliente=None))
    assert job2.estado == "listo" and d.out.estado == "listo" and d.out.error is None and d.ruta is None and not pdf.exists()


def test_cancelar_conserva_el_pdf_del_que_no_se_leyo_y_borra_el_ya_leido(web, hacer_pdf, monkeypatch):
    def lee_y_cancelan(doc, job, base, peso):
        s.cancelados.add(job.job_id)                                                # el auditor cancela mientras se lee el primero
    monkeypatch.setattr(servicio, "_procesar_doc", lee_y_cancelan)
    s = sesiones.obtener(web.cookies["session_id"])
    p1, p2 = pdf_de_prueba(hacer_pdf, s, "D1", nombre="a.pdf"), pdf_de_prueba(hacer_pdf, s, "D2", nombre="b.pdf")
    job = esperar(servicio.procesar(s, ["D1", "D2"], cliente=None))
    assert job.estado == "cancelado" and s.docs["D1"].out.estado == "listo" and s.docs["D2"].out.estado == "cargado"
    assert not p1.exists() and p2.exists() and s.docs["D2"].ruta == p2


def test_un_fallo_imprevisto_no_deja_el_trabajo_colgado(web, hacer_pdf, monkeypatch):
    monkeypatch.setattr(servicio, "_procesar_doc", leer_minimo)
    def revienta(*_):
        raise OSError("disco")
    monkeypatch.setattr(servicio, "_borrar_pdf", revienta)
    s = sesiones.obtener(web.cookies["session_id"])
    pdf_de_prueba(hacer_pdf, s, "D1")
    job = esperar(servicio.procesar(s, ["D1"], cliente=None))
    assert job.estado == "error" and not job.cancelable and sesiones.trabajo_activo(s) is None


def test_un_documento_que_no_se_pudo_clasificar_no_guarda_el_pdf_ni_cuenta_para_el_tope(web):
    s = sesiones.obtener(web.cookies["session_id"])
    r = web.post("/api/documents", files=[("archivos", ("malo.pdf", b"esto no es un pdf", "application/pdf"))])
    assert r.json()[0]["estado"] == "error" and not (s.dir / "D1").exists() and servicio.ocupan_cupo(s) == 0


@pytest.mark.integracion
def test_procesar_un_pdf_real_con_docling_borra_el_pdf(web, hacer_pdf):
    """Docling real (no usa el LLM ni embeddings: con un solo tipo de documento no se indexa)."""
    s = sesiones.obtener(web.cookies["session_id"])
    pdf = pdf_de_prueba(hacer_pdf, s, "D1")
    job = esperar(servicio.procesar(s, ["D1"], cliente=None), segundos=600)
    assert job.estado == "listo" and s.docs["D1"].ruta is None and not pdf.exists()


# ───────────────────────── tope, ejemplo, un trabajo a la vez ─────────────────────────

def test_cargar_ejemplo_repetido_no_duplica(web):
    primera = web.post("/api/samples/load").json()
    segunda = web.post("/api/samples/load").json()
    assert len(primera) == 2 and [d["id"] for d in segunda] == [d["id"] for d in primera]
    assert len(web.get("/api/session").json()["documentos"]) == 2


def test_cargar_ejemplo_respeta_el_tope_y_los_documentos_en_error_no_cuentan(web, monkeypatch):
    ajustar(monkeypatch, MAX_DOCS_SESION=2)
    s = sesiones.obtener(web.cookies["session_id"])
    s.docs["D90"] = Doc(out=DocumentoOut(id="D90", nombre="roto.pdf", estado="error"))
    assert servicio.ocupan_cupo(s) == 0
    assert len(web.post("/api/samples/load").json()) == 2                           # con 1 fallido y tope 2, el ejemplo (2) cabe
    web.delete("/api/session")
    web.get("/api/session")
    s2 = sesiones.obtener(web.cookies["session_id"])
    s2.docs["D91"] = Doc(out=DocumentoOut(id="D91", nombre="otro.pdf", tipo="normativa"))
    r = web.post("/api/samples/load")
    assert r.status_code == 422 and r.json()["codigo"] == "ERR-ING-004" and len(s2.docs) == 1       # no se cargó ninguno a medias


def test_subir_en_el_tope_da_el_texto_nuevo_de_err_ing_004(web, monkeypatch):
    ajustar(monkeypatch, MAX_DOCS_SESION=0)
    r = web.post("/api/documents", files=[("archivos", ("a.pdf", b"x", "application/pdf"))])
    assert r.status_code == 422 and r.json() == {"codigo": "ERR-ING-004", "mensaje": "Llegaste al máximo de 0 documentos. Quita alguno de la lista para agregar otro."}


def test_cambiar_el_tipo_de_un_documento_ya_procesado_da_el_texto_nuevo_de_err_doc_003(web):
    web.post("/api/samples/load")
    r = web.patch("/api/documents/D1", json={"tipo": "manual_control"})
    assert r.json() == {"codigo": "ERR-DOC-003", "mensaje": "Este documento ya se procesó. Para cambiar su tipo, quítalo y cárgalo de nuevo."}


def test_get_session_informa_el_trabajo_activo(web):
    s = sesiones.obtener(web.cookies["session_id"])
    assert web.get("/api/session").json()["trabajo_activo"] is None
    s.jobs["J1"] = JobOut(job_id="J1", tipo="procesamiento", estado="en_curso")
    assert web.get("/api/session").json()["trabajo_activo"] == {"id": "J1", "tipo": "procesamiento", "comparacion_id": None}
    s.jobs["J1"].estado = "listo"
    s.jobs["J2"] = JobOut(job_id="J2", tipo="comparacion", estado="en_cola", comparacion_id="c9")
    assert web.get("/api/session").json()["trabajo_activo"] == {"id": "J2", "tipo": "comparacion", "comparacion_id": "c9"}      # id = job_id (para sondear); comparacion_id aparte


def test_un_segundo_proceso_con_trabajo_activo_da_409_err_job_002(web):
    web.post("/api/samples/load")
    s = sesiones.obtener(web.cookies["session_id"])
    s.jobs["J1"] = JobOut(job_id="J1", tipo="procesamiento", estado="en_curso")
    r = web.post("/api/documents/process", json={"doc_ids": ["D1"]})
    assert r.status_code == 409 and r.json() == {"codigo": "ERR-JOB-002", "mensaje": "Ya hay un proceso en marcha con tu cuenta. Espera a que termine."}
    from tests.test_api import hojas
    n = [h["id"] for h in hojas(web.get("/api/sections/tree", params={"tipo": "normativa"}).json()[0]["nodos"])][:1]
    m = [h["id"] for h in hojas(web.get("/api/sections/tree", params={"tipo": "manual_control"}).json()[0]["nodos"]) if h["seleccionada"]][:1]
    r = web.post("/api/comparisons", json={"articulo_ids": n, "seccion_ids": m})            # una comparación tampoco arranca durante un procesamiento
    assert r.status_code == 409 and r.json()["codigo"] == "ERR-JOB-002"
    assert os.path.exists(s.dir)
