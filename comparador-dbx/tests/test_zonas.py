"""Zonas de documentos: test (MOCK y normas públicas) y val (documentos reales, confinados). Rutas y reglas de git."""
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from backend import config
from backend.config import RAIZ, carpeta_bloques, carpeta_comparaciones, carpeta_manuales, carpeta_normas, carpeta_salida, manuales_locales


def test_rutas_por_zona():
    assert carpeta_normas("test") == RAIZ / "documentos" / "test" / "normas"
    assert carpeta_manuales("val") == RAIZ / "documentos" / "val" / "manuales"
    assert carpeta_comparaciones("val") == RAIZ / "documentos" / "val" / "comparaciones"
    assert carpeta_salida("val") == RAIZ / "output" / "val"
    assert carpeta_bloques("test") == RAIZ / "output" / "test" / "bloques"


def test_zona_por_defecto_es_test():
    assert carpeta_normas() == RAIZ / "documentos" / "test" / "normas"
    assert carpeta_bloques() == RAIZ / "output" / "test" / "bloques"


def test_zona_invalida_se_rechaza():
    with pytest.raises(ValueError, match="Zona 'prod'"):
        carpeta_salida("prod")


def test_variable_de_carpeta_gana_sin_zona_explicita(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "settings", replace(config.settings, NORMAS_DIR=str(tmp_path)))
    assert carpeta_normas() == tmp_path
    assert carpeta_normas("val") == RAIZ / "documentos" / "val" / "normas"      # una zona explícita no la pisa la variable


def test_los_mock_estan_en_la_zona_test():
    assert {p.name for p in carpeta_manuales("test").glob("MOCK-DEMO-*.pdf")} == {"MOCK-DEMO-01.pdf", "MOCK-DEMO-02.pdf", "MOCK-DEMO-03.pdf"}
    assert all(not p.name.startswith("MOCK-DEMO-") for p in manuales_locales("test"))


@pytest.mark.skipif(shutil.which("git") is None, reason="sin git")
@pytest.mark.parametrize("ruta, ignorada", [
    ("documentos/test/manuales/MOCK-DEMO-01.pdf", False),     # los MOCK ficticios se versionan
    ("documentos/test/normas/norma.pdf", True),               # las normas públicas pesan MB: en local
    ("documentos/val/normas/real.pdf", True),                 # val: nunca
    ("documentos/val/manuales/real.pdf", True),
    ("documentos/val/comparaciones/mia.xlsx", True),
    ("output/test/recuperacion/pares.csv", False),            # resultados de test: se pueden versionar
    ("output/test/comparaciones/tabla.xlsx", False),
    ("output/test/bloques/abc.json", True),                   # la caché lleva el texto íntegro: nunca
    ("output/val/recuperacion/pares.csv", True),              # resultados de val: nunca
    ("output/val/bloques/abc.json", True),
])
def test_reglas_de_git_de_las_zonas(ruta, ignorada, tmp_path):
    """Usa el .gitignore real del repo en un repositorio temporal: no depende de enlaces ni de archivos locales."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    shutil.copy(RAIZ.parent / ".gitignore", tmp_path / ".gitignore")
    r = subprocess.run(["git", "check-ignore", "-q", f"comparador-dbx/{ruta}"], cwd=tmp_path, capture_output=True)
    assert (r.returncode == 0) is ignorada, f"{ruta}: {'debería ignorarse' if ignorada else 'debería poder versionarse'}"


def test_zona_de_un_archivo_y_exigir_en_zona():
    assert config.zona_de(RAIZ / "documentos" / "val" / "manuales" / "x.pdf") == "val"
    assert config.zona_de("documentos/test/normas/n.pdf") == "test"
    assert config.zona_de("/tmp/x.pdf") is None
    assert config.exigir_en_zona(RAIZ / "documentos" / "val" / "manuales" / "x.pdf") == "val"
    with pytest.raises(ValueError, match="fuera de documentos"):
        config.exigir_en_zona("/tmp/manual_real.pdf")                        # un documento fuera de las zonas no se acepta
    with pytest.raises(ValueError, match="zona 'val'"):
        config.exigir_en_zona(RAIZ / "documentos" / "val" / "manuales" / "x.pdf", "test")


def test_lo_versionado_en_output_test_no_menciona_documentos_de_val():
    """Red de seguridad: ningún archivo versionado de output/test/ nombra un documento de documentos/val/ (si hay)."""
    nombres = {p.stem.lower() for p in (RAIZ / "documentos" / "val").rglob("*") if p.is_file() and len(p.stem) >= 6}
    if not nombres or shutil.which("git") is None:
        pytest.skip("sin documentos en val (o sin git)")
    r = subprocess.run(["git", "ls-files", "output/test"], cwd=RAIZ, capture_output=True, text=True)
    for ruta in filter(None, r.stdout.splitlines()):
        texto = (RAIZ / ruta).read_text(encoding="utf-8", errors="ignore").lower()
        assert not [n for n in nombres if n in texto], f"{ruta} menciona un documento de val: no debe versionarse"
