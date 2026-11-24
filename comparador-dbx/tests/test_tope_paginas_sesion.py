"""Tope de páginas sumadas por sesión (MAX_PAGES_SESION, appsec S-18). Deterministas: la ingesta (lectura y clasificación del PDF) se sustituye por una
función que devuelve un número de páginas conocido, porque lo que se prueba es la aritmética del tope y su atomicidad, no al clasificador."""
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.api import rutas
from backend.api.schemas import DocumentoOut
from backend.config import settings
from backend.core import sesiones
from backend.core.sesiones import Doc, SesionPerdida
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


def ajustar(monkeypatch, **cambios):
    nuevo = replace(settings, **cambios)
    for modulo in (rutas, main, sesiones, servicio):
        monkeypatch.setattr(modulo, "settings", nuevo)
    return nuevo


def con_paginas(monkeypatch, paginas: int, puerta: threading.Barrier | None = None):
    """Sustituye la ingesta por una que siempre dice «PDF válido de N páginas»; con `puerta` fuerza que varias suban a la vez."""
    def falsa(ruta: Path, cliente):
        if puerta is not None:
            puerta.wait(timeout=5)
        return {"archivo": ruta.name, "ok": True, "paginas": paginas, "tipo": "normativa", "metadatos": {}, "sha256": "h" + ruta.name}
    monkeypatch.setattr(servicio, "ingerir", falsa)


def sesion_de(web):
    return sesiones.obtener(web.cookies["session_id"])


def test_el_valor_por_defecto_cabe_al_menos_un_pdf_del_maximo_permitido():
    assert settings.MAX_PAGES_SESION >= settings.MAX_PAGES        # un solo PDF de MAX_PAGES páginas siempre cabe


def test_un_documento_que_pasa_el_tope_queda_como_error_y_no_cuenta_para_el_cupo(web, monkeypatch):
    ajustar(monkeypatch, MAX_PAGES_SESION=10)
    con_paginas(monkeypatch, 6)
    s = sesion_de(web)
    primero = servicio.subir(s, "a.pdf", b"x", None)
    segundo = servicio.subir(s, "b.pdf", b"x", None)
    assert primero.estado != "error" and primero.paginas == 6
    assert segundo.estado == "error" and segundo.error.codigo == "ERR-ING-005"
    assert "12 páginas" in segundo.error.mensaje and "10" in segundo.error.mensaje and "Quita algún documento" in segundo.error.mensaje
    assert servicio.ocupan_cupo(s) == 1 and not (s.dir / segundo.id).exists()          # no cuenta como documento y su PDF no se queda


def test_justo_en_el_tope_cabe(web, monkeypatch):
    ajustar(monkeypatch, MAX_PAGES_SESION=10)
    s = sesion_de(web)
    con_paginas(monkeypatch, 6)
    servicio.subir(s, "a.pdf", b"x", None)
    con_paginas(monkeypatch, 4)
    cuarto = servicio.subir(s, "b.pdf", b"x", None)
    assert cuarto.estado != "error" and servicio.paginas_en_sesion(s) == 10


def test_los_documentos_fallidos_no_suman_paginas(web, monkeypatch):
    ajustar(monkeypatch, MAX_PAGES_SESION=10)
    con_paginas(monkeypatch, 8)
    s = sesion_de(web)
    s.docs["D90"] = Doc(out=DocumentoOut(id="D90", nombre="roto.pdf", paginas=99, estado="error"))
    assert servicio.paginas_en_sesion(s) == 0
    assert servicio.subir(s, "a.pdf", b"x", None).estado != "error"


def test_quitar_un_documento_libera_sus_paginas(web, monkeypatch):
    ajustar(monkeypatch, MAX_PAGES_SESION=10)
    con_paginas(monkeypatch, 6)
    s = sesion_de(web)
    primero = servicio.subir(s, "a.pdf", b"x", None)
    assert servicio.subir(s, "b.pdf", b"x", None).estado == "error"
    s.docs.pop(primero.id)                                                             # equivale a «Quitar»
    assert servicio.subir(s, "c.pdf", b"x", None).estado != "error"


