"""Huecos de QA sobre el tope de páginas por sesión (ERR-ING-005), el tope de la subida (413) y «Borrar todo» durante una subida (appsec S-18/S-22).
Deterministas: la ingesta se sustituye por una que dice «PDF válido de N páginas»; lo que se prueba es la aritmética y el orden de los pasos."""
import shutil
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.api import rutas
from backend.config import settings
from backend.core import sesiones
from backend.core.sesiones import SesionPerdida
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
    with TestClient(app, raise_server_exceptions=False) as c:
        c.get("/api/session")
        yield c


def ajustar(monkeypatch, **cambios):
    nuevo = replace(settings, **cambios)
    for modulo in (rutas, main, sesiones, servicio):
        monkeypatch.setattr(modulo, "settings", nuevo)


def con_paginas(monkeypatch, paginas: int):
    def falsa(ruta: Path, cliente):
        return {"archivo": ruta.name, "ok": True, "paginas": paginas, "tipo": "normativa", "metadatos": {}, "sha256": "h" + ruta.name}
    monkeypatch.setattr(servicio, "ingerir", falsa)


def sesion_de(web):
    return sesiones.obtener(web.cookies["session_id"])


def pdf(nombre="a.pdf"):
    return ("archivos", (nombre, b"x", "application/pdf"))


# --- ERR-ING-005 con los documentos de ejemplo cargados ---------------------------------------------------------------------------------

def test_las_paginas_del_ejemplo_cuentan_para_el_tope(web, monkeypatch):
    s = sesion_de(web)
    servicio.cargar_ejemplo(s)
    del_ejemplo = servicio.paginas_en_sesion(s)
    assert del_ejemplo == sum(d.out.paginas for d in s.docs.values()) > 0
    ajustar(monkeypatch, MAX_PAGES_SESION=del_ejemplo + 10)
    con_paginas(monkeypatch, 11)
    rechazado = servicio.subir(s, "a.pdf", b"x", None)
    assert rechazado.estado == "error" and rechazado.error.codigo == "ERR-ING-005" and f"{del_ejemplo + 11} páginas" in rechazado.error.mensaje
    con_paginas(monkeypatch, 10)
    assert servicio.subir(s, "b.pdf", b"x", None).estado != "error"           # justo en el tope, con el ejemplo ya cargado


def test_quitar_el_ejemplo_libera_sus_paginas(web, monkeypatch):
    s = sesion_de(web)
    servicio.cargar_ejemplo(s)
    ajustar(monkeypatch, MAX_PAGES_SESION=20)
    con_paginas(monkeypatch, 20)
    assert servicio.subir(s, "a.pdf", b"x", None).error.codigo == "ERR-ING-005"
    for doc_id in [i for i, d in s.docs.items() if d.out.estado != "error"]:         # «Quitar» a cada documento del ejemplo
        s.docs.pop(doc_id)
    assert servicio.subir(s, "b.pdf", b"x", None).estado != "error"


def test_un_pdf_invalido_conserva_su_propio_error_aunque_la_sesion_ya_pase_el_tope(web, monkeypatch):
    s = sesion_de(web)
    servicio.cargar_ejemplo(s)                                                   # el ejemplo no pasa por el tope de páginas: la sesión puede quedar por encima
    ajustar(monkeypatch, MAX_PAGES_SESION=1)
    monkeypatch.setattr(servicio, "ingerir", lambda ruta, cliente: {"archivo": ruta.name, "ok": False, "codigo": "ERR-ING-003", "mensaje": "El PDF está escaneado."})
    fila = servicio.subir(s, "escaneado.pdf", b"x", None)
    assert fila.estado == "error" and fila.error.codigo == "ERR-ING-003"          # el motivo real, no «tope de páginas»


