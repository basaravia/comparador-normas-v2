"""Catálogo de patrones de seccionado (docs/07 §2, nivel 1), multi-esquema y fácil de extender.

Cada `Patron` reconoce UN esquema de encabezado. El **nivel** lo fija siempre el patrón (`rango`), nunca la
tipografía; la regla de "≥ 3 apariciones con numeración creciente" (o encabezado validado en negrita) decide
cuáles valen para un documento. La precedencia es la de docs/07: libro > título > capítulo > sección > artículo > numeral > literal.

Esquemas de numeración soportados (todos en `numero()`):
  romano      I.  II.  XII.  ·  LIBRO I  ·  Capítulo IV
  arábigo     1.  1.1  3.2.1  ·  Sección 2  ·  Capítulo 3
  letra       A.  B.  C.   (secciones)  ·  a)  b)  (literales: quedan dentro del texto)
  ordinal     PRIMERA  Primero  SEGUNDO  DÉCIMO PRIMERO  VIGÉSIMA  ÚNICA  ·  Capítulo Primero
  mixto       Artículo 5  ·  Art. 5  ·  Artículo 5-A  ·  Art. 5 bis  ·  ARTÍCULO ÚNICO

Cómo añadir un esquema (editar solo este archivo): 1) escribe la regex con los grupos `id` (texto del identificador) y
`num` (su numeración; `suf` opcional para el sufijo "A"/"bis"); 2) añade un `Patron(clave, nivel, rango, regex)` en
`PATRONES` en el orden "de más específico a más general"; 3) si usa un número nuevo, enséñaselo a `numero()`;
4) si la clave es nueva, dale una abreviatura en `ABREVIATURA` de `sectioner.py`. Reglas de oro: anclar con
`[ \\t]*` (nunca `^\\s*`), no poner dos cuantificadores `*`/`+` seguidos sobre el mismo carácter y acotar los espacios
(`{0,3}`); los patrones se aplican solo a la primera línea del bloque (≤ 300 caracteres), pero el catálogo se prueba con 100 KB hostiles.
"""
import re
from typing import NamedTuple

_I = re.IGNORECASE
_ROM = r"[IVXLCDM]+"
_UN = r"(?:PRIMER|SEGUND|TERCER|CUART|QUINT|SEXT|S[EÉ]PTIM|OCTAV|NOVEN)[OA]"                  # primero … noveno
_ORD = rf"(?:(?:D[EÉ]CIM|VIG[EÉ]SIM)[OA](?:[ \t]+{_UN})?|{_UN}|[ÚU]NIC[OA])"                    # DÉCIMO PRIMERO, Segunda, ÚNICA
_FIN = r"(?=[ \t]{0,3}\.?[ \t]{0,3}[-–—]|[ \t]*[.:]|[ \t]*$)"   # tras el identificador: ".-", "-", ".", ":" o fin de línea
_NUM = rf"{_ROM}|\d+|{_ORD}|[A-ZÁÉÍÓÚ]+"                          # número de libro/título/capítulo
_SUF = r"(?:-(?P<suf>[A-Z])|[ \t]+(?P<suf2>BIS|TER|QU[AÁ]TER))?"  # 5-A, 5 bis


class Patron(NamedTuple):
    clave: str            # nombre único del esquema
    nivel: str            # valor de `Seccion.nivel`
    rango: int | None     # profundidad (menor = más arriba); None = no abre sección
    regex: re.Pattern
    siempre: bool = False  # no necesita la regla de ≥ 3 (encabezados sin número, DISPOSICIONES GENERALES)


PATRONES = [
    Patron("libro", "libro", 0, re.compile(rf"[ \t]*(?P<id>LIBRO[ \t]+(?P<num>{_NUM}))\b", _I)),
    Patron("titulo", "titulo", 1, re.compile(rf"[ \t]*(?P<id>T[IÍ]TULO[ \t]+(?P<num>{_NUM}))\b", _I)),
    Patron("disposiciones", "disposiciones", 1, re.compile(
        r"[ \t]*(?P<id>DISPOSICIONES[ \t]+(GENERALES|TRANSITORIAS|REFORMATORIAS|DEROGATORIAS|FINALES|COMPLEMENTARIAS))\b", _I), True),
    Patron("capitulo", "capitulo", 2, re.compile(rf"[ \t]*(?P<id>CAP[IÍ]TULO[ \t]+(?P<num>{_NUM}))\b", _I)),
    Patron("seccion", "seccion", 3, re.compile(
        rf"[ \t]*(?P<id>(SECCI[OÓ]N|SEC\.?)[ \t]+(?P<num>{_ROM}|\d+(?:\.\d+)*|{_ORD}|[A-Z]))\b", _I)),
    Patron("romano", "seccion", 3, re.compile(rf"[ \t]*(?P<id>(?P<num>{_ROM})\.)[ \t]+[A-ZÁÉÍÓÚ]")),    # IV.  ALCANCE
    Patron("letra", "seccion", 3, re.compile(r"[ \t]*(?P<id>(?P<num>[A-Z])\.)[ \t]+[A-ZÁÉÍÓÚ]")),       # A.  Objetivo
    Patron("articulo", "articulo", 4, re.compile(
        rf"[ \t]*(?P<id>(ART[IÍ]CULO|ART\.?)[ \t]*(?P<num>\d+(?:\.\d+)*|{_ROM}|[ÚU]NICO){_SUF}){_FIN}", _I)),
    Patron("disposicion", "articulo", 4, re.compile(rf"[ \t]*(?P<id>(?P<num>{_ORD}))[ \t]{{0,3}}\.?[ \t]{{0,3}}[-–—]", _I)),  # PRIMERA.-
    Patron("disposicion_final", "articulo", 1, re.compile(
        rf"[ \t]*(?P<id>DISPOSICI[OÓ]N[ \t]+(FINAL|[ÚU]NICA|DEROGATORIA|TRANSITORIA)){_FIN}", _I), True),
    Patron("numeral", "numeral", 5, re.compile(r"[ \t]*(?P<id>(?P<num>\d{1,3}(?:\.\d{1,3}){0,4}))\.?[ \t]+[A-ZÁÉÍÓÚ]")),  # 3.2.1 Título
    Patron("literal", "literal", None, re.compile(r"[ \t]*(?P<id>(?:[a-z]|[ivx]+)\))[ \t]", _I)),        # a)  iv)
]

