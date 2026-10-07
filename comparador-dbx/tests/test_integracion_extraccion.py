"""Integración de L2 con Docling REAL (docs/13: artículos de la LA/FT >= 95 % del conteo manual, reproceso usa la caché).

- `L1-XVI-cap-III.pdf` (3 páginas): Docling real, 1 hilo. Tarda ~1 min. Correr con `taskset -c 3 pytest -m integracion`.
- LA/FT (60 páginas): Docling tarda ~12 min, así que se usan los bloques ya extraídos por el desarrollador
  (`/tmp/claude-1000/extraccion-l2/lafit.json`, solo lectura; se salta si no existe) y se siembra el seccionado real.
La referencia es independiente del código: regex propia sobre el texto de PyMuPDF (artículo = línea que empieza por
"Artículo N" + punto o guion; la ruta de cada artículo = último Libro/Título/Capítulo/Sección anteriores, con reinicio de hijos).
"""
import dataclasses
import json
import os
import re
import time
import unicodedata
from pathlib import Path

import pymupdf
import pytest

from backend.config import RAIZ, settings
from backend.extraction import docling_extractor as de
from backend.extraction.sectioner import parsear_bloques

pytestmark = pytest.mark.integracion

NORMAS = Path(os.environ.get("NORMAS_DIR", RAIZ.parent.parent / "comparador-normativas-ec-v1" / "Normativa2026"))
CAP3 = NORMAS / "L1-XVI-cap-III.pdf"
LAFT = NORMAS / "Proyecto-de-Ley-Organica-Organica-para-Reprimir-y-Prevenir-el-Lavado-de-Activos-y-la-Financiacion-del-Terrorismo.pdf"
BLOQUES_LAFT = Path("/tmp/claude-1000/extraccion-l2/lafit.json")

ARTICULO = re.compile(r"^\s*Art[íi]culo\s+(\d{1,3})\s*[.\-–]", re.I)
ENCABEZADO = re.compile(r"^\s*(LIBRO|T[ÍI]TULO|CAP[ÍI]TULO|SECCI[ÓO]N)\s+([IVXLC]+|\d+)\b")
NIVELES = ["LIBRO", "TITULO", "CAPITULO", "SECCION"]


def sin_tildes(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()


def referencia(pdf):
    """{número de artículo: ruta esperada} leyendo el texto de PyMuPDF en orden."""
    vigente, esperado = {}, {}
    with pymupdf.open(pdf) as d:
        for pagina in d:
            for linea in pagina.get_text().split("\n"):
                if m := ENCABEZADO.match(linea):
                    nivel = sin_tildes(m.group(1))
                    for n in NIVELES[NIVELES.index(nivel):]:
                        vigente.pop(n, None)
                    vigente[nivel] = f"{nivel} {m.group(2).upper()}"
                elif m := ARTICULO.match(linea):
                    esperado.setdefault(int(m.group(1)), [vigente[n] for n in NIVELES if n in vigente])
    return esperado


def ruta_normalizada(seccion):
    return [" ".join(sin_tildes(x).split()) for x in seccion.ruta]


def articulos(secciones):
    """{número: Seccion} de los artículos de la norma (excluye disposiciones y duplicados #2)."""
    return {int(s.id.rsplit("ART-", 1)[1]): s for s in secciones if "ART-" in s.id and s.id.rsplit("ART-", 1)[1].isdigit()}


@pytest.fixture(scope="module")
def un_hilo():
    """Docling real con 1 hilo (OMP_NUM_THREADS=1 en el hijo) y caché limpia."""
    mp = pytest.MonkeyPatch()
    mp.setattr(de, "settings", dataclasses.replace(settings, DOCLING_THREADS=1))
    de.limpiar_cache()
    yield
    de.limpiar_cache()
    mp.undo()


@pytest.fixture(scope="module")
def cap3(un_hilo):
    if not CAP3.exists():
        pytest.skip(f"no existe {CAP3} (define NORMAS_DIR)")
    progreso = []
    t0 = time.perf_counter()
    bloques = de.extraer(CAP3, lambda hechas, total: progreso.append((hechas, total)))
    return bloques, time.perf_counter() - t0, progreso


def test_docling_real_extrae_cap_iii_y_informa_progreso(cap3):
    bloques, segundos, progreso = cap3
    print(f"\nDocling real, L1-XVI-cap-III: {len(bloques)} bloques en {segundos:.1f} s, progreso {progreso}")
    assert len(bloques) >= 30 and {b["pagina"] for b in bloques} == {1, 2, 3}
    assert all({"texto", "pagina", "tipo"} <= set(b) and b["texto"].strip() for b in bloques)
    assert progreso and progreso[-1] == (3, 3)


def test_cap_iii_tiene_8_articulos_y_8_de_8_rutas_contra_la_referencia(cap3):
    bloques, _, _ = cap3
    esperado = referencia(CAP3)
    assert sorted(esperado) == list(range(1, 9))  # conteo manual: 8 artículos
    avisos = []
    secciones = parsear_bloques(bloques, "N1", "normativa", pdf=CAP3, avisos=avisos)
    arts = articulos(secciones)
    assert sorted(arts) == list(range(1, 9))
    buenas = [n for n, s in arts.items() if ruta_normalizada(s) == esperado[n]]
    print(f"\nrutas correctas {len(buenas)}/8; avisos: {avisos}")
    assert len(buenas) == 8, {n: (ruta_normalizada(arts[n]), esperado[n]) for n in arts if n not in buenas}
    assert not any(s.seccionado_incierto for s in secciones)
    assert arts[8].ruta[-1].startswith("SECCIÓN II") or "SECCI" in arts[8].ruta[-1]


def test_reprocesar_el_mismo_pdf_usa_la_cache(cap3):
    bloques, primera, _ = cap3
    t0 = time.perf_counter()
    otra = de.extraer(CAP3)
    segunda = time.perf_counter() - t0
    print(f"\nprimera {primera:.1f} s · segunda {segunda:.3f} s")
    assert otra == bloques and segunda < 1 and segunda < primera / 20


def test_laft_99_de_99_articulos_y_rutas_98_de_99_con_los_bloques_ya_extraidos():
    if not BLOQUES_LAFT.exists() or not LAFT.exists():
        pytest.skip(f"faltan {BLOQUES_LAFT} o {LAFT}")
    bloques = json.loads(BLOQUES_LAFT.read_text())
    esperado = referencia(LAFT)
    assert sorted(esperado) == list(range(1, 100))  # conteo manual (regex propia): 99
    avisos = []
    secciones = parsear_bloques(bloques, "N1", "normativa", pdf=LAFT, avisos=avisos)
    arts = articulos(secciones)
    coinciden = set(arts) & set(esperado)
    falsos_positivos, falsos_negativos = set(arts) - set(esperado), set(esperado) - set(arts)
    buenas = [n for n in coinciden if ruta_normalizada(arts[n]) == esperado[n]]
    malas = sorted(set(coinciden) - set(buenas))
    print(f"\nLA/FT artículos {len(coinciden)}/99, FP {sorted(falsos_positivos)}, FN {sorted(falsos_negativos)}"
          f"\nrutas correctas {len(buenas)}/99; incorrectas {malas}; avisos {len(avisos)}")
    assert len(coinciden) / len(esperado) >= 0.95  # criterio de docs/13
    assert len(coinciden) == 99 and not falsos_positivos
    assert len(buenas) >= 98
    # una ruta equivocada nunca se presenta como buena: debe venir marcada como incierta
    assert all(arts[n].seccionado_incierto for n in malas), [n for n in malas if not arts[n].seccionado_incierto]