def test_dos_subidas_simultaneas_no_pueden_pasarse_del_tope(web, monkeypatch):
    ajustar(monkeypatch, MAX_PAGES_SESION=10)
    con_paginas(monkeypatch, 6, puerta=threading.Barrier(2))           # las dos terminan la ingesta a la vez; el tope se decide después, bajo el bloqueo
    s = sesion_de(web)
    resultados = []

    def subir(nombre):
        resultados.append(servicio.subir(s, nombre, b"x", None))

    hilos = [threading.Thread(target=subir, args=(n,)) for n in ("a.pdf", "b.pdf")]
    [h.start() for h in hilos]
    [h.join(timeout=10) for h in hilos]
    estados = sorted(r.estado == "error" for r in resultados)
    assert estados == [False, True] and servicio.paginas_en_sesion(s) == 6        # una entra y la otra se rechaza: nunca las dos (12 > 10)


def test_por_la_api_el_documento_rechazado_llega_como_error_de_negocio(web, monkeypatch):
    ajustar(monkeypatch, MAX_PAGES_SESION=5)
    con_paginas(monkeypatch, 4)
    primero = web.post("/api/documents", files=[("archivos", ("a.pdf", b"x", "application/pdf"))])
    segundo = web.post("/api/documents", files=[("archivos", ("b.pdf", b"x", "application/pdf"))])
    assert primero.status_code == 200 and primero.json()[0]["estado"] != "error"
    fila = segundo.json()[0]
    assert segundo.status_code == 200 and fila["estado"] == "error" and fila["error"]["codigo"] == "ERR-ING-005"
    assert "Traceback" not in fila["error"]["mensaje"] and "páginas" in fila["error"]["mensaje"]          # lenguaje de negocio, sin trazas


# --- S-22: «Borrar todo» durante la clasificación y tope de cargar_ejemplo bajo concurrencia -------------------------------------------

def test_borrar_todo_durante_la_clasificacion_no_deja_el_pdf_ni_registra_el_documento(web, monkeypatch):
    s = sesion_de(web)

    def ingesta_y_llega_borrar_todo(ruta: Path, cliente):
        with s.lock:
            s.cerrada = True                                   # lo que hace DELETE /api/session antes de borrar
        return {"archivo": ruta.name, "ok": True, "paginas": 3, "tipo": "normativa", "metadatos": {}, "sha256": "h"}

    monkeypatch.setattr(servicio, "ingerir", ingesta_y_llega_borrar_todo)
    with pytest.raises(SesionPerdida):
        servicio.subir(s, "a.pdf", b"x", None)
    assert not any(p.suffix == ".pdf" for p in s.dir.rglob("*")) if s.dir.exists() else True        # ningún PDF queda en /tmp
    assert s.docs == {}                                         # ni el documento ni el cupo reservado quedan registrados


def test_la_subida_que_falla_o_se_cancela_tambien_libera_su_carpeta(web, monkeypatch):
    s = sesion_de(web)

    def cae(ruta, cliente):
        raise RuntimeError("falla la clasificación")

    monkeypatch.setattr(servicio, "ingerir", cae)
    with pytest.raises(RuntimeError):
        servicio.subir(s, "a.pdf", b"x", None)
    assert s.docs == {} and not (s.dir / "D1").exists()


def test_dos_cargas_del_ejemplo_a_la_vez_no_pasan_el_tope_ni_lo_duplican(web, monkeypatch):
    ajustar(monkeypatch, MAX_DOCS_SESION=2)
    s = sesion_de(web)
    resultados, errores = [], []

    def cargar():
        try:
            resultados.append(servicio.cargar_ejemplo(s))
        except Exception as e:                                  # noqa: BLE001
            errores.append(e)

    hilos = [threading.Thread(target=cargar) for _ in range(4)]
    [h.start() for h in hilos]
    [h.join(timeout=10) for h in hilos]
    assert not errores and len(s.docs) == 2 and servicio.ocupan_cupo(s) == 2
