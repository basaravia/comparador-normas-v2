"""Sub-chunker (docs/08, backend/retrieval/chunker.py). Unitarias, sin modelo."""
import subprocess
import sys
from pathlib import Path

import pytest

from backend.retrieval.chunker import _unidades, estimar_tokens, prefijo, subchunkear, texto_a_embeber
from l3_ayudas import cfg, seccion

RAIZ = Path(__file__).resolve().parent.parent
S = cfg(SUBCHUNK_TOKENS=500, SUBCHUNK_OVERLAP=0.15)


def palabras(n):
    return " ".join(f"palabra{i}" for i in range(n))


def test_estimar_tokens():
    assert estimar_tokens("") == 0
    assert estimar_tokens("una dos tres cuatro cinco seis siete ocho nueve diez") == 14  # 10 palabras x 1,35 -> 14


def test_seccion_corta_es_un_solo_subchunk_con_el_literal():
    sec = seccion(texto="  Las entidades concilian la caja a diario.\n")
    subs = subchunkear(sec, "Ley", S)
    assert len(subs) == 1
    assert subs[0].texto == "Las entidades concilian la caja a diario."
    assert (subs[0].id, subs[0].seccion_id, subs[0].orden) == ("D:1#c0", "D:1", 0)


def test_seccion_vacia_da_un_subchunk_vacio():
    # construir_indice la omite antes de embeber; el chunker no revienta.
    assert [c.texto for c in subchunkear(seccion(texto="   "), "Ley", S)] == [""]


def test_seccion_justo_en_el_presupuesto_es_un_subchunk_y_pasada_la_presupuesto_se_parte():
    gastado = estimar_tokens(prefijo(seccion(), "Ley"))
    n = int((S.SUBCHUNK_TOKENS - gastado) / 1.35)       # palabras que caben con el prefijo
    assert len(subchunkear(seccion(texto=palabras(n)), "Ley", S)) == 1
    assert len(subchunkear(seccion(texto=palabras(n + 5)), "Ley", S)) > 1


def test_seccion_larga_se_parte_con_ids_ordenados_y_cubre_todo_el_texto():
    texto = palabras(1500)
    subs = subchunkear(seccion(texto=texto), "Ley", S)
    assert len(subs) > 1
    assert [c.id for c in subs] == [f"D:1#c{i}" for i in range(len(subs))]
    assert [c.orden for c in subs] == list(range(len(subs)))
    assert {c.seccion_id for c in subs} == {"D:1"}
    assert set(" ".join(c.texto for c in subs).split()) == set(texto.split())   # no se pierde ninguna palabra
    assert subs[0].texto.split()[0] == "palabra0" and subs[-1].texto.split()[-1] == "palabra1499"


def test_solape_de_cada_subchunk_es_cerca_del_15_por_ciento():
    subs = subchunkear(seccion(texto=palabras(1500)), "Ley", S)
    for a, b in zip(subs, subs[1:]):
        cola = [w for w in a.texto.split() if w in set(b.texto.split())]      # palabras que repite el siguiente
        solape = estimar_tokens(" ".join(cola))
        assert 0.10 * S.SUBCHUNK_TOKENS <= solape <= 0.20 * S.SUBCHUNK_TOKENS, solape
        assert b.texto.split()[:len(cola)] == a.texto.split()[-len(cola):]    # y son la cola del anterior


def test_primer_subchunk_cerca_de_500_tokens():
    subs = subchunkear(seccion(texto=palabras(1500)), "Ley", S)
    assert 0.9 * S.SUBCHUNK_TOKENS <= estimar_tokens(subs[0].texto) <= S.SUBCHUNK_TOKENS


def test_ningun_subchunk_pasa_de_subchunk_tokens():
    subs = subchunkear(seccion(texto=palabras(1500)), "Ley", S)
    assert max(estimar_tokens(c.texto) for c in subs) <= S.SUBCHUNK_TOKENS


def test_presupuesto_incluye_el_prefijo_y_no_baja_del_minimo():
    # prefijo enorme: el cuerpo conserva al menos PRESUPUESTO_MINIMO tokens y no entra en bucle
    sec = seccion(texto=palabras(400), ruta=["ruta " * 400])
    subs = subchunkear(sec, "Ley", S)
    assert len(subs) > 1


