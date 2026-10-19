"""Agregación de marcas por artículo y controles sin base normativa (docs/09 §5). Python determinista, sin tokens.

Marcas del banco: A sí cumple · L parcialmente · R no cumple · X no aplica · P información obtenida de la normativa.
"""
from collections import Counter

from backend.models import Par


def _confianza(p: Par) -> float:
    return p.veredicto.confianza if p.veredicto else 0.0


def _score(p: Par) -> float:
    return max([x for x in (p.score_v1, p.score_v2) if x is not None], default=0.0)


def naturaleza_articulo(pares: list[Par]) -> str | None:
    """Moda de la naturaleza entre los pares con veredicto; ante empate, "obligacion" (el caso que exige más cuidado). None si ninguno tiene veredicto."""
    cuentas = Counter(p.veredicto.naturaleza_articulo for p in pares if p.veredicto)
    if not cuentas:
        return None
    mejor = max(cuentas.values())
    empatadas = [n for n, c in cuentas.items() if c == mejor]
    return "obligacion" if "obligacion" in empatadas else empatadas[0]


def marca_articulo(pares: list[Par]) -> tuple[str, list[Par]]:
    """`(marca, pares de respaldo)` de un artículo a partir de sus pares.

    A si algún par cubre totalmente (respaldo: el de mayor confianza); si no, L si alguno cubre parcialmente (1 sección, docs/14 #5);
    si no, R (el respaldo es el par más similar y el comentario explica la brecha). Un artículo sin ningún veredicto válido sale R:
    el llamador lo marca `requiere_revision` (nunca se presenta como cumplimiento).
    """
    validos = [p for p in pares if p.veredicto]
    nat = naturaleza_articulo(validos)
    if nat == "informativo":
        return "P", []
    if nat == "no_aplica_entidad":
        return "X", []
    tot = sorted((p for p in validos if p.veredicto.cobertura == "total"), key=_confianza, reverse=True)
    par = sorted((p for p in validos if p.veredicto.cobertura == "parcial"), key=_confianza, reverse=True)
    if tot:
        return "A", tot[:1]
    if par:
        return "L", par[:1]
    return "R", sorted(validos, key=_score, reverse=True)[:1]


def controles_sin_base(secciones_sel: list[str], pares: list[Par]) -> list[str]:
    """Vía 2: ids de las secciones seleccionadas del manual sin ningún par con cobertura total o parcial sobre un artículo de naturaleza "obligacion"."""
    por_articulo: dict[str, list[Par]] = {}
    for p in pares:
        por_articulo.setdefault(p.articulo_id, []).append(p)
    obligacion = {a for a, ps in por_articulo.items() if naturaleza_articulo(ps) == "obligacion"}
    con_base = {p.seccion_id for p in pares
                if p.veredicto and p.veredicto.cobertura in ("total", "parcial") and p.articulo_id in obligacion}
    return [s for s in secciones_sel if s not in con_base]
