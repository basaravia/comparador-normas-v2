"""Marca configurable (docs/ux/identidad-visual-v1.md §4 y §6): validación de URL, lista blanca de campos y ruta de logos. Deterministas, sin modelo."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.main import app

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><script>alert(1)</script><rect width="10" height="10"/></svg>'


@pytest.fixture
def marca(tmp_path, monkeypatch):
    """Configuración con una carpeta de logos temporal; devuelve (carpeta, cliente)."""
    (tmp_path / "logo-org.svg").write_bytes(SVG)
    (tmp_path / "logo-pie.png").write_bytes(b"\x89PNG")
    (tmp_path / "secreto.svg").write_bytes(SVG)                      # existe en la carpeta pero ninguna variable lo nombra
    s = replace(config.settings, LOGO_DIR=str(tmp_path), LOGO_ORG_URL="/marca/logo-org.svg", LOGO_PRODUCTO_URL="/marca/falta.svg",
                LOGO_PIE_URL="/marca/logo-pie.png", NOMBRE_PRODUCTO="Auditoría X", TEXTO_ALTERNATIVO="Banco X")
    monkeypatch.setattr(config, "settings", s)
    with TestClient(app) as c:
        yield tmp_path, c


@pytest.mark.parametrize("valor", [
    "javascript:alert(1)", "data:image/svg+xml;base64,AAAA", "https://evil.example/logo.svg", "http://x/logo.svg", "//evil.example/marca/a.svg",
    "/marca/../config/x.svg", "/marca/a..svg", "/marca/a/b.svg", "/marca/a.svg?x=1", "/marca/a.svg#f", "/marca/a.gif", "/marca/%2e%2e.svg",
    "marca/a.svg", "/marca/" + "a" * 70 + ".svg", "/marca/a\n.svg",
])
def test_url_de_logo_invalida_se_descarta_con_aviso_que_no_incluye_el_valor(valor, monkeypatch, caplog):
    monkeypatch.setenv("LOGO_ORG_URL", valor)
    with caplog.at_level("WARNING"):
        assert config._url_marca("LOGO_ORG_URL") == ""
    assert "LOGO_ORG_URL" in caplog.text and "evil" not in caplog.text


def test_url_de_logo_valida_vacia_o_ausente(monkeypatch):
    monkeypatch.setenv("LOGO_ORG_URL", "/marca/logo-org.svg")
    assert config._url_marca("LOGO_ORG_URL") == "/marca/logo-org.svg"
    monkeypatch.setenv("LOGO_ORG_URL", "")
    assert config._url_marca("LOGO_ORG_URL") == ""


def test_texto_de_marca_sin_caracteres_de_control_y_acotado(monkeypatch):
    monkeypatch.setenv("NOMBRE_PRODUCTO", "Audi\x07to\nría" + "x" * 200)
    nombre = config._texto_marca("NOMBRE_PRODUCTO", 80)
    assert len(nombre) == 80 and nombre.startswith("Auditoría") and "\n" not in nombre and "\x07" not in nombre


def test_la_marca_publica_es_una_lista_blanca_y_no_trae_logos_inexistentes(marca):
    _, c = marca
    r = c.get("/api/brand")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json() == {"nombre_producto": "Auditoría X", "texto_alternativo": "Banco X", "logo_org": "/marca/logo-org.svg",
                        "logo_producto": "", "logo_pie": "/marca/logo-pie.png"}          # el producto apunta a un archivo que no existe → vacío
    for campo, valor in config.settings.__dict__.items():
        if config.es_secreto(campo) and valor:
            assert valor not in r.text


def test_sin_configurar_la_marca_viene_vacia_y_no_hay_logos(monkeypatch):
    monkeypatch.setattr(config, "settings", replace(config.settings, LOGO_ORG_URL="", LOGO_PRODUCTO_URL="", LOGO_PIE_URL="", TEXTO_ALTERNATIVO=""))
    with TestClient(app) as c:
        j = c.get("/api/brand").json()
    assert j["logo_org"] == j["logo_producto"] == j["logo_pie"] == "" and j["nombre_producto"]


def test_el_logo_se_sirve_con_tipo_fijo_y_csp_propia(marca):
    _, c = marca
    r = c.get("/marca/logo-org.svg")
    assert r.status_code == 200 and r.content == SVG
    assert r.headers["content-type"] == "image/svg+xml" and r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"] and "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "private, max-age=3600"
    assert c.get("/marca/logo-pie.png").headers["content-type"] == "image/png"


@pytest.mark.parametrize("ruta", ["/marca/secreto.svg", "/marca/falta.svg", "/marca/..%2fconfig%2fdefaults.env", "/marca/%2e%2e/x.svg", "/marca/logo-org.svg/x", "/marca/"])
def test_solo_se_sirve_lo_que_la_configuracion_nombra(marca, ruta):
    _, c = marca
    r = c.get(ruta)
    assert r.status_code in (404, 200) and (r.status_code == 404 or r.headers.get("content-type", "").startswith("text/html"))   # el catch-all del SPA no devuelve un logo
    assert SVG not in r.content


def test_un_logo_enlace_simbolico_fuera_de_la_carpeta_no_se_sirve(marca, tmp_path_factory):
    carpeta, c = marca
    fuera = tmp_path_factory.mktemp("fuera") / "otro.svg"
    fuera.write_bytes(SVG)
    (carpeta / "enlace.svg").symlink_to(fuera)
    config.settings = replace(config.settings, LOGO_PRODUCTO_URL="/marca/enlace.svg")      # el fixture restaura el original al terminar
    assert c.get("/marca/enlace.svg").status_code == 404


def test_un_enlace_simbolico_en_bucle_no_tumba_ni_el_logo_ni_la_marca(marca):
    carpeta, c = marca
    (carpeta / "bucle.svg").symlink_to(carpeta / "bucle.svg")
    config.settings = replace(config.settings, LOGO_PRODUCTO_URL="/marca/bucle.svg")        # el fixture restaura el original al terminar
    assert c.get("/marca/bucle.svg").status_code == 404
    r = c.get("/api/brand")
    assert r.status_code == 200 and r.json()["logo_producto"] == "" and r.json()["logo_org"] == "/marca/logo-org.svg"


def test_un_logo_demasiado_grande_no_se_sirve(marca, caplog):
    carpeta, c = marca
    (carpeta / "logo-org.svg").write_bytes(b"x" * (config.LOGO_MAX_BYTES + 1))
    with caplog.at_level("WARNING"):
        assert c.get("/marca/logo-org.svg").status_code == 404
    assert "512 KB" in caplog.text
    assert c.get("/api/brand").json()["logo_org"] == ""
