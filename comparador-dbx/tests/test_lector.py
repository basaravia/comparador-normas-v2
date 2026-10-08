"""backend/extraction/lector.py y manuales_locales(): unitarias (el extractor de Docling se sustituye por bloques ya extraídos)."""
import json

import pytest

from backend.config import manuales_locales
from backend.extraction import docling_extractor, lector
from conftest import TEXTO

BLOQUES = [{"texto": f"Artículo {n}.- Texto {n}.", "pagina": 1, "tipo": "parrafo"} for n in (1, 2, 3)]


@pytest.fixture
def extractor(monkeypatch):
    llamadas = []
    monkeypatch.setattr(docling_extractor, "extraer", lambda ruta, progreso=None: llamadas.append(ruta) or BLOQUES)
    return llamadas


def test_leer_documento_devuelve_las_secciones_del_pdf(hacer_pdf, extractor):
    secs = lector.leer_documento(hacer_pdf("n.pdf", textos=(TEXTO,)), "N1", "normativa")
    assert [s.identificador for s in secs] == ["Artículo 1", "Artículo 2", "Artículo 3"] and len(extractor) == 1


def test_con_cache_la_segunda_lectura_no_vuelve_a_extraer(hacer_pdf, extractor, tmp_path):
    pdf = hacer_pdf("n.pdf", textos=(TEXTO,))
    a = lector.leer_documento(pdf, "N1", "normativa", cache=tmp_path / "bloques")
    b = lector.leer_documento(pdf, "N1", "normativa", cache=tmp_path / "bloques")
    assert len(extractor) == 1 and [s.id for s in a] == [s.id for s in b]
    [archivo] = list((tmp_path / "bloques").glob("*.json"))
    assert json.loads(archivo.read_text(encoding="utf-8")) == BLOQUES


def test_otro_pdf_no_reutiliza_la_cache_de_uno_distinto(hacer_pdf, extractor, tmp_path):
    lector.leer_documento(hacer_pdf("a.pdf", textos=(TEXTO,)), "N1", "normativa", cache=tmp_path)
    lector.leer_documento(hacer_pdf("b.pdf", textos=(TEXTO + " distinto",)), "N1", "normativa", cache=tmp_path)
    assert len(extractor) == 2


def test_los_avisos_del_seccionado_llegan_a_quien_llama(hacer_pdf, extractor):
    avisos = []
    lector.leer_documento(hacer_pdf("n.pdf", textos=(TEXTO,)), "N1", "normativa", avisos=avisos)
    assert isinstance(avisos, list)


def test_manuales_locales_excluye_los_mock_de_git(tmp_path, monkeypatch):
    for n in ("MOCK-DEMO-01.pdf", "MANUAL-X.pdf", "otro.pdf", "nota.txt"):
        (tmp_path / n).write_bytes(b"%PDF-")
    monkeypatch.setattr("backend.config.carpeta_manuales", lambda: tmp_path)
    assert [p.name for p in manuales_locales()] == ["MANUAL-X.pdf", "otro.pdf"]


# --- Endurecimiento de la caché (appsec, 8 oct 2026) ---------------------------------------------------------------------

def test_la_cache_se_escribe_con_permisos_privados(hacer_pdf, extractor, tmp_path):
    lector.leer_documento(hacer_pdf("n.pdf", textos=(TEXTO,)), "N1", "normativa", cache=tmp_path / "bloques")
    [archivo] = list((tmp_path / "bloques").glob("*.json"))
    assert (archivo.stat().st_mode & 0o777) == 0o600 and ((tmp_path / "bloques").stat().st_mode & 0o777) == 0o700


def test_un_acierto_de_cache_no_se_salta_la_validacion_del_pdf(extractor, tmp_path):
    falso = tmp_path / "falso.pdf"; falso.write_text("esto no es un pdf")
    (tmp_path / "bloques").mkdir()
    with pytest.raises(docling_extractor.ExtraccionError):
        lector.leer_documento(falso, "N1", "normativa", cache=tmp_path / "bloques")
    assert extractor == []


@pytest.mark.parametrize("contenido", ["no es json {", '{"no": "una lista"}', '[{"texto": 1, "pagina": 1, "tipo": "parrafo"}]', '["texto"]'])
def test_una_cache_danada_o_manipulada_se_ignora_y_se_vuelve_a_extraer(hacer_pdf, extractor, tmp_path, contenido):
    pdf = hacer_pdf("n.pdf", textos=(TEXTO,))
    lector.leer_documento(pdf, "N1", "normativa", cache=tmp_path / "bloques")       # crea la caché real
    [archivo] = list((tmp_path / "bloques").glob("*.json"))
    archivo.write_text(contenido, encoding="utf-8")
    secs = lector.leer_documento(pdf, "N1", "normativa", cache=tmp_path / "bloques")
    assert len(extractor) == 2 and len(secs) == 3                                  # volvió a extraer y reescribió la caché
    assert json.loads(archivo.read_text(encoding="utf-8")) == BLOQUES