def test_un_lote_por_la_api_acepta_lo_que_cabe_y_rechaza_el_resto_en_orden(web, monkeypatch):
    ajustar(monkeypatch, MAX_PAGES_SESION=10)
    con_paginas(monkeypatch, 6)
    r = web.post("/api/documents", files=[pdf("a.pdf"), pdf("b.pdf"), pdf("c.pdf")])
    assert r.status_code == 200
    assert [f["estado"] == "error" for f in r.json()].count(True) == 2           # una cabe (6) y las otras dos (12 > 10) no
    assert [f["error"]["codigo"] for f in r.json() if f["estado"] == "error"] == ["ERR-ING-005"] * 2
    assert servicio.paginas_en_sesion(sesion_de(web)) == 6


def test_el_rechazado_por_tope_no_deja_su_pdf_ni_cuenta_para_documentos(web, monkeypatch):
    ajustar(monkeypatch, MAX_PAGES_SESION=5, MAX_DOCS_SESION=2)
    con_paginas(monkeypatch, 4)
    s = sesion_de(web)
    servicio.subir(s, "a.pdf", b"x", None)
    for _ in range(3):                                                           # tres rechazos seguidos no agotan el tope de documentos (ERR-ING-004)
        assert servicio.subir(s, "b.pdf", b"x", None).error.codigo == "ERR-ING-005"
    assert servicio.ocupan_cupo(s) == 1
    assert sorted(p.name for p in s.dir.iterdir()) == ["D1"]                    # solo la carpeta del documento aceptado


# --- Tope del cuerpo de la subida: Content-Length exacto ----------------------------------------------------------------------------------

def cuerpo_multipart(relleno: int) -> tuple[bytes, dict]:
    frontera = "XfronteraX"
    cabecera = f'--{frontera}\r\nContent-Disposition: form-data; name="archivos"; filename="a.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
    cuerpo = cabecera + b"0" * relleno + f"\r\n--{frontera}--\r\n".encode()
    return cuerpo, {"content-type": f"multipart/form-data; boundary={frontera}"}


def test_content_length_justo_en_el_tope_pasa_y_un_byte_mas_se_corta(web, monkeypatch):
    cuerpo, cab = cuerpo_multipart(100)
    monkeypatch.setattr(main, "tope_subida", lambda: len(cuerpo))
    r = web.post("/api/documents", content=cuerpo, headers=cab)
    assert r.status_code == 200 and r.json()[0]["estado"] == "error"                    # llegó al validador (no es un PDF), no se cortó por tamaño
    monkeypatch.setattr(main, "tope_subida", lambda: len(cuerpo) - 1)
    r = web.post("/api/documents", content=cuerpo, headers=cab)
    assert r.status_code == 413 and r.json()["codigo"] == "ERR-ING-002"


def test_el_corte_413_lleva_cabeceras_de_seguridad_y_no_se_cachea(web, monkeypatch):
    monkeypatch.setattr(main, "tope_subida", lambda: 10)
    cuerpo, cab = cuerpo_multipart(100)
    r = web.post("/api/documents", content=cuerpo, headers=cab)
    assert r.status_code == 413
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store" and "frame-ancestors" in r.headers["content-security-policy"]


def test_sin_content_length_la_subida_sigue_llegando_al_limite_por_archivo(web, monkeypatch):
    monkeypatch.setattr(main, "tope_subida", lambda: 10)
    cuerpo, cab = cuerpo_multipart(100)
    r = web.post("/api/documents", content=(c for c in [cuerpo]), headers=cab)       # transferencia por tramos: no hay Content-Length que mirar
    assert "content-length" not in r.request.headers and r.status_code == 200          # el tope por archivo (`_leer`) es la defensa en este caso


def test_el_tope_solo_aplica_a_la_subida_de_documentos(web, monkeypatch):
    monkeypatch.setattr(main, "tope_subida", lambda: 10)
    r = web.post("/api/samples/load", content=b"0" * 100)
    assert r.status_code == 200
    r = web.get("/api/session", headers={"content-length": "99999999"})
    assert r.status_code == 200


def test_un_content_length_que_no_es_numero_no_se_corta_ni_rompe(web, monkeypatch):
    monkeypatch.setattr(main, "tope_subida", lambda: 10)
    cuerpo, cab = cuerpo_multipart(100)
    r = web.post("/api/documents", content=cuerpo, headers={**cab, "content-length": "-5"})
    assert r.status_code != 413 and r.status_code < 500


