"""Secciones que no sirven para comparar (docs/07 §2b, docs/14 #24): carátula, preámbulo, índice, control de versiones, anexos…

Clasificación DETERMINISTA por el título de la sección (sin LLM, CLAUDE.md regla 3). El catálogo de abajo son datos: para añadir o quitar una
categoría se edita `CATALOGO`, no el código. Una sección hereda la exclusión de su ancestro (todo lo que cuelga de "ANEXOS" queda fuera).
No se toca el contrato `Seccion`: el resultado vive en la tabla de recuperación (columnas `Incluir` y `Motivo`) y el auditor puede cambiarlo.
"""
import re
import unicodedata
from typing import NamedTuple

from backend.models import Seccion

AMBOS, NORMA, MANUAL = {"normativa", "manual_control"}, {"normativa"}, {"manual_control"}


class Regla(NamedTuple):
    categoria: str          # motivo que ve el auditor
    patron: re.Pattern      # sobre el título normalizado (sin tildes, minúsculas, sin signos)
    aplica_a: set[str]      # tipos de documento
    max_profundidad: int | None = None   # solo en capítulos y sus hijos directos (len(ruta) <= n); None = a cualquier profundidad
    max_palabras: int | None = None      # solo si el título es corto: un título largo suele ser una frase del cuerpo ("Introducción de nuevos clientes: …")


def _r(categoria: str, patron: str, aplica_a: set[str], max_profundidad: int | None = None, max_palabras: int | None = None) -> Regla:
    return Regla(categoria, re.compile(patron), aplica_a, max_profundidad, max_palabras)


# Normas: solo carátula, índice y considerandos; las disposiciones y los anexos de una norma SE INCLUYEN (decisión del usuario, 8 oct 2026).
# Manuales: además preámbulo, control de versiones, correspondencia con lineamientos, registro de elaboración y anexos.
# Los títulos se escriben libremente, así que las reglas son estrictas: título entero o corto (appsec, 8 oct 2026: falsos positivos).
CATALOGO: list[Regla] = [
    _r("carátula", r"^(portada|caratula|hoja de (presentacion|titulo|control)|datos del documento|documentacion de procesos)$", AMBOS, max_palabras=4),
    _r("índice", r"^(indice( general)?|tabla de contenidos?|contenidos?)$", AMBOS),
    _r("considerandos", r"^(considerandos?|exposicion de motivos|motivacion)$", NORMA, max_palabras=4),
    _r("revisión y aprobación", r"\b(revision y aprobacion|aprobacion del documento)\b", MANUAL, max_palabras=6),
    _r("revisión y aprobación", r"^(control|historial) de (cambios|versiones)( y (cambios|versiones))?$", MANUAL),
    _r("correspondencia con lineamientos", r"\bcorrespondencia con (los )?lineamientos\b", MANUAL, max_palabras=8),
    _r("registro de elaboración", r"\bregistro de (elaboracion|actualizacion)\b|\belaboracion actualizacion\b", MANUAL, max_palabras=6),
    _r("preámbulo", r"^(introduccion|objetivos?( del manual| general| principal| especificos?)?|alcance( del manual)?|antecedentes|presentacion|"
                    r"generalidades|marco (general|normativo|conceptual)|base normativa|normativa nacional)\b", MANUAL,
       max_profundidad=1, max_palabras=5),     # "Objetivos" o "Base normativa" dentro de un procedimiento (5.4.1, 5.3.10.1) SON cuerpo del manual
    _r("anexo", r"^(anexos?|apendices?)\b|^metodologias anexas$|^manual de usuario$", MANUAL),
    _r("anexo", r"\b(anexo|apendice)s?\b", MANUAL, max_profundidad=1, max_palabras=6),     # "…según el Anexo 3" dentro de un procedimiento no es un anexo
]


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sin_tildes.casefold()).split())


def _titulo(s: Seccion) -> str:
    """Título sin numeración: el de la sección o, si el seccionador no lo aceptó, la primera línea sin su identificador."""
    if s.titulo:
        return _normalizar(s.titulo)
    primera = s.texto_literal.strip().split("\n", 1)[0]
    # el identificador solo se quita si es una palabra completa ("I" de "I. INTRODUCCIÓN", no la "I" de "INTRODUCCIÓN")
    return _normalizar(re.sub(rf"^{re.escape(s.identificador)}(?![0-9A-Za-zÁÉÍÓÚÑáéíóúñ])[\s.:\-–—]*", "", primera))


def motivo_propio(s: Seccion) -> str | None:
    """Categoría del catálogo que corresponde al título de la sección, o None si es cuerpo del documento."""
    titulo = _titulo(s)
    for r in CATALOGO:
        if (s.tipo_doc in r.aplica_a and r.patron.search(titulo) and (r.max_profundidad is None or len(s.ruta) <= r.max_profundidad)
                and (r.max_palabras is None or len(titulo.split()) <= r.max_palabras)):
            return r.categoria
    return None


def clasificar_secciones(secciones: list[Seccion]) -> dict[str, tuple[bool, str]]:
    """`{id: (incluir, motivo)}`. Se recorren en orden de documento: una sección hereda la exclusión de su ancestro más cercano excluido.

    `motivo` es "" si se incluye; "anexo" si el título lo es; "anexo (hereda de XII)" si lo es un ancestro."""
    resultado: dict[str, tuple[bool, str]] = {}
    pila: list[tuple[int, str, str]] = []            # (profundidad, identificador, motivo) de los ancestros excluidos
    for s in secciones:
        profundidad = len(s.ruta)
        while pila and pila[-1][0] >= profundidad:
            pila.pop()
        propio = motivo_propio(s)
        if propio:
            pila.append((profundidad, s.identificador, propio))
            resultado[s.id] = (False, propio)
        elif pila:
            _, ident, motivo = pila[-1]
            resultado[s.id] = (False, f"{motivo} (hereda de {ident})")
        else:
            resultado[s.id] = (True, "")
    return resultado
