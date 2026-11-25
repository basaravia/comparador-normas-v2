"""scripts/prueba_humo.py: la selección del ejemplo reducido (la parte pura; el resto se prueba contra una app real)."""
import importlib.util

from backend.config import RAIZ

spec = importlib.util.spec_from_file_location("prueba_humo", RAIZ / "scripts" / "prueba_humo.py")
humo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(humo)


def nodo(i, hoja=True, excluida=False, marcada=False, hijos=()):
    return {"id": i, "hoja": hoja, "excluida": excluida, "seleccionada": marcada, "hijos": list(hijos)}


ARBOL = [{"doc_id": "D", "nombre": "x", "avisos": [], "nodos": [
    nodo("T1", hoja=False, hijos=[nodo("A1", marcada=True), nodo("A2", excluida=True), nodo("A3")]),
    nodo("A4", marcada=True)]}]


def test_hojas_ignora_las_excluidas_y_las_ramas():
    assert humo.hojas(ARBOL, solo_marcadas=False) == ["A1", "A3", "A4"]


def test_con_solo_marcadas_deja_las_preseleccionadas():
    assert humo.hojas(ARBOL, solo_marcadas=True) == ["A1", "A4"]


def test_sin_documentos_no_hay_hojas():
    assert humo.hojas([], False) == []


def test_con_token_la_url_debe_ser_https():
    import pytest
    humo.exigir_https("https://app.example.test", True)
    humo.exigir_https("http://localhost:8000", False)             # sin token no hay nada que proteger
    with pytest.raises(SystemExit):
        humo.exigir_https("http://app.example.test", True)
