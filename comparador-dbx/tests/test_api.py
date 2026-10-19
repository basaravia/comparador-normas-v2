"""API (docs/11, backend/api/): sesión, ejemplo, árbol, selección y errores en lenguaje de negocio. Sin modelos: nada de esto llama al LLM."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def web():
    with TestClient(app) as c:
        yield c


def hojas(nodos):
    for n in nodos:
        if n["hoja"]:
            yield n
        yield from hojas(n["hijos"])


def test_sin_cookie_se_crea_sesion_y_con_cookie_inexistente_es_410(web):
    assert web.get("/api/session").json() == {"documentos": [], "comparacion_id": None}
    assert "session_id" in web.cookies
    web.cookies.set("session_id", "no-existe")
    r = web.get("/api/session")
    assert r.status_code == 410 and r.json()["codigo"] == "ERR-SES-001" and "sesión" in r.json()["mensaje"]


def test_ejemplo_arbol_y_vista_previa(web):
    docs = web.post("/api/samples/load").json()
    assert [d["tipo"] for d in docs] == ["normativa", "manual_control"] and all(d["estado"] == "listo" for d in docs)
    arbol_n = web.get("/api/sections/tree", params={"tipo": "normativa"}).json()
    assert len(list(hojas(arbol_n[0]["nodos"]))) == 18
    manual = web.get("/api/sections/tree", params={"tipo": "manual_control"}).json()[0]
    excl = [h for h in hojas(manual["nodos"]) if h["excluida"]]
    assert excl and all(not h["seleccionada"] and h["motivo"] for h in excl) and manual["avisos"]
    hoja = next(hojas(arbol_n[0]["nodos"]))
    r = web.get(f"/api/sections/{hoja['id']}")                       # los ids llevan ':' y '/'
    assert r.status_code == 200 and r.json()["texto"] and r.json()["pagina_inicio"] >= 1


def test_seleccion_invalida_da_mensajes_de_negocio(web):
    web.post("/api/samples/load")
    n = [h["id"] for h in hojas(web.get("/api/sections/tree", params={"tipo": "normativa"}).json()[0]["nodos"])]
    m = [h["id"] for h in hojas(web.get("/api/sections/tree", params={"tipo": "manual_control"}).json()[0]["nodos"]) if h["seleccionada"]]
    for cuerpo in ({"articulo_ids": [], "seccion_ids": m}, {"articulo_ids": m[:1], "seccion_ids": n[:1]},       # vacío / tipos al revés
                   {"articulo_ids": ["N9:no-existe"], "seccion_ids": m}):
        r = web.post("/api/comparisons", json=cuerpo)
        assert r.status_code == 422 and r.json()["codigo"].startswith("ERR-CMP") and "Traceback" not in r.text


def test_archivo_que_no_es_pdf_vuelve_como_error_del_documento_no_como_4xx(web):
    r = web.post("/api/documents", files=[("archivos", ("malo.pdf", b"esto no es un pdf", "application/pdf"))])
    assert r.status_code == 200
    d = r.json()[0]
    assert d["estado"] == "error" and d["error"]["codigo"] == "ERR-ING-003"


def test_procesar_sin_tipo_pide_elegirlo_y_documento_inexistente_se_explica(web):
    web.get("/api/session")
    r = web.post("/api/documents/process", json={"doc_ids": ["D99"]})
    assert r.status_code == 422 and r.json()["codigo"] == "ERR-DOC-001"


def test_reiniciar_borra_la_sesion(web):
    web.post("/api/samples/load")
    assert web.delete("/api/session").status_code == 200
    web.cookies.clear()
    assert web.get("/api/session").json()["documentos"] == []


def test_cabeceras_de_seguridad_y_api_sin_cache(web):
    r = web.get("/api/session")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store" and "default-src 'self'" in r.headers["content-security-policy"]


def test_ruta_api_inexistente_no_cae_en_el_frontend(web):
    r = web.get("/api/no-existe")
    assert r.status_code == 404 and r.json()["codigo"] == "ERR-HTTP-404"
