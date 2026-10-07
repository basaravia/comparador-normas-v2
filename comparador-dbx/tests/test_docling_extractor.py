"""Lógica determinista de `docling_extractor` (docs/07 §1) SIN Docling.

`_COMANDO` se reemplaza por un script de Python de prueba que habla el mismo protocolo que el trabajador real
(una línea JSON por evento: `{"progreso": [hechas, total]}` y `{"bloques": [...]}`) o que se queda dormido o falla.
Es un comando de prueba, no un modelo: el subproceso, el timeout, el entorno, la cola y la caché son los reales.
Los PDFs se generan con pymupdf (fixture `hacer_pdf`). Docling real: `test_integracion_extraccion.py`.
"""
import dataclasses
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.config import RAIZ, settings
from backend.extraction import docling_extractor as de
from backend.extraction import docling_worker
from backend.extraction.docling_extractor import ExtraccionError, extraer, limpiar_cache
from conftest import TEXTO

BLOQUES = [{"texto": "Artículo 1.- Objeto", "pagina": 1, "tipo": "parrafo"}, {"texto": "cuerpo", "pagina": 2, "tipo": "parrafo"}]
EMITE_BLOQUES = f"print(json.dumps({{'bloques': {BLOQUES!r}}}))"


@pytest.fixture(autouse=True)
def cache_limpia():
    limpiar_cache()
    yield
    limpiar_cache()


@pytest.fixture
def comando(tmp_path, monkeypatch):
    """`comando(cuerpo)` instala como `_COMANDO` un script de Python con ese cuerpo. Devuelve la carpeta de apoyo."""
    def _instalar(cuerpo):
        script = tmp_path / "trabajador_de_prueba.py"
        script.write_text("import json, os, sys, time, subprocess\n" + cuerpo + "\n")
        monkeypatch.setattr(de, "_COMANDO", [sys.executable, str(script)])
        return tmp_path
    return _instalar


@pytest.fixture
def ajustes(monkeypatch):
    def _cambiar(**campos):
        monkeypatch.setattr(de, "settings", dataclasses.replace(settings, **campos))
    return _cambiar


def pdf_n(hacer_pdf, n):
    """PDF válido distinto por n (otro SHA-256)."""
    return hacer_pdf(f"doc{n}.pdf", textos=(f"{TEXTO} variante {n}",))


# --- Camino feliz -------------------------------------------------------------------------------------

def test_devuelve_los_bloques_del_trabajador_y_pasa_los_argumentos_de_la_configuracion(hacer_pdf, comando, ajustes):
    comando("print(json.dumps({'bloques': [{'texto': json.dumps(sys.argv[2:]), 'pagina': 1, 'tipo': 'parrafo'}]}))")
    ajustes(DOCLING_TABLES="off", DOCLING_THREADS=1, DOCLING_CHUNK_PAGES=7, DOCLING_ARTIFACTS="")
    pdf = pdf_n(hacer_pdf, 1)
    bloques = extraer(pdf)
    assert json.loads(bloques[0]["texto"]) == ["off", "1", "7"]
    limpiar_cache()
    ajustes(DOCLING_TABLES="fast", DOCLING_THREADS=2, DOCLING_CHUNK_PAGES=10, DOCLING_ARTIFACTS="/modelos/docling")
    assert json.loads(extraer(pdf)[0]["texto"]) == ["fast", "2", "10", "/modelos/docling"]


def test_devuelve_los_bloques_tal_cual(hacer_pdf, comando):
    comando(EMITE_BLOQUES)
    assert extraer(pdf_n(hacer_pdf, 1)) == BLOQUES


def test_progreso_se_informa_por_tanda_y_el_ruido_de_stdout_se_ignora(hacer_pdf, comando):
    comando("print('Docling imprime ruido que no es JSON')\nprint(json.dumps({'progreso': [10, 25]}))\nprint('{roto')\n"
            "print(json.dumps({'progreso': [20, 25]}))\nprint(json.dumps({'progreso': [25, 25]}))\n" + EMITE_BLOQUES)
    visto = []
    assert extraer(pdf_n(hacer_pdf, 1), lambda hechas, total: visto.append((hechas, total))) == BLOQUES
    assert visto == [(10, 25), (20, 25), (25, 25)]