_VALOR_ROMANO = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_RAICES = [("PRIMER", 1), ("SEGUND", 2), ("TERCER", 3), ("CUART", 4), ("QUINT", 5), ("SEXT", 6), ("SEPTIM", 7),
           ("OCTAV", 8), ("NOVEN", 9), ("DECIM", 10), ("VIGESIM", 20), ("UNIC", 1)]
_SUFIJOS = {"BIS": 1, "TER": 2, "QUATER": 3}


def _romano(s: str) -> int | None:
    if not re.fullmatch(_ROM, s.upper()):
        return None
    v = [_VALOR_ROMANO[c] for c in s.upper()]
    return sum(-a if a < b else a for a, b in zip(v, v[1:] + [0]))


def _sin_tildes(s: str) -> str:
    return s.upper().translate(str.maketrans("ÁÉÍÓÚ", "AEIOU"))


def numero(texto: str | None, sufijo: str | None = None, es_letra: bool = False) -> tuple[int, ...] | None:
    """Numeración como tupla comparable: '3.2.1' → (3,2,1), 'IV' → (4,), 'DÉCIMO PRIMERO' → (11,), 'B' (letra) → (2,).
    `sufijo` ('A', 'bis') añade un último elemento: '5-A' → (5, 1), así 5 < 5-A < 6."""
    if not texto:
        return None
    if re.fullmatch(r"\d+(\.\d+)*", texto):
        base = tuple(int(x) for x in texto.split("."))
    elif es_letra and re.fullmatch(r"[A-Za-z]", texto):
        base = (ord(texto.upper()) - 64,)
    else:
        palabras = _sin_tildes(texto).split()
        valores = [next((v for r, v in _RAICES if p.startswith(r)), None) for p in palabras]
        if palabras and all(valores):
            base = (sum(valores),)
        elif (r := _romano(texto)):
            base = (r,)
        else:
            return None
    if sufijo:
        s = _sin_tildes(sufijo)
        base += (_SUFIJOS.get(s) or ord(s[0]) - 64,)
    return base


# Docling a veces junta varios artículos en un solo párrafo ("... masiva. Artículo 4.- El CONCLAFT ... Artículo 5.- ..."):
# Dos encabezados pegados en una línea ("VIII. CULTURA ORGANIZACIONAL 8.1 Capacitación al personal"): se corta antes de una numeración
# jerárquica seguida de mayúscula. Solo se aplica a bloques de tipo encabezado. Solo lookahead: búsqueda lineal.
CORTE_ENCABEZADOS = re.compile(r"(?<=\S)[ \t]+(?=\d{1,2}(?:\.\d{1,2}){1,4}[ \t]+[A-ZÁÉÍÓÚÑ])")

# Cola del documento: hojas de firmas y certificaciones que siguen al texto de la norma (p. ej. "FIRMAS DE RESPALDO …",
# "Firmado electrónicamente por: …", "CERTIFICACIÓN:"). Sin esto se pegan a la última sección. Anclado al inicio del bloque: sin backtracking.
COLA_DOCUMENTO = re.compile(r"[ \t]*(?:FIRMAS?[ \t]+DE[ \t]+RESPALDO|Firmado[ \t]+electr[óo]nicamente[ \t]+por|CERTIFICACI[ÓO]N[ \t]*:?[ \t]*$)", re.I)

# antes de buscar patrones el bloque se parte en esos puntos. Exige el ".-" tras el número y, dentro de una línea,
# que venga después de un punto, ";", ":" o comilla de cierre (así no corta "conforme al artículo 5 de esta Ley").
# Búsqueda lineal: los espacios antes del guion están acotados (`{0,3}`); dos `*` seguidos sobre el mismo carácter serían cuadráticos (appsec).
CORTE_ARTICULOS = re.compile(
    rf'(?:(?<=[.;:"”»])[ \t]+|\n[ \t]*)(?=(?:ART[IÍ]CULO|ART\.?)[ \t]*\d+(?:\.\d+)*{_SUF}[ \t]{{0,3}}\.?[ \t]{{0,3}}[-–—]'
    rf'|{_ORD}[ \t]{{0,3}}\.?[ \t]{{0,3}}[-–—])', _I)
