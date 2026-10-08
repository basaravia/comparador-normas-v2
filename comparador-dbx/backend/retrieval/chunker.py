"""Sub-chunking por sección (docs/08).

Adaptado de `chunking.py` de la v6 (modelo parent-child): se indexa el sub-chunk, se devuelve la
sección. Se conserva la idea de cortar por fronteras del documento (párrafos, numerales, literales)
y no cada N caracteres, el solape de unas palabras y la estimación de tokens por palabras.
Sin pandas, sin LangChain; el presupuesto y el solape salen de `settings`.

El texto literal de la sección nunca se altera: el prefijo de contexto solo va en el texto a embeber.
"""
import math
import re

from backend.config import Settings, settings
from backend.models import Seccion, SubChunk

TOKENS_POR_PALABRA = 1.35  # español jurídico (valor de la v6); la estimación cae del lado seguro
PRESUPUESTO_MINIMO = 32    # si el prefijo se come el presupuesto, el cuerpo no baja de aquí

# Un numeral (1. 1.1. 1) 1.-) o literal (a) (a) a.-) abre ítem solo al inicio de línea o tras . ; :
_MARCADOR = re.compile(r"(?:\d+(?:\.\d+)*\s*(?:\.-|[.)-])|\(?[a-zA-ZñÑ](?:\.-|[.)]))(?=\s)")
_FRASE = re.compile(r"(?<=[.;:])\s+")


def estimar_tokens(texto: str) -> int:
    return math.ceil(len(texto.split()) * TOKENS_POR_PALABRA)


def _es_frontera(texto: str, i: int) -> bool:
    """¿El marcador en `i` abre un ítem? Mira solo los caracteres anteriores más cercanos (costo constante)."""
    if i <= len(texto) - len(texto.lstrip()):
        return True                      # solo hay espacios antes
    if not texto[i - 1].isspace():
        return False                     # "USD 2.500.000": el "500." es parte de un número
    j = i - 1
    while texto[j].isspace():            # último carácter útil antes del marcador
        j -= 1
    return texto[j] in ".;:"


def _es_fila_tabla(linea: str) -> bool:
    return linea.lstrip().startswith("|")


def _unidades(texto: str, tablas: bool = True) -> list[str]:
    """Texto -> párrafos, numerales y literales. Con `tablas`, las filas Markdown consecutivas (`| a | b |`) son UNA unidad."""
    salida = []
    lineas, i = texto.split("\n"), 0
    while i < len(lineas):
        if tablas and _es_fila_tabla(lineas[i]):
            j = i
            while j < len(lineas) and _es_fila_tabla(lineas[j]):
                j += 1
            salida.append("\n".join(x.strip() for x in lineas[i:j]))
            i = j
            continue
        parrafo, i = lineas[i], i + 1
        cortes = [m.start() for m in _MARCADOR.finditer(parrafo) if m.start() > 0 and _es_frontera(parrafo, m.start())]
        limites = [0, *cortes, len(parrafo)]
        salida += [parrafo[a:b].strip() for a, b in zip(limites, limites[1:])]
    return [u for u in salida if u]


_SEPARADOR_TABLA = re.compile(r"\|[\s:|-]+\|")


def _partir_tabla(tabla: str, presupuesto: int) -> list[tuple[str, bool]]:
    """Una tabla que no cabe se parte por filas y **cada trozo repite la cabecera** (como `repeat_table_header` de Docling).

    Un trozo lleva al menos una fila. Devuelve `(pieza, True)`: la cabecera ya da el contexto, no se añade solape."""
    filas = tabla.split("\n")
    n = 2 if len(filas) > 1 and _SEPARADOR_TABLA.fullmatch(filas[1].strip()) else 1
    cabecera, cuerpo = filas[:n], filas[n:]
    piezas, actual = [], []
    for fila in cuerpo:
        if actual and estimar_tokens("\n".join([*cabecera, *actual, fila])) > presupuesto:
            piezas.append("\n".join([*cabecera, *actual]))
            actual = []
        actual.append(fila)
    if actual or not piezas:
        piezas.append("\n".join([*cabecera, *actual]))
    return [(p, k > 0) for k, p in enumerate(piezas)]


