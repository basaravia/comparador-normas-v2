"""Huecos de tests/test_marca.py hallados por mutación manual (QA, pantalla 1 del rediseño). Deterministas, sin modelo.

Cada prueba mata un mutante que sobrevivía: tope de 64 caracteres, `.png` en la variable, tamaño exacto, carpeta vacía, extensión en mayúsculas.
"""
import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.main import app

RAIZ = Path(__file__).resolve().parent.parent
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'


def _con_carpeta(monkeypatch, carpeta, **urls):
    base = dict(LOGO_DIR=str(carpeta), LOGO_ORG_URL="", LOGO_PRODUCTO_URL="", LOGO_PIE_URL="")
    monkeypatch.setattr(config, "settings", replace(config.settings, **{**base, **urls}))


# --- Variable de entorno: límites del nombre y extensiones -------------------------------------------------------------------

def test_el_nombre_sin_extension_admite_64_caracteres_y_no_65(monkeypatch):
    ok = "/marca/" + "a" * 64 + ".svg"            # el tope de 64 es del nombre sin la extensión
    largo = "/marca/" + "a" * 65 + ".svg"
    monkeypatch.setenv("LOGO_ORG_URL", ok)
    assert config._url_marca("LOGO_ORG_URL") == ok
    monkeypatch.setenv("LOGO_ORG_URL", largo)
    assert config._url_marca("LOGO_ORG_URL") == ""


@pytest.mark.parametrize("valor", ["/marca/logo.svg", "/marca/logo.png", "/marca/a-b_c.1.png"])
def test_se_aceptan_svg_y_png_con_el_juego_de_caracteres_documentado(valor, monkeypatch):
    monkeypatch.setenv("LOGO_PIE_URL", valor)
    assert config._url_marca("LOGO_PIE_URL") == valor


@pytest.mark.parametrize("valor", ["/marca/Logo.SVG", "/marca/logo.PNG", "/marca/logo.Svg", "/marca/logo", "/marca/.svg", "/marca/ñ.svg", "/marca/a b.svg",
                                   "/marca/a\\b.svg", "/Marca/logo.svg", "/MARCA/logo.svg"])
def test_extension_en_mayusculas_o_nombre_fuera_del_juego_se_descarta(valor, monkeypatch):
    """Decisión vigente: solo minúsculas (`.svg`/`.png`). Si se acepta la mayúscula, `TIPOS_LOGO` ya usa `.lower()`; esta prueba hará visible el cambio.
    """
    monkeypatch.setenv("LOGO_ORG_URL", valor)
    assert config._url_marca("LOGO_ORG_URL") == ""


def test_un_comentario_de_dotenv_leido_como_valor_no_es_un_logo(monkeypatch, caplog):
    monkeypatch.setenv("LOGO_ORG_URL", "# opcional: /marca/logo.svg")
    with caplog.at_level(logging.WARNING):
        assert config._url_marca("LOGO_ORG_URL") == ""
    assert caplog.text == ""            # un comentario es «sin valor», no un valor inválido: no alarma


def test_el_texto_de_marca_conserva_acentos_y_recorta_espacios(monkeypatch):
    monkeypatch.setenv("NOMBRE_PRODUCTO", "  Auditoría — Ñandú  ")
    assert config._texto_marca("NOMBRE_PRODUCTO", 80) == "Auditoría — Ñandú"


# --- Configuración por defecto -----------------------------------------------------------------------------------------------

def test_los_defaults_versionados_no_traen_logos_y_si_nombre():
    """`config/defaults.env` es lo que ve un despliegue sin configurar la marca: cabecera con texto, ningún logo servible."""
    from dotenv import dotenv_values
    d = dotenv_values(RAIZ / "config" / "defaults.env")
    assert d["NOMBRE_PRODUCTO"].strip() and d["LOGO_DIR"].strip()
    assert d["LOGO_ORG_URL"] == d["LOGO_PRODUCTO_URL"] == d["LOGO_PIE_URL"] == ""
    assert not Path(d["LOGO_DIR"]).is_absolute()                 # relativa a comparador-dbx/, no a una ruta del laptop


def test_con_las_variables_de_marca_ausentes_el_arranque_no_falla_y_la_marca_va_vacia():
    """Proceso aparte (Settings se lee al importar): se quitan las 6 variables de marca después de cargar los .env y se pide /api/brand y un logo."""
    codigo = """
import os, dotenv
original = dotenv.load_dotenv
MARCA = ["NOMBRE_PRODUCTO", "TEXTO_ALTERNATIVO", "LOGO_DIR", "LOGO_ORG_URL", "LOGO_PRODUCTO_URL", "LOGO_PIE_URL"]
def sin_marca(*a, **k):
    r = original(*a, **k)
    for v in MARCA: os.environ.pop(v, None)
    return r
dotenv.load_dotenv = sin_marca
from fastapi.testclient import TestClient
from backend.main import app
with TestClient(app) as c:
    print(c.get("/api/brand").status_code, c.get("/api/brand").json(), c.get("/marca/logo.svg").status_code)
"""
    entorno = {k: v for k, v in os.environ.items() if k not in ("LOGO_DIR", "LOGO_ORG_URL", "LOGO_PRODUCTO_URL", "LOGO_PIE_URL")}
    r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    assert r.stdout.strip().splitlines()[-1] == ("200 {'nombre_producto': '', 'texto_alternativo': '', 'logo_org': '', 'logo_producto': '', "
                                                 "'logo_pie': ''} 404")


