"""Pantalla «Comparando» (docs/11, docs/ux/comparacion-en-curso-v1.md §5): pares resueltos incrementales, `cancelando` y tope de llamadas vivas.

Deterministas. El juicio del modelo se reemplaza por un veredicto fijo; lo que se prueba es lo que hace el código con él: `juzgar_par` real
(verificación de citas con `verificar_fragmento` real), `_ObsJob` real y los endpoints reales."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from backend.api.schemas import JobOut
from backend.config import settings
from backend.core import sesiones
from backend.engine import juez, servicio
from backend.engine.juez import juzgar_par, juzgar_pares
from backend.main import app
from backend.models import Par, Seccion, Veredicto
from tests.test_cancelar_comparacion import DOS, comparacion, esperar  # noqa: F401

NORMA = "Las entidades deberán conciliar diariamente los saldos de caja y reportar las diferencias al comité en un plazo máximo de cuatro días. " * 2
MANUAL = "El área de tesorería concilia diariamente los saldos de caja y reporta las diferencias al comité de riesgos dentro de cuatro días."
LARGO = " ".join(f"obligación{i:03d} sujeta a verificación documental" for i in range(30))        # ~1000 letras


def sec(i: str, doc: str, tipo: str, texto: str) -> Seccion:
    return Seccion(id=i, doc_id=doc, tipo_doc=tipo, nivel="articulo", identificador=i, ruta=["Título I", i], texto_literal=texto,
                   pagina_inicio=7, pagina_fin=8, seccionado_incierto=False, estrategia="patron", es_hoja=True)


class Cliente:
    """Devuelve siempre el mismo veredicto (no se llama a ningún modelo)."""

    def __init__(self, v: Veredicto):
        self.v = v

    def chat_json(self, sistema, usuario, modelo):
        return self.v


def veredicto(cita_norma: str, cita_manual: str | None, faltantes: list[str] | None = None) -> Veredicto:
    return Veredicto(naturaleza_articulo="obligacion", cobertura="parcial", cita_norma=cita_norma, cita_manual=cita_manual, comentario="c",
                     elementos_faltantes=faltantes or [], confianza=0.8)


@pytest.fixture
def web():
    """Cliente con una sola sesión (el servidor admite pocas a la vez), que se libera al terminar."""
    with TestClient(app) as c:
        c.get("/api/session")
        yield c
        sesiones.reiniciar(c.cookies["session_id"])


@pytest.fixture
def ctx(web):
    s = sesiones.obtener(web.cookies["session_id"])
    job = JobOut(job_id="J1", tipo="comparacion", estado="en_curso")
    s.jobs["J1"] = job
    todas = {"A1": sec("A1", "D1", "normativa", NORMA), "M1": sec("M1", "D2", "manual_control", MANUAL), "A2": sec("A2", "D1", "normativa", LARGO)}
    nombres = {"D1": "Norma 1", "D2": "Manual 1"}
    return servicio._ObsJob(job, s, todas, nombres), job, s, todas, nombres


def resolver(ctx, i: int, v: Veredicto, articulo: str = "A1", total: int = 100) -> Par:
    """Juzga un par con `juzgar_par` real y se lo entrega al observador, como hace `juzgar_pares`."""
    o, _, _, todas, nombres = ctx
    p = Par(id=f"P{i}", articulo_id=articulo, seccion_id="M1", origen={"v1"}, score_v1=0.6)
    o.empieza(p)
    juzgar_par(p, todas[articulo], todas["M1"], nombres, Cliente(v))
    o.termina(p, i, total)
    return p


def pedir(web, job_id: str, desde=None) -> dict:
    r = web.get(f"/api/jobs/{job_id}" + ("" if desde is None else f"?desde={desde}"))
    assert r.status_code == 200
    return r.json()


# --- desde=N, seq_ultimo, recarga ---

def test_desde_filtra_los_pares_nuevos_y_seq_ultimo_es_monotono(ctx, web):
    for i in range(1, 6):
        resolver(ctx, i, veredicto("conciliar diariamente los saldos de caja", "concilia diariamente los saldos de caja"))
    antes = 0
    for desde, esperados in [(None, [1, 2, 3, 4, 5]), (0, [1, 2, 3, 4, 5]), (2, [3, 4, 5]), (5, []), (99, [])]:
        j = pedir(web, "J1", desde)
        assert [p["seq"] for p in j["pares_resueltos"]] == esperados and j["seq_ultimo"] >= antes
        antes = j["seq_ultimo"]
    assert antes == 5
    resolver(ctx, 6, veredicto("conciliar diariamente los saldos de caja", None))
    j = pedir(web, "J1", 5)
    assert [p["seq"] for p in j["pares_resueltos"]] == [6] and j["seq_ultimo"] == 6


def test_desde_negativo_o_no_numerico_se_rechaza(web):
    assert web.get("/api/jobs/J1?desde=-1").status_code == 422
    assert web.get("/api/jobs/J1?desde=abc").status_code == 422


def test_la_lista_sobrevive_al_anillo_de_20_y_la_recarga_con_desde_0_recupera_todo(ctx, web):
    for i in range(1, 26):
        resolver(ctx, i, veredicto("conciliar diariamente los saldos de caja", "concilia diariamente los saldos de caja"))
    j = pedir(web, "J1", 0)
    assert len(j["ultimos_veredictos"]) == 20 and len(j["pares_resueltos"]) == 25 and j["seq_ultimo"] == 25
    assert [p["seq"] for p in j["pares_resueltos"]] == list(range(1, 26))
    assert j["pares_hechos"] == 25 and j["pares_total"] == 100          # los de pares, no el progreso mezclado


def test_las_respuestas_que_no_son_el_sondeo_no_cargan_la_lista(ctx, web):
    resolver(ctx, 1, veredicto("conciliar diariamente los saldos de caja", None))
    r = web.post("/api/jobs/J1/cancel").json()
    assert r["pares_resueltos"] == [] and r["cancelando"] is True
    assert pedir(web, "J1", 0)["pares_resueltos"] != []


# --- contenido de cada par: regla 5 ---

def test_cada_par_trae_fragmentos_y_citas_que_son_texto_del_documento(ctx, web):
    resolver(ctx, 1, veredicto("conciliar   diariamente los saldos de caja", "concilia diariamente los saldos de caja", ["plazo"]))
    p = pedir(web, "J1")["pares_resueltos"][0]
    assert p["articulo"]["documento"] == "Norma 1" and p["articulo"]["identificador"] == "A1" and p["articulo"]["pagina"] == 7
    assert p["seccion"]["documento"] == "Manual 1" and p["seccion"]["identificador"] == "M1" and p["seccion"]["pagina"] == 7
    assert p["cita_norma"] == "conciliar diariamente los saldos de caja" and p["cita_norma"] in " ".join(NORMA.split())      # texto real, espacios del documento
    assert p["cita_manual"] in MANUAL and p["cita_norma_ok"] and p["cita_manual_ok"] and not p["requiere_revision"]
    assert p["elementos_faltantes"] == ["plazo"] and p["cobertura"] == "parcial" and p["par_id"] == "P1" and p["seq"] == 1


def test_cita_no_verificable_llega_vacia_y_marcada_por_revisar(ctx, web):
    resolver(ctx, 1, veredicto("zzzz qqqq xxxx wwww kkkk jjjj", "vvvv bbbb nnnn mmmm"))
    p = pedir(web, "J1")["pares_resueltos"][0]
    assert p["cita_norma"] == "" and p["cita_manual"] == "" and not p["cita_norma_ok"] and not p["cita_manual_ok"] and p["requiere_revision"]


def test_cita_dudosa_muestra_solo_texto_del_documento(ctx, web):
    inventada = "concilian los saldos de caja cada semana y reportan las diferencias al directorio en un plazo de cuatro días"
    resolver(ctx, 1, veredicto(inventada, "concilia diariamente los saldos de caja"))
    p = pedir(web, "J1")["pares_resueltos"][0]
    assert p["cita_norma"] in " ".join(NORMA.split()) or p["cita_norma"] == ""        # nunca el texto del modelo
    assert p["cita_norma"] != inventada and not p["cita_norma_ok"] and p["requiere_revision"]


def test_la_cita_se_acota_a_600_letras_y_sigue_siendo_texto_del_documento(ctx, web):
    resolver(ctx, 1, veredicto(LARGO, "concilia diariamente los saldos de caja"), articulo="A2")
    p = pedir(web, "J1")["pares_resueltos"][0]
    assert len(LARGO) > 600 and len(p["cita_norma"]) == 600 and LARGO.startswith(p["cita_norma"]) and p["cita_norma_ok"]


def test_los_elementos_faltantes_se_acotan_a_10_de_300_letras(ctx, web):
    faltantes = [f"{i}" + "x" * 500 for i in range(15)]
    resolver(ctx, 1, veredicto("conciliar diariamente los saldos de caja", "concilia diariamente los saldos de caja", faltantes))
    p = pedir(web, "J1")["pares_resueltos"][0]
    assert len(p["elementos_faltantes"]) == 10 and all(len(f) == 300 for f in p["elementos_faltantes"])
    assert p["elementos_faltantes"][0] == faltantes[0][:300] and p["elementos_faltantes"][9] == faltantes[9][:300]


def test_par_sin_veredicto_trae_citas_vacias(ctx, web):
    o, _, _, _, _ = ctx
    p = Par(id="P1", articulo_id="A1", seccion_id="M1", origen={"v1"}, requiere_revision=True)
    o.empieza(p); o.termina(p, 1, 3)
    r = pedir(web, "J1")["pares_resueltos"][0]
    assert r["cobertura"] == "sin_veredicto" and r["cita_norma"] == "" and r["cita_manual"] == "" and r["elementos_faltantes"] == []


def test_la_verificacion_se_hace_una_sola_vez_y_el_par_resuelto_coincide_con_el_veredicto_del_par(ctx):
    p = resolver(ctx, 1, veredicto("conciliar diariamente los saldos de caja", "concilia diariamente los saldos de caja"))
    r = ctx[1]._resueltos[0]
    assert (r.cita_norma, r.cita_manual) == (p.veredicto.cita_norma, p.veredicto.cita_manual)


# --- cancelando y pares tardíos ---

def test_cancelando_es_true_desde_cancelar_hasta_que_el_job_termina(ctx, web):
    _, job, s, _, _ = ctx
    assert pedir(web, "J1")["cancelando"] is False
    servicio.cancelar(s, "J1")
    assert [pedir(web, "J1")["cancelando"] for _ in range(3)] == [True, True, True]            # estable y viene del servidor: sobrevive a recargar
    job.estado = "cancelado"
    assert pedir(web, "J1")["cancelando"] is False


def test_un_par_tardio_tras_cancelar_no_entra_en_la_lista(ctx):
    o, job, _, _, _ = ctx
    resolver(ctx, 1, veredicto("conciliar diariamente los saldos de caja", None))
    o.cerrar()                                                  # lo que hace `_ejecutar` al cancelar
    resolver(ctx, 2, veredicto("conciliar diariamente los saldos de caja", None))
    assert [p.seq for p in job._resueltos] == [1] and job.pares_hechos == 1


# --- campos aditivos ---

def test_un_job_antiguo_sigue_validando_y_los_campos_nuevos_arrancan_vacios():
    j = JobOut.model_validate({"job_id": "J", "tipo": "comparacion", "estado": "en_cola", "progreso": 0.5, "pares_total": 4, "pares_hechos": 1})
    assert j.pares_resueltos == [] and j.seq_ultimo == 0 and j.cancelando is False and j._resueltos == []
    assert "_resueltos" not in j.model_dump()


def test_el_job_entrega_los_parametros_de_la_pantalla(web, ctx):
    j = pedir(web, "J1")
    assert j["estimado_desde_pares"] == 3 and j["pares_por_pagina"] == 50


# --- tope de llamadas vivas del juez ---

def test_el_contador_vuelve_a_cero_tras_terminar_y_tras_una_excepcion(monkeypatch):
    secciones = {"A1": sec("A1", "D1", "normativa", NORMA), "M1": sec("M1", "D2", "manual_control", MANUAL)}
    pares = [Par(id=f"P{i}", articulo_id="A1", seccion_id="M1", origen={"v1"}) for i in range(3)]
    dentro = []

    def ok(p, *a, **k):
        dentro.append(juez.llamadas_vivas())
        return p

    monkeypatch.setattr(juez, "juzgar_par", ok)
    assert juez.llamadas_vivas() == 0
    asyncio.run(juzgar_pares(pares, secciones, {}, None, DOS))
    assert min(dentro) >= 1 and max(dentro) <= DOS.LLM_CONCURRENCY and juez.llamadas_vivas() == 0

    def falla(p, *a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(juez, "juzgar_par", falla)
    with pytest.raises(RuntimeError):
        asyncio.run(juzgar_pares(pares, secciones, {}, None, DOS))
    esperar(lambda: juez.llamadas_vivas() == 0)
    assert juez.llamadas_vivas() == 0


def test_comparar_se_rechaza_con_409_si_hay_tantas_llamadas_vivas_como_la_concurrencia(comparacion, monkeypatch):
    s, art, sec_id = comparacion
    monkeypatch.setattr(juez, "_VIVAS", DOS.LLM_CONCURRENCY)
    with pytest.raises(servicio.ComparacionError) as e:
        servicio.comparar(s, [art], [sec_id], cliente=None)
    assert e.value.codigo == "ERR-CMP-008" and e.value.estado_http == 409
    assert e.value.mensaje_negocio == "El servicio de IA está terminando llamadas anteriores o atendiendo otra comparación. Espera unos segundos e inténtalo de nuevo."
    assert not s.jobs and not s.comparaciones                      # no quedó nada a medias


def test_comparar_pasa_con_el_contador_en_cero(comparacion, monkeypatch):
    s, art, sec_id = comparacion

    async def sin_pares(pares, *a, **k):
        return pares

    monkeypatch.setattr(servicio, "juzgar_pares", sin_pares)
    monkeypatch.setattr(juez, "_VIVAS", DOS.LLM_CONCURRENCY - 1)    # por debajo del tope también pasa
    job = servicio.comparar(s, [art], [sec_id], cliente=None)
    esperar(lambda: job.estado in ("cancelado", "listo", "error"), 10)
    assert job.comparacion_id in s.comparaciones
    time.sleep(0.1)


def test_el_409_llega_por_http_con_el_codigo(web, monkeypatch):
    monkeypatch.setattr(juez, "_VIVAS", settings.LLM_CONCURRENCY)      # la API usa la configuración vigente de la sesión (la del stage)
    s = sesiones.obtener(web.cookies["session_id"])
    servicio.cargar_ejemplo(s)
    todas = s.secciones()
    a = next(i for i, x in todas.items() if x.tipo_doc == "normativa" and x.es_hoja)
    m = next(i for i, x in todas.items() if x.tipo_doc == "manual_control" and x.es_hoja)
    r = web.post("/api/comparisons", json={"articulo_ids": [a], "seccion_ids": [m]})
    assert r.status_code == 409 and r.json()["codigo"] == "ERR-CMP-008" and "Traceback" not in r.text