def test_sin_callback_de_progreso_no_falla(hacer_pdf, comando):
    comando("print(json.dumps({'progreso': [1, 1]}))\n" + EMITE_BLOQUES)
    assert extraer(pdf_n(hacer_pdf, 1)) == BLOQUES


def test_acepta_la_ruta_como_texto(hacer_pdf, comando):
    comando(EMITE_BLOQUES)
    assert extraer(str(pdf_n(hacer_pdf, 1))) == BLOQUES


def test_modificar_la_lista_devuelta_no_altera_la_cache(hacer_pdf, comando):
    comando(EMITE_BLOQUES)
    pdf = pdf_n(hacer_pdf, 1)
    extraer(pdf).clear()
    assert extraer(pdf) == BLOQUES


# --- Caché por SHA-256 ------------------------------------------------------------------------------------

def _con_contador(tmp_path):
    return ("open(%r, 'a').write('x'); " % str(tmp_path / "corridas")) + EMITE_BLOQUES


def corridas(tmp_path):
    f = tmp_path / "corridas"
    return len(f.read_text()) if f.exists() else 0


def test_reprocesar_el_mismo_pdf_usa_la_cache(hacer_pdf, comando, tmp_path):
    comando(_con_contador(tmp_path))
    pdf = pdf_n(hacer_pdf, 1)
    primero = extraer(pdf)
    t0 = time.perf_counter()
    segundo = extraer(pdf)
    assert corridas(tmp_path) == 1 and segundo == primero
    assert time.perf_counter() - t0 < 0.5  # sin lanzar subproceso


def test_la_clave_es_el_contenido_no_el_nombre(hacer_pdf, comando, tmp_path):
    comando(_con_contador(tmp_path))
    a = hacer_pdf("a.pdf", textos=(TEXTO,))
    b = a.with_name("copia_con_otro_nombre.pdf")
    b.write_bytes(a.read_bytes())
    extraer(a)
    extraer(b)
    assert corridas(tmp_path) == 1


def test_contenido_distinto_no_comparte_cache(hacer_pdf, comando, tmp_path):
    comando(_con_contador(tmp_path))
    extraer(pdf_n(hacer_pdf, 1))
    extraer(pdf_n(hacer_pdf, 2))
    assert corridas(tmp_path) == 2


def test_limpiar_cache_obliga_a_extraer_de_nuevo(hacer_pdf, comando, tmp_path):
    comando(_con_contador(tmp_path))
    pdf = pdf_n(hacer_pdf, 1)
    extraer(pdf)
    limpiar_cache()
    extraer(pdf)
    assert corridas(tmp_path) == 2


def test_la_cache_tiene_tope_max_cache_y_descarta_el_mas_antiguo(hacer_pdf, comando, tmp_path, monkeypatch):
    assert de.MAX_CACHE == 8
    monkeypatch.setattr(de, "MAX_CACHE", 2)
    comando(_con_contador(tmp_path))
    a, b, c = (pdf_n(hacer_pdf, n) for n in (1, 2, 3))
    for pdf in (a, b, c):
        extraer(pdf)
    assert len(de._CACHE) == 2 and corridas(tmp_path) == 3
    extraer(c)
    extraer(b)  # siguen en caché
    assert corridas(tmp_path) == 3
    extraer(a)  # el más antiguo se descartó: vuelve a extraerse
    assert corridas(tmp_path) == 4 and len(de._CACHE) == 2


def test_con_el_tope_real_nunca_hay_mas_de_8_pdfs(hacer_pdf, comando):
    comando(EMITE_BLOQUES)
    for n in range(10):
        extraer(pdf_n(hacer_pdf, n))
    assert len(de._CACHE) == de.MAX_CACHE == 8


def test_un_fallo_no_se_guarda_en_cache(hacer_pdf, comando, tmp_path):
    pdf = pdf_n(hacer_pdf, 1)
    comando("sys.exit(5)")
    with pytest.raises(ExtraccionError):
        extraer(pdf)
    assert de._CACHE == {}
    comando(EMITE_BLOQUES)
    assert extraer(pdf) == BLOQUES