# --- Lo que se sirve ---------------------------------------------------------------------------------------------------------

def test_sin_carpeta_configurada_no_se_sirve_nada_del_directorio_del_proyecto(tmp_path, monkeypatch):
    """LOGO_DIR vacío no debe convertirse en «la raíz del proyecto»: aunque la variable del logo nombre un archivo que existe allí."""
    (tmp_path / "logo-org.svg").write_bytes(SVG)
    monkeypatch.setattr(config, "RAIZ", tmp_path)
    _con_carpeta(monkeypatch, "", LOGO_ORG_URL="/marca/logo-org.svg")
    assert config.logo_permitido("logo-org.svg") is None
    with TestClient(app) as c:
        assert c.get("/marca/logo-org.svg").status_code == 404
        assert c.get("/api/brand").json()["logo_org"] == ""


def test_el_tope_de_tamano_es_inclusivo_en_512_kb(tmp_path, monkeypatch):
    _con_carpeta(monkeypatch, tmp_path, LOGO_ORG_URL="/marca/justo.svg", LOGO_PIE_URL="/marca/pasado.svg")
    (tmp_path / "justo.svg").write_bytes(b"x" * config.LOGO_MAX_BYTES)
    (tmp_path / "pasado.svg").write_bytes(b"x" * (config.LOGO_MAX_BYTES + 1))
    assert config.LOGO_MAX_BYTES == 512 * 1024
    assert config.logo_permitido("justo.svg") is not None
    assert config.logo_permitido("pasado.svg") is None


def test_un_directorio_con_nombre_de_logo_no_se_sirve(tmp_path, monkeypatch):
    (tmp_path / "falso.svg").mkdir()
    _con_carpeta(monkeypatch, tmp_path, LOGO_ORG_URL="/marca/falso.svg")
    with TestClient(app) as c:
        assert c.get("/marca/falso.svg").status_code == 404
        assert c.get("/api/brand").json()["logo_org"] == ""


def test_un_enlace_simbolico_dentro_de_la_carpeta_si_se_sirve(tmp_path, monkeypatch):
    (tmp_path / "real.svg").write_bytes(SVG)
    (tmp_path / "alias.svg").symlink_to(tmp_path / "real.svg")
    _con_carpeta(monkeypatch, tmp_path, LOGO_ORG_URL="/marca/alias.svg")
    with TestClient(app) as c:
        assert c.get("/marca/alias.svg").content == SVG


@pytest.mark.parametrize("nombre", ["../config/defaults.env", "..", ".", "", "/etc/passwd", "a/../b.svg", "logo-org.svg/..", "logo-org.svg\x00.png"])
def test_logo_permitido_rechaza_nombres_con_ruta_aunque_se_llame_directo(nombre, tmp_path, monkeypatch):
    """Defensa en profundidad: la ruta HTTP ya no deja pasar `/`, pero la función se usa también desde `marca_publica`."""
    (tmp_path / "logo-org.svg").write_bytes(SVG)
    _con_carpeta(monkeypatch, tmp_path, LOGO_ORG_URL="/marca/logo-org.svg")
    assert config.logo_permitido(nombre) is None


def test_el_mismo_archivo_en_dos_variables_y_el_cambio_de_archivo_se_ven_sin_reiniciar(tmp_path, monkeypatch):
    (tmp_path / "logo.svg").write_bytes(SVG)
    _con_carpeta(monkeypatch, tmp_path, LOGO_ORG_URL="/marca/logo.svg", LOGO_PIE_URL="/marca/logo.svg")
    with TestClient(app) as c:
        j = c.get("/api/brand").json()
        assert j["logo_org"] == j["logo_pie"] == "/marca/logo.svg"
        (tmp_path / "logo.svg").unlink()                          # el servicio retira el archivo: la cabecera pasa a texto
        assert c.get("/api/brand").json()["logo_org"] == ""


def test_peticiones_simultaneas_al_logo_y_a_la_marca_dan_siempre_lo_mismo(tmp_path, monkeypatch):
    (tmp_path / "logo.svg").write_bytes(SVG)
    _con_carpeta(monkeypatch, tmp_path, LOGO_ORG_URL="/marca/logo.svg")

    def pedir(_):
        with TestClient(app) as c:
            a, b = c.get("/marca/logo.svg"), c.get("/api/brand")
            return a.status_code, a.content, b.status_code, b.json()["logo_org"]

    with ThreadPoolExecutor(8) as pool:
        resultados = list(pool.map(pedir, range(24)))
    assert set(resultados) == {(200, SVG, 200, "/marca/logo.svg")}


@pytest.mark.parametrize("metodo", ["post", "put", "delete", "patch"])
@pytest.mark.parametrize("ruta", ["/marca/logo.svg", "/api/brand"])
def test_la_marca_es_de_solo_lectura(metodo, ruta):
    with TestClient(app) as c:
        assert getattr(c, metodo)(ruta).status_code in (404, 405)


def test_la_marca_no_exige_sesion_ni_identidad_y_no_crea_sesion():
    """La cabecera pinta antes de que exista sesión: ni /api/brand ni el logo piden identidad ni dejan una sesión abierta."""
    with TestClient(app) as c:
        r = c.get("/api/brand")
        assert r.status_code == 200 and "set-cookie" not in r.headers