def test_prefijo_solo_en_el_texto_a_embeber_y_literal_intacto():
    literal = "Artículo 1.- Las entidades concilian la caja.\n\n  Segunda línea."
    sec = seccion(texto=literal)
    sub = subchunkear(sec, "Ley LA/FT", S)[0]
    assert prefijo(sec, "Ley LA/FT") == "Ley LA/FT > Título I > Artículo 1: "
    assert texto_a_embeber(sec, sub, "Ley LA/FT") == "Ley LA/FT > Título I > Artículo 1: " + sub.texto
    assert "Ley LA/FT" not in sub.texto                 # el sub-chunk guardado no lleva prefijo
    assert sec.texto_literal == literal                 # la sección no se altera


def test_documento_por_defecto_es_el_doc_id():
    sec = seccion(texto="Texto breve de la sección.", doc_id="N1")
    assert texto_a_embeber(sec, subchunkear(sec, None, S)[0]).startswith("N1 > Título I > Artículo 1: ")


def test_prefijo_sin_ruta():
    assert prefijo(seccion(ruta=()), "M1") == "M1 > Artículo 1: "


def test_cada_subchunk_es_texto_literal_de_la_seccion():
    # Con un texto sin repeticiones, cada sub-chunk (menos el solape ya comprobado) está dentro del literal.
    texto = palabras(1500)
    for c in subchunkear(seccion(texto=texto), "Ley", S):
        assert c.texto in texto


# --- Fronteras: numerales, literales y números con puntos -------------------------------------------

def test_numero_con_puntos_no_es_numeral():
    assert _unidades("El monto supera USD 2.500.000 por operación y se reporta.") == \
        ["El monto supera USD 2.500.000 por operación y se reporta."]


def test_articulo_5_punto_las_entidades_no_se_corta():
    assert _unidades("Conforme al artículo 5. Las entidades deben reportar.") == \
        ["Conforme al artículo 5. Las entidades deben reportar."]


def test_numerales_y_literales_abren_item():
    texto = "Reglas: 1. Primero; 2. Segundo\n3.1. Tercero\na) uno b) dos; c) tres\n(d) cuatro"
    assert _unidades(texto) == ["Reglas:", "1. Primero;", "2. Segundo", "3.1. Tercero", "a) uno b) dos;", "c) tres", "(d) cuatro"]


def test_marcadores_en_medio_de_frase_no_cortan():
    assert _unidades("según el literal a) del artículo y el numeral 4. se aplica") == \
        ["según el literal a) del artículo y el numeral 4. se aplica"]


def test_subchunks_parten_en_fronteras_de_item_no_dentro_de_un_numero():
    items = " ".join(f"{i}. El responsable verifica el monto de USD 2.500.000 en la operación número {i} del día." for i in range(1, 80))
    subs = subchunkear(seccion(texto=items), "Ley", cfg(SUBCHUNK_TOKENS=120, SUBCHUNK_OVERLAP=0.0))
    assert len(subs) > 1
    for c in subs:
        assert c.texto.startswith(tuple(f"{i}. El responsable" for i in range(1, 80)))   # cada uno abre en un ítem
        assert "USD 2.500.000" in c.texto and not c.texto.endswith("USD 2.")


# --- Hostil -------------------------------------------------------------------------------------------

PATRONES_HOSTILES = ["1. ", "a) ", "1.1.1. ", "x ", "."]