# --- Validación previa ----------------------------------------------------------------------------------------

def test_pdf_corrupto_se_rechaza_antes_de_lanzar_el_subproceso(tmp_path, comando):
    comando("open(%r, 'w').write('corrio')\n" % str(tmp_path / "marca") + EMITE_BLOQUES)
    malo = tmp_path / "malo.pdf"
    malo.write_bytes(b"esto no es un pdf")
    with pytest.raises(ExtraccionError) as e:
        extraer(malo)
    assert e.value.codigo == "ERR-ING-003" and "PDF válido" in e.value.para_usuario()["mensaje"]
    assert not (tmp_path / "marca").exists()


def test_pdf_escaneado_se_rechaza_antes_de_lanzar_el_subproceso(hacer_pdf, tmp_path, comando):
    comando("open(%r, 'w').write('corrio')\n" % str(tmp_path / "marca") + EMITE_BLOQUES)
    with pytest.raises(ExtraccionError) as e:
        extraer(hacer_pdf("escaneo.pdf", textos=("", "")))
    assert e.value.codigo == "ERR-ING-001" and not (tmp_path / "marca").exists()


def test_pdf_que_pasa_el_limite_de_paginas_se_rechaza(hacer_pdf, comando, monkeypatch):
    from backend.ingest import validation
    monkeypatch.setattr(validation, "settings", dataclasses.replace(settings, MAX_PAGES=2))
    comando(EMITE_BLOQUES)
    with pytest.raises(ExtraccionError) as e:
        extraer(hacer_pdf("largo.pdf", textos=(TEXTO,) * 3))
    assert e.value.codigo == "ERR-ING-002"


# --- Entorno mínimo y directorio del hijo -------------------------------------------------------------------------

