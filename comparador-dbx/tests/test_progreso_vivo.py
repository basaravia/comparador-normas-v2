"""Progreso en vivo y cancelación (docs/ux/mejora-experiencia-v1.md). Todo determinista: ningún modelo interviene en estas pruebas."""
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.schemas import JobOut
from backend.core import sesiones
from backend.engine import servicio
from backend.engine.juez import Cancelado, Observador, juzgar_pares
from backend.extraction import docling_extractor
from backend.main import app
from backend.models import Par, Seccion, Veredicto


def seccion(i: str, doc: str, tipo: str) -> Seccion:
    return Seccion(id=i, doc_id=doc, tipo_doc=tipo, nivel="articulo", identificador=i, ruta=[], texto_literal=f"Texto literal de {i} " * 20,
                   pagina_inicio=3, pagina_fin=3, seccionado_incierto=False, estrategia="patron", es_hoja=True)


def par(i: int) -> Par:
    return Par(id=f"P{i}", articulo_id="A1", seccion_id="M1", origen={"v1"}, score_v1=0.61)


@pytest.fixture
def obs():
    s = sesiones.crear()
    job = JobOut(job_id="J1", tipo="comparacion", estado="en_curso")
    todas = {"A1": seccion("A1", "D1", "normativa"), "M1": seccion("M1", "D2", "manual_control")}
    yield servicio._ObsJob(job, s, todas, {"D1": "Norma", "D2": "Manual"}), job, s
    sesiones.reiniciar(s.id)


def test_el_observador_refleja_pares_en_curso_veredictos_y_conteos_reales(obs):
    o, job, _ = obs
    p = par(1)
    o.empieza(p)
    assert [x.par_id for x in job.pares_en_curso] == ["P1"]
    f = job.pares_en_curso[0]
    assert f.articulo.preview.startswith("Texto literal de A1") and len(f.articulo.preview) <= 160 and f.score == 0.61 and f.origen == ["v1"]
    p.veredicto = Veredicto(naturaleza_articulo="obligacion", cobertura="parcial", cita_norma="x", comentario="c", confianza=0.8)
    p.cita_norma_verificada, p.cita_manual_verificada, p.requiere_revision = True, False, True
    o.termina(p, 1, 3)
    assert job.pares_en_curso == [] and job.pares_hechos == 1 and job.pares_total == 3
    v = job.ultimos_veredictos[0]
    assert (v.cobertura, v.confianza, v.cita_norma_ok, v.cita_manual_ok, v.requiere_revision) == ("parcial", 0.8, True, False, True)
    assert job.conteo_cobertura == {"parcial": 1} and job.a_revision == 1


def test_par_sin_veredicto_se_cuenta_como_a_revision_nunca_como_cobertura(obs):
    o, job, _ = obs
    p = par(2)
    p.requiere_revision = True
    o.empieza(p); o.termina(p, 1, 1)
    assert job.conteo_cobertura == {"sin_veredicto": 1} and job.ultimos_veredictos[0].cobertura == "sin_veredicto"


def test_el_anillo_de_veredictos_guarda_los_ultimos_20_y_la_secuencia_crece(obs):
    o, job, _ = obs
    for i in range(25):
        p = par(i)
        o.empieza(p); o.termina(p, i + 1, 25)
    assert len(job.ultimos_veredictos) == 20 and job.ultimos_veredictos[-1].seq == 25 and sum(job.conteo_cobertura.values()) == 25


def test_espera_por_limite_de_tasa_se_activa_y_se_apaga(obs):
    o, job, _ = obs
    o.espera(par(1), 20, 2, 6)
    assert job.espera_limite.activa and job.espera_limite.intento == 2 and job.espera_limite.max == 6 and job.espera_limite.hasta_ts > 0
    o.reanuda(par(1))
    assert not job.espera_limite.activa


def test_cancelar_job_en_curso_lo_marca_y_el_observador_lo_ve(obs):
    o, job, s = obs
    s.jobs["J1"] = job
    assert not o.cancelado()
    servicio.cancelar(s, "J1")
    assert o.cancelado() and not job.cancelable and job.etapa.startswith("Cancelando")


def test_cancelar_job_inexistente_o_terminado(obs):
    _, job, s = obs
    with pytest.raises(servicio.ComparacionError) as e:
        servicio.cancelar(s, "no-existe")
    assert e.value.codigo == "ERR-JOB-404"
    job.estado = "listo"
    s.jobs["J1"] = job
    assert servicio.cancelar(s, "J1").estado == "listo" and "J1" not in s.cancelados


def test_el_juez_cancelado_no_lanza_ninguna_llamada_al_modelo():
    class Cancelada(Observador):
        def cancelado(self) -> bool:
            return True

    class SinLlamadas:                                  # si el juez llamara al modelo, esto fallaría el test
        def chat_json(self, *a, **k):
            raise AssertionError("no debía llamar al modelo")

    pares = [par(i) for i in range(3)]
    secciones = {"A1": seccion("A1", "D1", "normativa"), "M1": seccion("M1", "D2", "manual_control")}
    with pytest.raises(Cancelado):
        asyncio.run(juzgar_pares(pares, secciones, {}, SinLlamadas(), obs=Cancelada()))
    assert all(p.veredicto is None for p in pares)


