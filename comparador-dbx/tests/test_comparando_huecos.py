"""Huecos de la pantalla «Comparando» detectados por QA (23 nov 2026). Deterministas: ningún modelo interviene.

Reutilizan los observadores y fixtures de `test_comparando_api.py`; los pares se juzgan con `juzgar_par` y la verificación de citas reales."""
import gc
import threading
import time
import weakref

import pytest
from fastapi.testclient import TestClient

from backend.api.schemas import JobOut
from backend.config import settings
from backend.core import sesiones
from backend.engine import juez, servicio
from backend.engine.verificacion import verificar_fragmento
from backend.main import app
from tests.test_comparando_api import MANUAL, NORMA, ctx, pedir, resolver, veredicto, web  # noqa: F401

CITA_OK = "conciliar diariamente los saldos de caja"
MANUAL_OK = "concilia diariamente los saldos de caja"


# --- ?desde con valores extremos por HTTP ---

@pytest.mark.parametrize("desde", ["2147483648", "9223372036854775807", "9223372036854775808", "1" + "0" * 40])
def test_desde_enorme_devuelve_lista_vacia_y_no_revienta(ctx, web, desde):
    resolver(ctx, 1, veredicto(CITA_OK, MANUAL_OK))
    r = web.get(f"/api/jobs/J1?desde={desde}")
    assert r.status_code == 200 and r.json()["pares_resueltos"] == [] and r.json()["seq_ultimo"] == 1 and "Traceback" not in r.text


@pytest.mark.parametrize("desde", ["", "1.5", "1e3", "-0", "-1", "abc", "NaN", "inf", "null", "%00", "1;2", "0x10"])
def test_desde_invalido_nunca_da_500_ni_filtra_texto_tecnico(ctx, web, desde):
    resolver(ctx, 1, veredicto(CITA_OK, MANUAL_OK))
    r = web.get(f"/api/jobs/J1?desde={desde}")
    assert r.status_code in (200, 422) and "Traceback" not in r.text and "File \"" not in r.text


def test_desde_repetido_usa_un_valor_y_el_cero_explicito_devuelve_todo(ctx, web):
    for i in range(1, 4):
        resolver(ctx, i, veredicto(CITA_OK, MANUAL_OK))
    assert web.get("/api/jobs/J1?desde=1&desde=2").status_code in (200, 422)
    assert [p["seq"] for p in pedir(web, "J1", 0)["pares_resueltos"]] == [1, 2, 3]


# --- cita por debajo del umbral: vacía, no la del modelo ---

def test_cita_con_parecido_bajo_el_umbral_llega_vacia_y_marcada_por_revisar(ctx, web):
    parecida = "los saldos de caja se concilian cada mes por el área contable y se archivan sin reportar nada"
    ratio = verificar_fragmento(parecida, " ".join(NORMA.split())).ratio
    assert 0.3 < ratio < settings.CITATION_SHOW_MIN, ratio                 # condición de la prueba: parecida, pero bajo el umbral
    resolver(ctx, 1, veredicto(parecida, parecida))
    p = pedir(web, "J1")["pares_resueltos"][0]
    assert p["cita_norma"] == "" and p["cita_manual"] == "" and not p["cita_norma_ok"] and not p["cita_manual_ok"] and p["requiere_revision"]
    assert parecida not in str(p)                                           # el texto del modelo no sale por ningún campo


# --- elementos faltantes en el límite ---

def test_elementos_faltantes_en_el_limite_exacto_no_se_recortan(ctx, web):
    exactos = [f"{i:02d}" + "y" * 298 for i in range(10)]                  # 10 ítems de 300: justo en el borde
    resolver(ctx, 1, veredicto(CITA_OK, MANUAL_OK, exactos))
    assert pedir(web, "J1")["pares_resueltos"][0]["elementos_faltantes"] == exactos
    resolver(ctx, 2, veredicto(CITA_OK, MANUAL_OK, exactos + ["z"]))        # uno más: se descarta el 11.º
    assert pedir(web, "J1")["pares_resueltos"][1]["elementos_faltantes"] == exactos


# --- memoria: la lista se libera con la sesión ---