def test_el_hijo_recibe_un_entorno_minimo_sin_claves_de_los_modelos(hacer_pdf, comando, ajustes, monkeypatch):
    for nombre in ("GROQ_API_KEY", "FOUNDRY_AI_TOKEN", "DATABRICKS_TOKEN", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(nombre, "secreto-que-no-debe-salir")
    monkeypatch.setenv("HF_HOME", "/modelos")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    ajustes(DOCLING_THREADS=1)
    comando("print(json.dumps({'bloques': [{'texto': json.dumps(dict(os.environ)), 'pagina': 1, 'tipo': 'parrafo'},"
            " {'texto': os.getcwd(), 'pagina': 1, 'tipo': 'parrafo'}]}))")
    entorno_hijo, cwd = (b["texto"] for b in extraer(pdf_n(hacer_pdf, 1)))
    entorno_hijo = json.loads(entorno_hijo)
    assert not {"GROQ_API_KEY", "FOUNDRY_AI_TOKEN", "DATABRICKS_TOKEN", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY"} & set(entorno_hijo)
    assert "secreto-que-no-debe-salir" not in json.dumps(entorno_hijo)
    assert entorno_hijo["OMP_NUM_THREADS"] == "1" and entorno_hijo["HF_HUB_DISABLE_TELEMETRY"] == "1" and entorno_hijo["DO_NOT_TRACK"] == "1"
    assert entorno_hijo["HF_HOME"] == "/modelos" and entorno_hijo["LC_ALL"] == "C.UTF-8" and "PATH" in entorno_hijo
    assert set(entorno_hijo) <= de.ENTORNO_HIJO | {"OMP_NUM_THREADS", "HF_HUB_DISABLE_TELEMETRY", "DO_NOT_TRACK", "HF_HOME", "LC_ALL"}
    assert Path(cwd).resolve() == Path(RAIZ).resolve()


def test_el_hijo_corre_en_su_propia_sesion_para_poder_matarlo_con_killpg(hacer_pdf, comando):
    comando("print(json.dumps({'bloques': [{'texto': '%d %d' % (os.getpgrp(), os.getsid(0)), 'pagina': 1, 'tipo': 'parrafo'}]}))")
    pgrp, sid = map(int, extraer(pdf_n(hacer_pdf, 1))[0]["texto"].split())
    assert pgrp != os.getpgrp() and sid != os.getsid(0)


# --- Timeout y killpg ---------------------------------------------------------------------------------------------------

def vivo(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # un zombi sin recoger también cuenta como muerto
        return "Z" not in Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return False


def test_timeout_termina_el_grupo_completo_y_da_err_ext_002(hacer_pdf, comando, ajustes, tmp_path):
    """El trabajador lanza un nieto (como los procesos auxiliares de Docling) y se duerme: killpg debe matar a ambos."""
    ajustes(DOCLING_TIMEOUT_S=1)
    comando(f"nieto = subprocess.Popen(['sleep', '300'])\nopen({str(tmp_path / 'pid_nieto')!r}, 'w').write(str(nieto.pid))\n"
            f"open({str(tmp_path / 'pid_hijo')!r}, 'w').write(str(os.getpid()))\nprint(json.dumps({{'progreso': [1, 9]}}), flush=True)\ntime.sleep(300)")
    t0 = time.perf_counter()
    with pytest.raises(ExtraccionError) as e:
        extraer(pdf_n(hacer_pdf, 1))
    assert time.perf_counter() - t0 < 6
    assert e.value.codigo == "ERR-EXT-002" and "más de lo permitido" in e.value.para_usuario()["mensaje"]
    assert "1 s" in str(e.value)
    nieto, hijo = (int((tmp_path / f).read_text()) for f in ("pid_nieto", "pid_hijo"))
    for _ in range(40):
        if not vivo(nieto) and not vivo(hijo):
            break
        time.sleep(0.05)
    assert not vivo(hijo) and not vivo(nieto)
    assert de._CACHE == {}


@pytest.mark.xfail(strict=False, reason="DEFECTO QA-02: si el trabajador ignora SIGTERM no hay SIGKILL hasta que cierre stdout; "
                                        "el timeout no se aplica (docling_extractor.py:109-125)")
def test_timeout_se_aplica_aunque_el_trabajador_ignore_sigterm(hacer_pdf, comando, ajustes):
    ajustes(DOCLING_TIMEOUT_S=1)
    comando("import signal\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(6)")
    t0 = time.perf_counter()
    with pytest.raises(ExtraccionError):
        extraer(pdf_n(hacer_pdf, 1))
    assert time.perf_counter() - t0 < 4


def test_matar_un_grupo_que_ya_no_existe_no_falla():
    p = subprocess.Popen(["true"], start_new_session=True)
    p.wait()
    de._matar(p, signal.SIGTERM)  # ProcessLookupError se ignora


# --- Errores ERR-EXT-001 / 003 ----------------------------------------------------------------------------------------------

def test_codigo_de_salida_distinto_de_cero_es_err_ext_001_con_el_detalle(hacer_pdf, comando):
    comando("sys.stderr.write('Traceback: el modelo no cargo')\nsys.exit(3)")
    with pytest.raises(ExtraccionError) as e:
        extraer(pdf_n(hacer_pdf, 1))
    assert e.value.codigo == "ERR-EXT-001"
    assert "código 3" in str(e.value) and "el modelo no cargo" in str(e.value)
    assert e.value.para_usuario() == {"codigo": "ERR-EXT-001", "mensaje": "No pudimos leer el texto de este documento. Intenta con otro archivo."}
    assert "Traceback" not in e.value.para_usuario()["mensaje"]


def test_salida_con_bloques_pero_codigo_distinto_de_cero_tambien_falla(hacer_pdf, comando):
    comando(EMITE_BLOQUES + "\nsys.exit(1)")
    with pytest.raises(ExtraccionError) as e:
        extraer(pdf_n(hacer_pdf, 1))
    assert e.value.codigo == "ERR-EXT-001"


def test_salida_sin_el_evento_de_bloques_es_err_ext_001(hacer_pdf, comando):
    comando("print(json.dumps({'progreso': [1, 1]}))")
    with pytest.raises(ExtraccionError) as e:
        extraer(pdf_n(hacer_pdf, 1))
    assert e.value.codigo == "ERR-EXT-001" and "código 0" in str(e.value)


def test_el_detalle_del_error_oculta_secretos_y_se_acota_a_500_caracteres(hacer_pdf, comando):
    comando("sys.stderr.write('x' * 2000 + ' clave gsk_' + 'a' * 30 + ' fin')\nsys.exit(2)")
    with pytest.raises(ExtraccionError) as e:
        extraer(pdf_n(hacer_pdf, 1))
    assert "gsk_" not in str(e.value) and "***" in str(e.value)
    assert len(str(e.value)) < 650


def test_bloques_vacios_es_err_ext_003(hacer_pdf, comando):
    comando("print(json.dumps({'bloques': []}))")
    with pytest.raises(ExtraccionError) as e:
        extraer(pdf_n(hacer_pdf, 1))
    assert e.value.codigo == "ERR-EXT-003" and e.value.para_usuario()["mensaje"] == "No encontramos texto en este documento."
    assert de._CACHE == {}


def test_el_error_lleva_codigo_y_mensaje_propios():
    e = ExtraccionError("detalle técnico")
    assert (e.codigo, str(e)) == ("ERR-EXT-001", "detalle técnico")
    e2 = ExtraccionError("x", "ERR-EXT-009", "mensaje de negocio")
    assert e2.para_usuario() == {"codigo": "ERR-EXT-009", "mensaje": "mensaje de negocio"}


# --- Cola de 1 worker ---------------------------------------------------------------------------------------------------------

def test_la_cola_tiene_un_solo_worker():
    assert de._COLA._max_workers == 1


def test_dos_extracciones_simultaneas_nunca_corren_en_paralelo(hacer_pdf, comando, tmp_path):
    bitacora = tmp_path / "bitacora"
    comando(f"f = open({str(bitacora)!r}, 'a')\nf.write('ini\\n'); f.flush()\ntime.sleep(0.6)\nf.write('fin\\n'); f.close()\n" + EMITE_BLOQUES)
    resultados = []
    hilos = [threading.Thread(target=lambda p=pdf_n(hacer_pdf, n): resultados.append(extraer(p))) for n in (1, 2, 3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(30)
    assert len(resultados) == 3
    assert bitacora.read_text().split() == ["ini", "fin"] * 3


def test_el_mismo_pdf_pedido_a_la_vez_se_extrae_una_sola_vez(hacer_pdf, comando, tmp_path):
    comando(f"open({str(tmp_path / 'corridas')!r}, 'a').write('x')\ntime.sleep(0.6)\n" + EMITE_BLOQUES)
    pdf = pdf_n(hacer_pdf, 1)
    resultados = []
    hilos = [threading.Thread(target=lambda: resultados.append(extraer(pdf))) for _ in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(30)
    assert resultados == [BLOQUES] * 3 and corridas(tmp_path) == 1


# --- Trabajador (solo la parte que no necesita Docling) -------------------------------------------------------------------------

@pytest.mark.parametrize("etiqueta, es_tabla, tipo", [
    ("title", False, "encabezado"), ("section_header", False, "encabezado"), ("list_item", False, "lista"),
    ("text", False, "parrafo"), ("paragraph", False, "parrafo"), ("table", True, "tabla"), ("section_header", True, "tabla")])
def test_tipo_de_bloque_segun_la_etiqueta_de_docling(etiqueta, es_tabla, tipo):
    assert docling_worker._tipo(SimpleNamespace(label=SimpleNamespace(value=etiqueta)), es_tabla) == tipo


def test_el_trabajador_descarta_encabezados_y_pies_de_pagina():
    assert docling_worker.OMITIR == {"page_header", "page_footer"}


def test_comando_por_defecto_es_el_trabajador_y_importarlo_no_carga_docling():
    assert de._COMANDO[1:] == ["-m", "backend.extraction.docling_worker"]
    salida = subprocess.run([sys.executable, "-c", "import sys, backend.extraction.docling_worker as w; "
                             "print(any(m.split('.')[0] == 'docling' for m in sys.modules))"],
                            capture_output=True, text=True, cwd=RAIZ, check=True)
    assert salida.stdout.strip() == "False"