@pytest.mark.parametrize("patron", PATRONES_HOSTILES)
def test_entrada_hostil_de_400kb_se_parte_sin_alterar_el_literal(patron):
    texto = patron * (400 * 1024 // len(patron))
    sec = seccion(texto=texto)
    subs = subchunkear(sec, "Ley", S)
    assert subs and sec.texto_literal == texto


@pytest.mark.parametrize("patron", PATRONES_HOSTILES)
def test_entrada_hostil_de_400kb_en_menos_de_medio_segundo(patron):
    # Se mide en un intérprete limpio: con `--cov` el trazado de coverage multiplica el tiempo por ~2
    # y mediría a coverage, no al chunker (criterio de docs/13 / entrada hostil de L3).
    codigo = (
        "import sys, time\n"
        "sys.path[:0] = [%r, %r]\n"
        "from l3_ayudas import seccion\n"
        "from backend.retrieval.chunker import subchunkear\n"
        "sec = seccion(texto=%r * (400 * 1024 // %d))\n"
        "t0 = time.perf_counter(); subchunkear(sec, 'Ley'); print(time.perf_counter() - t0)\n"
    ) % (str(RAIZ), str(RAIZ / "tests"), patron, len(patron))
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True, cwd=RAIZ)
    assert float(salida.stdout) < 0.5, f"{patron!r}: {salida.stdout.strip()} s"


# --- Tablas atómicas (TABLAS_ATOMICAS) -----------------------------------------------------------------------------

from backend.retrieval.chunker import _empaquetar, _partir_tabla  # noqa: E402

TABLA = "\n".join(["| Desde | Hasta | % |", "|---|---|---|"] + [f"| {i}00 | {i}99 | {i}.5% |" for i in range(1, 41)])


def test_una_tabla_es_una_sola_unidad_y_el_texto_de_alrededor_se_separa():
    u = _unidades("Conforme a la tabla:\n" + TABLA + "\nLa porción variable es otra.")
    assert len(u) == 3 and u[1] == TABLA and u[0].startswith("Conforme") and u[2].startswith("La porción")


def test_sin_el_interruptor_la_tabla_vuelve_a_ser_una_unidad_por_fila():
    assert len(_unidades(TABLA, tablas=False)) == 42


def test_una_tabla_larga_se_parte_por_filas_y_cada_trozo_repite_la_cabecera():
    piezas = _partir_tabla(TABLA, presupuesto=120)
    assert len(piezas) > 1
    for k, (p, solapada) in enumerate(piezas):
        assert p.startswith("| Desde | Hasta | % |\n|---|---|---|") and solapada == (k > 0)
    filas = [f for p, _ in piezas for f in p.split("\n")[2:]]
    assert filas == TABLA.split("\n")[2:]                               # ninguna fila se pierde ni se repite
    assert all(estimar_tokens(p) <= 120 for p, _ in piezas)


def test_la_tabla_nunca_se_corta_sin_cabecera_al_empaquetar():
    chunks = _empaquetar(_unidades("Texto previo.\n" + TABLA), presupuesto=120, solape=15)
    for c in chunks:
        if "| 2" in c or "| 3" in c:
            assert "| Desde | Hasta | % |" in c


def test_subchunkear_respeta_el_interruptor(monkeypatch):
    import dataclasses
    from backend.config import settings
    from l3_ayudas import cfg  # noqa: F401
    sec = seccion(texto="Art.\n" + TABLA)
    con = subchunkear(sec, "Ley", dataclasses.replace(S, TABLAS_ATOMICAS=True, SUBCHUNK_TOKENS=200))
    sin = subchunkear(sec, "Ley", dataclasses.replace(S, TABLAS_ATOMICAS=False, SUBCHUNK_TOKENS=200))
    assert all("| Desde | Hasta | % |" in c.texto for c in con if "| 3" in c.texto)
    assert any("| Desde | Hasta | % |" not in c.texto for c in sin if "| 3" in c.texto)


def test_el_solape_no_arrastra_filas_de_una_tabla_aunque_el_texto_final_sea_corto():
    tabla = "\n".join(TABLA.split("\n")[:7])                                  # cabecera + 5 filas
    corto = "En ningún caso la porción variable podrá superar los dos mil dólares."
    largo = "Otro párrafo largo sin tablas. " * 20
    chunks = _empaquetar(["Intro.", tabla, corto, largo], presupuesto=90, solape=60)
    k = next(i for i, c in enumerate(chunks) if corto in c)
    assert k + 1 < len(chunks)
    siguiente = chunks[k + 1]
    assert "|" not in siguiente and siguiente.startswith("En ningún caso")        # solapa el texto corto, nunca filas de la tabla