def test_la_lista_de_pares_se_libera_al_borrar_la_sesion():
    with TestClient(app) as c:
        c.get("/api/session")
        sid = c.cookies["session_id"]
        s = sesiones.obtener(sid)
        job = JobOut(job_id="J9", tipo="comparacion", estado="en_curso")
        s.jobs["J9"] = job
        job._resueltos.extend([object()] * 5)                               # basta con que la lista exista: lo que se mide es su liberación
        ref_job, ref_lista = weakref.ref(job), job._resueltos
        assert len(ref_lista) == 5
        sesiones.reiniciar(sid)
        assert sesiones.existente(sid) is None
        del job, s, ref_lista
        gc.collect()
        assert ref_job() is None                                            # nadie retiene el job ni su lista


def test_tras_borrar_la_sesion_el_job_ya_no_se_puede_pedir(ctx, web):
    resolver(ctx, 1, veredicto(CITA_OK, MANUAL_OK))
    sesiones.reiniciar(web.cookies["session_id"])
    r = web.get("/api/jobs/J1?desde=0")
    assert r.status_code in (404, 410) and "pares_resueltos" not in r.text


# --- cancelando visible tras recargar (otro cliente con la misma cookie) ---

def test_cancelando_se_ve_en_un_get_nuevo_con_la_misma_cookie(ctx, web):
    _, job, s, _, _ = ctx
    servicio.cancelar(s, "J1")
    with TestClient(app, cookies={"session_id": web.cookies["session_id"]}) as recargado:      # una pestaña recién abierta
        j = recargado.get("/api/jobs/J1?desde=0").json()
    assert j["cancelando"] is True and j["estado"] == "en_curso"
    job.estado = "cancelado"
    assert pedir(web, "J1")["cancelando"] is False


# --- ERR-CMP-008: mensaje neutro ---

def test_el_409_por_llamadas_vivas_no_nombra_proveedores_ni_internos(web, monkeypatch):
    monkeypatch.setattr(juez, "_VIVAS", settings.LLM_CONCURRENCY)
    s = sesiones.obtener(web.cookies["session_id"])
    servicio.cargar_ejemplo(s)
    todas = s.secciones()
    a = next(i for i, x in todas.items() if x.tipo_doc == "normativa" and x.es_hoja)
    m = next(i for i, x in todas.items() if x.tipo_doc == "manual_control" and x.es_hoja)
    r = web.post("/api/comparisons", json={"articulo_ids": [a], "seccion_ids": [m]})
    cuerpo = r.json()
    assert r.status_code == 409 and cuerpo["codigo"] == "ERR-CMP-008"
    prohibidas = ["groq", "ollama", "foundry", "openai", "429", "semáforo", "hilo", "thread", "llm", "concurrencia", "pool", "traceback", "api key"]
    assert not [w for w in prohibidas if w in cuerpo["mensaje"].lower()], cuerpo["mensaje"]
    assert not s.jobs and not s.comparaciones


# --- cargar_ejemplo con 8 hilos ---

def test_cargar_ejemplo_con_8_hilos_a_la_vez_no_duplica(web, monkeypatch):
    original = servicio.clasificar_secciones

    def lenta(secs):                                     # ensancha la ventana entre la comprobación y el alta (función determinista, no un modelo)
        time.sleep(0.05)
        return original(secs)
    monkeypatch.setattr(servicio, "clasificar_secciones", lenta)
    s = sesiones.obtener(web.cookies["session_id"])
    barrera, errores, listas = threading.Barrier(8), [], []

    def cargar():
        try:
            barrera.wait(10)
            listas.append(servicio.cargar_ejemplo(s))
        except Exception as e:                           # noqa: BLE001 - se reporta en el assert
            errores.append(repr(e))
    hilos = [threading.Thread(target=cargar) for _ in range(8)]
    [h.start() for h in hilos]
    [h.join(30) for h in hilos]
    nombres = sorted(d.out.nombre for d in s.docs.values())
    assert not errores and len(listas) == 8, errores
    assert len(s.docs) == 2 and len(set(nombres)) == 2, nombres          # una norma y un manual, sin repetir
    assert len({id_ for id_ in s.docs}) == 2 and all(len(l) == 2 for l in listas)
