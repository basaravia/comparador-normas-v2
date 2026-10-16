"""Verificación de fragmentos citados por el LLM contra el texto literal (docs/09 §4).

El texto que llega al Excel es siempre el del documento fuente; el modelo solo propone fragmentos y aquí se comprueba, se corrige al texto real
(si se parece lo suficiente) y se calcula su posición. Python determinista: sin modelos.
"""
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from backend.config import Settings, settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Verificado:
    estado: str            # "exacto" | "corregido" | "dudoso" | "no_encontrado"
    ratio: float           # parecido con el texto real, 0-1
    inicio: int | None     # posición en el texto literal (None si no se pinta)
    fin: int | None
    texto_real: str        # fragmento del texto literal más cercano ("" si no hay)

    @property
    def verificado(self) -> bool:
        return self.estado in ("exacto", "corregido")


def _normalizar(texto: str) -> tuple[str, list[int]]:
    """Colapsa espacios y saltos de línea; devuelve el texto normalizado y, por carácter, su posición en el original."""
    salida, mapa, previo_blanco = [], [], True
    for i, c in enumerate(texto):
        if c.isspace():
            if not previo_blanco:
                salida.append(" "); mapa.append(i)
            previo_blanco = True
        else:
            salida.append(c); mapa.append(i); previo_blanco = False
    while salida and salida[-1] == " ":
        salida.pop(); mapa.pop()
    return "".join(salida), mapa


def _original(mapa: list[int], texto: str, ini: int, fin: int) -> tuple[int, int]:
    """Traslada [ini, fin) del texto normalizado al texto original (el fin incluye el último carácter no blanco)."""
    return mapa[ini], mapa[fin - 1] + 1


def verificar_fragmento(fragmento: str, texto: str, desde: int = 0, s: Settings = settings) -> Verificado:
    """Busca `fragmento` en `texto` (texto_literal). `desde` = posición donde acabó el fragmento anterior (los requisitos siguen el orden del artículo).

    Subcadena exacta tras normalizar espacios → verificado. Si no, ventana más parecida (difflib): ratio >= CITATION_FUZZY_MIN → se reemplaza por
    el texto real; >= CITATION_SHOW_MIN → dudoso (se muestra el real con aviso, no se pinta); menos → no encontrado.
    """
    f, _ = _normalizar(fragmento)
    t, mapa = _normalizar(texto)
    if not f or not t:
        return Verificado("no_encontrado", 0.0, None, None, "")
    # Posición mínima en el texto normalizado: primer carácter normalizado cuya posición original sea >= desde.
    base = next((k for k, p in enumerate(mapa) if p >= desde), len(t))
    i = t.find(f, base)
    if i < 0:
        i = t.find(f)                      # el orden esperado falló: la primera ocurrencia en cualquier posición
        if i >= 0:
            log.warning("Fragmento repetido o fuera de orden: se usa la primera ocurrencia.")
    if i >= 0:
        ini, fin = _original(mapa, texto, i, i + len(f))
        return Verificado("exacto", 1.0, ini, fin, texto[ini:fin])
    ini_n, fin_n, ratio = _mas_parecido(f, t)
    if ratio >= s.CITATION_FUZZY_MIN:
        ini, fin = _original(mapa, texto, ini_n, fin_n)
        return Verificado("corregido", ratio, ini, fin, texto[ini:fin])
    if ratio >= s.CITATION_SHOW_MIN:
        ini, fin = _original(mapa, texto, ini_n, fin_n)
        return Verificado("dudoso", ratio, None, None, texto[ini:fin])
    return Verificado("no_encontrado", ratio, None, None, "")


def _mas_parecido(f: str, t: str) -> tuple[int, int, float]:
    """Ventana del texto normalizado más parecida a `f`: se ancla en el bloque común más largo y se afina con SequenceMatcher."""
    sm = SequenceMatcher(None, t, f, autojunk=False)
    bloque = max(sm.get_matching_blocks(), key=lambda b: b.size)
    if bloque.size == 0:
        return 0, 0, 0.0
    centro = bloque.a - bloque.b
    mejor = (0, 0, 0.0)
    holgura = max(10, len(f) // 10)
    for ini in range(max(0, centro - holgura), min(len(t), centro + holgura) + 1, max(1, holgura // 5)):
        for largo in (len(f) - holgura // 2, len(f), len(f) + holgura // 2):
            fin = min(len(t), ini + max(largo, 1))
            if fin <= ini:
                continue
            r = SequenceMatcher(None, t[ini:fin], f, autojunk=False).ratio()
            if r > mejor[2]:
                mejor = (ini, fin, r)
    return mejor
