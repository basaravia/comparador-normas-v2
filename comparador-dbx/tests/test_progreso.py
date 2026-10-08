"""backend/core/progreso.py: logs sencillos y barra de progreso (unitaria, sin modelos)."""
import logging

import pytest

from backend.core.progreso import _ManejadorTqdm, configurar_logs, progreso


@pytest.fixture(autouse=True)
def logger_limpio():
    antes = (list(logging.getLogger("backend").handlers), logging.getLogger("backend").level, logging.getLogger("backend").propagate)
    yield
    lg = logging.getLogger("backend")
    lg.handlers, lg.level, lg.propagate = antes[0], antes[1], antes[2]


def test_configurar_logs_muestra_los_mensajes_del_backend_con_hora(capsys):
    configurar_logs()
    logging.getLogger("backend.extraction.docling_extractor").info("Docling: 43 bloques en 33 s")
    salida = capsys.readouterr()
    texto = salida.out + salida.err
    assert "Docling: 43 bloques en 33 s" in texto and texto.split()[0].count(":") == 2        # HH:MM:SS al inicio


def test_configurar_logs_es_idempotente_no_duplica_los_mensajes(capsys):
    configurar_logs(); configurar_logs(); configurar_logs()
    assert sum(isinstance(h, _ManejadorTqdm) for h in logging.getLogger("backend").handlers) == 1
    logging.getLogger("backend.x").info("una sola vez")
    salida = capsys.readouterr()
    assert (salida.out + salida.err).count("una sola vez") == 1


def test_configurar_logs_respeta_el_nivel(capsys):
    configurar_logs("WARNING")
    logging.getLogger("backend.x").info("detalle")
    logging.getLogger("backend.x").warning("aviso")
    texto = "".join(capsys.readouterr())
    assert "aviso" in texto and "detalle" not in texto


def test_un_fallo_al_escribir_el_log_no_tumba_el_proceso(monkeypatch):
    configurar_logs()
    monkeypatch.setattr("backend.core.progreso.tqdm.write", lambda *a, **k: (_ for _ in ()).throw(OSError("pantalla cerrada")))
    logging.getLogger("backend.x").info("no debe lanzar")           # handleError escribe en stderr y sigue


def test_progreso_actualiza_total_y_avance_y_cierra_la_barra(capsys):
    with progreso("Docling · prueba", "pág") as cb:
        cb(1, 3); cb(3, 3)
    err = capsys.readouterr().err
    assert "Docling · prueba" in err and "3/3" in err and "pág" in err


def test_progreso_cierra_la_barra_aunque_el_proceso_falle(capsys):
    with pytest.raises(RuntimeError):
        with progreso("falla", "it") as cb:
            cb(1, 5)
            raise RuntimeError("boom")
    assert "1/5" in capsys.readouterr().err