def _partir_largo(unidad: str, presupuesto: int, solape: int = 0) -> list[tuple[str, bool]]:
    """Una unidad que no cabe se parte por frases y, si aún no cabe, por palabras con ventana deslizante.

    Devuelve `(pieza, ya_solapada)`: las ventanas de palabras posteriores a la primera ya traen su solape."""
    piezas = []
    por_pieza = max(1, int(presupuesto / TOKENS_POR_PALABRA))
    paso = max(1, por_pieza - int(solape / TOKENS_POR_PALABRA))   # ventana deslizante: el solape va dentro de las piezas
    for frase in _FRASE.split(unidad):
        if estimar_tokens(frase) <= presupuesto:
            piezas.append((frase, False))
        else:
            palabras = frase.split()
            piezas += [(" ".join(palabras[i:i + por_pieza]), i > 0)
                       for i in range(0, max(1, len(palabras) - por_pieza + paso), paso)]
    return piezas


def _cola(piezas: list[str], palabras: int, tablas: bool) -> str:
    """Las últimas `palabras` palabras del chunk, sin retroceder nunca por encima de una tabla (sus filas no sirven de solape)."""
    cola: list[str] = []
    for pieza in reversed(piezas):
        if tablas and _es_fila_tabla(pieza):
            break
        cola = pieza.split() + cola
        if len(cola) >= palabras:
            break
    return " ".join(cola[-palabras:])


def _empaquetar(unidades: list[str], presupuesto: int, solape: int, tablas: bool = True) -> list[str]:
    """Agrupa unidades hasta `presupuesto` tokens; cada chunk repite las últimas `solape` tokens del anterior."""
    chunks, actual, palabras = [], [], 0       # `palabras` acumuladas: evita re-unir `actual` en cada pieza
    for unidad in unidades:
        if estimar_tokens(unidad) <= presupuesto:
            partes = [(unidad, False)]
        elif tablas and _es_fila_tabla(unidad):
            partes = _partir_tabla(unidad, presupuesto)
        else:
            partes = _partir_largo(unidad, presupuesto, solape)
        for pieza, solapada in partes:
            n = len(pieza.split())
            if actual and math.ceil((palabras + n) * TOKENS_POR_PALABRA) > presupuesto:
                cerrado = " ".join(actual)
                chunks.append(cerrado)
                cola = _cola(actual, max(1, int(solape / TOKENS_POR_PALABRA)), tablas) if solape > 0 else ""
                cabe = int(presupuesto / TOKENS_POR_PALABRA) - n     # palabras de solape que caben junto a la pieza
                cola = " ".join(cola.split()[-cabe:]) if cabe > 0 and not solapada else ""   # sin salirse del presupuesto
                actual, palabras = ([cola, pieza], len(cola.split()) + n) if cola else ([pieza], n)
            else:
                actual.append(pieza)
                palabras += n
    if actual:
        chunks.append(" ".join(actual))
    return chunks


def prefijo(seccion: Seccion, documento: str) -> str:
    """`"{documento} > {ruta} > {identificador}: "` (docs/08)."""
    return " > ".join([documento, *seccion.ruta, seccion.identificador]) + ": "


def subchunkear(seccion: Seccion, documento: str | None = None, s: Settings = settings) -> list[SubChunk]:
    """Sub-chunks de una sección (~`SUBCHUNK_TOKENS`, solape `SUBCHUNK_OVERLAP`). Una sección corta es uno solo.

    El texto de cada sub-chunk es un trozo literal de la sección; el prefijo cuenta en el presupuesto.
    """
    texto = seccion.texto_literal.strip()
    gastado = estimar_tokens(prefijo(seccion, documento or seccion.doc_id))
    if estimar_tokens(texto) + gastado <= s.SUBCHUNK_TOKENS:
        piezas = [texto]
    else:
        presupuesto = max(s.SUBCHUNK_TOKENS - gastado, PRESUPUESTO_MINIMO)
        piezas = _empaquetar(_unidades(texto, s.TABLAS_ATOMICAS), presupuesto, int(presupuesto * s.SUBCHUNK_OVERLAP), s.TABLAS_ATOMICAS) or [texto]
    return [SubChunk(id=f"{seccion.id}#c{i}", seccion_id=seccion.id, texto=p, orden=i) for i, p in enumerate(piezas)]


def texto_a_embeber(seccion: Seccion, sub: SubChunk, documento: str | None = None) -> str:
    return prefijo(seccion, documento or seccion.doc_id) + sub.texto