def test_el_limite_por_archivo_sigue_cortando_aunque_el_cuerpo_quepa(web, monkeypatch):
    ajustar(monkeypatch, MAX_DOCS_SESION=3, MAX_MB=1)                                   # el cuerpo cabe en 4 MiB, el archivo (1,5 MiB) no en 1
    r = web.post("/api/documents", files=[("archivos", ("a.pdf", b"0" * int(1.5 * 1024 ** 2), "application/pdf"))])
    assert r.status_code == 422 and r.json()["codigo"] == "ERR-ING-002"            # el límite por archivo responde 422 (ComparacionError); el del cuerpo entero, 413


# --- «Borrar todo» durante una subida -----------------------------------------------------------------------------------------------------

def test_borrar_todo_por_la_api_durante_la_clasificacion_responde_410_y_no_deja_pdf(web, monkeypatch):
    s = sesion_de(web)
    carpeta_sesion = s.dir

    def ingesta_y_llega_borrar_todo(ruta: Path, cliente):
        with s.lock:
            s.cerrada = True
        sesiones.reiniciar(s.id)                                    # lo que hace DELETE /api/session: saca la sesión y borra su carpeta
        return {"archivo": ruta.name, "ok": True, "paginas": 3, "tipo": "normativa", "metadatos": {}, "sha256": "h"}

    monkeypatch.setattr(servicio, "ingerir", ingesta_y_llega_borrar_todo)
    r = web.post("/api/documents", files=[pdf()])
    assert r.status_code == 410 and r.json()["codigo"] == "ERR-SES-001"
    assert not carpeta_sesion.exists() and s.docs == {}


def test_borrar_todo_justo_antes_de_guardar_el_pdf_responde_410_no_500(web, monkeypatch):
    """La sesión se cierra y su carpeta se borra entre la reserva del cupo y `mkdir` de la carpeta del documento."""
    s = sesion_de(web)
    mkdir = Path.mkdir

    def mkdir_tras_borrar_todo(self, *a, **k):                      # justo antes de crear la carpeta del documento llega «Borrar todo»
        with s.lock:
            s.cerrada = True
        shutil.rmtree(s.dir)
        return mkdir(self, *a, **k)

    monkeypatch.setattr(Path, "mkdir", mkdir_tras_borrar_todo)
    monkeypatch.setattr(servicio, "ingerir", lambda ruta, cliente: pytest.fail("no debe clasificar un PDF de una sesión borrada"))
    with pytest.raises(SesionPerdida):
        servicio.subir(s, "a.pdf", b"x", None)
    assert s.docs == {}


def test_borrar_todo_mientras_otra_subida_espera_en_ingesta_no_registra_nada(web, monkeypatch):
    """Dos subidas en vuelo; «Borrar todo» llega con las dos clasificando: ninguna se registra y ningún PDF queda."""
    s = sesion_de(web)
    dentro, sigue = threading.Barrier(3), threading.Event()

    def lenta(ruta: Path, cliente):
        dentro.wait(timeout=5)
        sigue.wait(timeout=5)
        return {"archivo": ruta.name, "ok": True, "paginas": 2, "tipo": "normativa", "metadatos": {}, "sha256": "h" + ruta.name}

    monkeypatch.setattr(servicio, "ingerir", lenta)
    errores = []

    def subir(nombre):
        try:
            servicio.subir(s, nombre, b"x", None)
        except SesionPerdida as e:
            errores.append(e)

    hilos = [threading.Thread(target=subir, args=(n,)) for n in ("a.pdf", "b.pdf")]
    [h.start() for h in hilos]
    dentro.wait(timeout=5)                                          # las dos están clasificando
    assert servicio.ocupan_cupo(s) == 2                             # y ya tienen su cupo reservado
    with s.lock:
        s.cerrada = True
    sigue.set()
    [h.join(timeout=10) for h in hilos]
    assert len(errores) == 2 and s.docs == {} and not any(p.suffix == ".pdf" for p in s.dir.rglob("*"))
