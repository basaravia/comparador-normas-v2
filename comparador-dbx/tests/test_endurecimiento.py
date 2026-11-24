"""Endurecimiento BAJA de appsec (S-16): cabeceras también en los 500, CSP sin 'unsafe-inline' en style-src y tope del cuerpo de la subida. Deterministas."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.api import rutas
from backend.config import settings
from backend.core import sesiones
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


def ajustar(monkeypatch, **cambios):
    nuevo = replace(settings, **cambios)
    for modulo in (rutas, main, sesiones, servicio):
        monkeypatch.setattr(modulo, "settings", nuevo)


def test_un_error_500_lleva_las_cabeceras_de_seguridad_y_no_se_cachea(monkeypatch):
    def explota(*a, **k):
        raise RuntimeError("fallo interno con /ruta/secreta")

    monkeypatch.setattr(servicio, "cargar_ejemplo", explota)
    with TestClient(app, raise_server_exceptions=False) as c:
        c.get("/api/session")
        r = c.post("/api/samples/load")
    assert r.status_code == 500
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY" and r.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"] and r.headers["cache-control"] == "no-store"
    assert "ruta/secreta" not in r.text and "RuntimeError" not in r.text                 # nada técnico en pantalla (CLAUDE.md regla 11)


def test_la_csp_no_permite_estilos_en_linea_salvo_atributos():
    csp = main.CABECERAS["Content-Security-Policy"]
    directiva = {p.split()[0]: p.split()[1:] for p in csp.split(";") if p.strip()}
    assert "'unsafe-inline'" not in directiva["style-src"]                               # ni <style> ni hojas incrustadas
    assert directiva["style-src-attr"] == ["'unsafe-inline'"]                           # los atributos style="" de React (ancho de las barras) siguen permitidos
    assert directiva["default-src"] == ["'self'"] and "script-src" not in directiva       # los scripts siguen limitados a 'self' por default-src


def test_una_subida_mayor_que_la_sesion_se_corta_antes_de_leer_el_cuerpo(monkeypatch):
    ajustar(monkeypatch, MAX_DOCS_SESION=1, MAX_MB=1)                                    # tope = (1 × 1 + 1) MiB = 2 MiB
    leidos = []
    monkeypatch.setattr(rutas, "_leer", lambda a: leidos.append(a) or b"")
    with TestClient(app) as c:
        c.get("/api/session")
        r = c.post("/api/documents", files=[("archivos", ("grande.pdf", b"0" * (3 * 1024 ** 2), "application/pdf"))])
    assert r.status_code == 413 and r.json()["codigo"] == "ERR-ING-002" and "MB" in r.json()["mensaje"]
    assert leidos == []                                                                  # el cuerpo no llegó a procesarse


def test_una_subida_normal_no_se_corta(monkeypatch):
    ajustar(monkeypatch, MAX_DOCS_SESION=1, MAX_MB=1)
    with TestClient(app) as c:
        c.get("/api/session")
        r = c.post("/api/documents", files=[("archivos", ("a.pdf", b"no es un pdf", "application/pdf"))])
    assert r.status_code == 200 and r.json()[0]["estado"] == "error"                   # llega al validador y falla por no ser PDF, no por tamaño


def test_el_tope_de_subida_sale_de_la_configuracion(monkeypatch):
    ajustar(monkeypatch, MAX_DOCS_SESION=8, MAX_MB=20)
    assert main.tope_subida() == (8 * 20 + 1) * 1024 ** 2