def test_cancelar_la_lectura_de_un_pdf_en_cola_no_arranca_docling(tmp_path):
    ruta = tmp_path / "a.pdf"
    docling_extractor.cancelar(ruta)
    with pytest.raises(docling_extractor.ExtraccionError) as e:
        docling_extractor._trabajo(ruta, "sha-que-no-esta-en-cache", None)
    assert e.value.codigo == "ERR-EXT-005" and ruta not in docling_extractor._CANCELADOS      # la marca se limpia al terminar


def test_api_job_trae_reloj_del_servidor_y_miniatura_valida_pagina_y_documento():
    with TestClient(app) as web:
        web.post("/api/samples/load")
        sid = web.cookies["session_id"]
        s = sesiones.obtener(sid)
        job = servicio._job(s, "procesamiento")
        j = web.get(f"/api/jobs/{job.job_id}").json()
        assert j["ahora_ts"] >= j["inicio_ts"] > 0 and j["cancelable"] is True
        assert web.post(f"/api/jobs/{job.job_id}/cancel").json()["cancelable"] is False
        assert web.post("/api/jobs/no-existe/cancel").status_code == 422
        d = next(iter(s.docs))
        r = web.get(f"/api/documents/{d}/pages/1/thumb")                 # el ejemplo no tiene PDF: mensaje de negocio, no traza
        assert r.status_code == 422 and "Traceback" not in r.text
        assert web.get("/api/documents/no-existe/pages/1/thumb").status_code == 422


def test_la_indexacion_cancelada_corta_en_el_siguiente_lote_y_sin_cancelar_solo_avanza(obs):
    _, job, _ = obs
    servicio._indexando(job, 2, 5, 10)
    assert job.indexacion_hechos == 5 and job.indexacion_total == 10 and 0 < job.progreso < 1
    with pytest.raises(Cancelado):
        servicio._indexando(job, 2, 6, 10, cancelado=True)


def test_una_cancelacion_vieja_no_se_arrastra_al_reintento(tmp_path):
    ruta = tmp_path / "a.pdf"
    docling_extractor.cancelar(ruta)                       # llegó tarde: el PDF ya no estaba leyéndose
    docling_extractor.olvidar_cancelacion(ruta)            # lo que hace el job al empezar y al terminar
    assert ruta not in docling_extractor._CANCELADOS


def test_miniatura_con_cache_acotado_y_misma_imagen():
    import pymupdf
    with TestClient(app) as web:
        web.get("/api/session")
        s = sesiones.obtener(web.cookies["session_id"])
        carpeta = Path(s.dir) / "m"; carpeta.mkdir()
        pdf = carpeta / "m.pdf"
        with pymupdf.open() as doc:
            for i in range(3):
                doc.new_page().insert_text((72, 72), f"Página {i + 1}")
            doc.save(pdf)
        from backend.api.schemas import DocumentoOut
        from backend.core.sesiones import Doc
        s.docs["M1"] = Doc(out=DocumentoOut(id="M1", nombre="m.pdf", paginas=3), ruta=pdf)
        a = web.get("/api/documents/M1/pages/2/thumb")
        assert a.status_code == 200 and a.headers["content-type"] == "image/png" and a.content[:4] == b"\x89PNG"
        assert web.get("/api/documents/M1/pages/2/thumb").content == a.content and ("%s" % s.id, "M1", 2) in servicio._MINIATURAS
        assert web.get("/api/documents/M1/pages/4/thumb").status_code == 422 and web.get("/api/documents/M1/pages/0/thumb").status_code == 422
    for i in range(servicio.MAX_MINIATURAS + 10):
        servicio._MINIATURAS[("x", "y", i)] = b""
        while len(servicio._MINIATURAS) > servicio.MAX_MINIATURAS:
            servicio._MINIATURAS.popitem(last=False)
    assert len(servicio._MINIATURAS) <= servicio.MAX_MINIATURAS


# --- QA: huecos cerrados (RF-20 / RF-21, criterios 7 y 10 de docs/ux/mejora-experiencia-v1.md §e) ---

def test_la_espera_por_limite_de_tasa_se_corta_al_cancelar_sin_dormir():
    from backend.engine.juez import _dormir

    class Cancelada(Observador):
        def cancelado(self) -> bool:
            return True

    import time
    t0 = time.perf_counter()
    with pytest.raises(Cancelado):
        _dormir(30, Cancelada())
    assert time.perf_counter() - t0 < 0.5


def test_los_campos_nuevos_del_job_son_aditivos_y_arrancan_vacios():
    j = JobOut(job_id="J", tipo="comparacion", estado="en_cola")
    assert j.pares_en_curso == [] and j.ultimos_veredictos == [] and j.conteo_cobertura == {} and j.a_revision == 0
    assert not j.espera_limite.activa


def test_suma_de_conteos_vivos_es_igual_a_pares_hechos_y_cada_veredicto_es_un_par_real(obs):
    o, job, _ = obs
    ids = set()
    for i in range(7):
        p = par(i)
        if i % 3:
            p.veredicto = Veredicto(naturaleza_articulo="obligacion", cobertura="total" if i % 2 else "nula", cita_norma="x", comentario="c", confianza=0.9)
        else:
            p.requiere_revision = True
        o.empieza(p); o.termina(p, i + 1, 7)
        ids.add(p.id)
    assert sum(job.conteo_cobertura.values()) == job.pares_hechos == 7
    assert {v.par_id for v in job.ultimos_veredictos} == ids


def test_cancelar_dos_veces_es_idempotente(obs):
    _, job, s = obs
    s.jobs["J1"] = job
    servicio.cancelar(s, "J1"); servicio.cancelar(s, "J1")
    assert "J1" in s.cancelados and not job.cancelable
