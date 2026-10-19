"""Agregación de marcas y controles sin base (docs/09 §5, backend/engine/agregacion.py). Tablas de verdad, sin modelo."""
from backend.engine.agregacion import controles_sin_base, marca_articulo, naturaleza_articulo
from datos_papel import par, veredicto


def ps(*specs, art="A1"):
    """(nat, cobertura, confianza, score) -> pares del artículo."""
    return [par(f"P{i}", art, f"S{i}", veredicto(nat=n, cob=c, conf=cf), s1=sc, r1=1) for i, (n, c, cf, sc) in enumerate(specs)]


def test_total_gana_y_el_respaldo_es_el_de_mayor_confianza():
    marca, resp = marca_articulo(ps(("obligacion", "parcial", .99, .9), ("obligacion", "total", .6, .5), ("obligacion", "total", .8, .4)))
    assert marca == "A" and [p.id for p in resp] == ["P2"]


def test_parcial_sin_total_es_L_con_una_seccion():
    marca, resp = marca_articulo(ps(("obligacion", "parcial", .5, .5), ("obligacion", "parcial", .9, .4), ("obligacion", "nula", .9, .9)))
    assert marca == "L" and [p.id for p in resp] == ["P1"]


def test_todo_nulo_es_R_con_el_par_mas_similar_de_respaldo():
    marca, resp = marca_articulo(ps(("obligacion", "nula", .9, .3), ("obligacion", "nula", .9, .7)))
    assert marca == "R" and [p.id for p in resp] == ["P1"]


def test_naturaleza_informativa_es_P_y_no_aplica_es_X():
    assert marca_articulo(ps(("informativo", "nula", .9, .5), ("informativo", "nula", .8, .4))) == ("P", [])
    assert marca_articulo(ps(("no_aplica_entidad", "nula", .9, .5))) == ("X", [])


def test_empate_de_naturaleza_cuenta_como_obligacion():
    assert naturaleza_articulo(ps(("informativo", "nula", .9, .5), ("obligacion", "nula", .9, .5))) == "obligacion"


def test_sin_veredictos_no_es_cumplimiento_sale_R_sin_respaldo():
    sin = [par("P1", "A1", "S1", None)]
    assert naturaleza_articulo(sin) is None
    assert marca_articulo(sin) == ("R", [])


def test_controles_sin_base_solo_sobre_articulos_de_obligacion():
    pares = [par("P1", "A1", "S1", veredicto(cob="total")), par("P2", "A1", "S2", veredicto(cob="nula")),
             par("P3", "A2", "S3", veredicto(nat="informativo", cob="total")), par("P4", "A2", "S2", veredicto(nat="informativo", cob="nula"))]
    assert controles_sin_base(["S1", "S2", "S3", "S4"], pares) == ["S2", "S3", "S4"]    # S3: su único par es de un artículo informativo; S4: sin pares
