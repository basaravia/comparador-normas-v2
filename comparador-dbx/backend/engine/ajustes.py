"""Ajustes por sesión (RF-19, docs/14 #33): una lista blanca de parámetros que el auditor puede cambiar sin tocar secretos, modelos ni límites de seguridad.

La lista, las etiquetas y los rangos viven en `config/ajustes.json`; los valores por defecto, en `config/defaults.env` (y el stage). Los cambios
viven en la sesión (memoria): el servidor no guarda nada más (CLAUDE.md regla 8).
"""
import json
import math
from dataclasses import replace

from backend.api.schemas import AjusteOut, AjustesOut
from backend.config import RAIZ, Settings, settings
from backend.core.errors import ComparadorError
from backend.core.sesiones import Sesion

RUTA = RAIZ / "config" / "ajustes.json"
MAX_CLAVES = 50


class AjusteInvalido(ComparadorError):
    codigo = "ERR-AJU-001"

    def __init__(self, mensaje: str):
        super().__init__(mensaje)
        self.mensaje_negocio = mensaje


def definicion() -> dict[str, dict]:
    return json.loads(RUTA.read_text(encoding="utf-8"))


def _limites(clave: str, d: dict, s: Settings) -> tuple[float, float]:
    """Rango efectivo: MAX_PARES nunca sube por encima del valor del stage (costo y tiempo)."""
    hasta = d["max"]
    if clave == "MAX_PARES":
        hasta = min(hasta, getattr(s, clave))
    return d["min"], hasta


def validar(valores: dict, s: Settings = settings) -> dict[str, float]:
    """Solo claves de la lista blanca (el resto se descarta), números dentro del rango y coherentes entre sí. Devuelve lo que difiere del defecto."""
    if not isinstance(valores, dict) or len(valores) > MAX_CLAVES:
        raise AjusteInvalido("Los ajustes no tienen un formato válido.")
    defs, ok = definicion(), {}
    for clave, d in defs.items():
        if clave not in valores:
            continue
        v = valores[clave]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise AjusteInvalido(f"«{d['etiqueta']}» debe ser un número.")
        if d["tipo"] == "entero":
            if v != int(v):
                raise AjusteInvalido(f"«{d['etiqueta']}» debe ser un número entero.")
            v = int(v)
        lo, hi = _limites(clave, d, s)
        if not lo <= v <= hi:
            raise AjusteInvalido(f"«{d['etiqueta']}» debe estar entre {lo:g} y {hi:g}.".replace(".", ","))
        if v != getattr(s, clave):
            ok[clave] = v
    efectivo = {**{k: getattr(s, k) for k in defs}, **ok}
    if efectivo["CITATION_SHOW_MIN"] > efectivo["CITATION_FUZZY_MIN"]:
        raise AjusteInvalido("La exigencia para mostrar una cita no puede ser mayor que la exigida para validarla como literal.")
    return ok


def efectivos(sesion: Sesion, s: Settings = settings) -> Settings:
    return replace(s, **sesion.ajustes)


def valores_usados(s: Settings) -> dict[str, float]:
    return {k: getattr(s, k) for k in definicion()}


def listar(sesion: Sesion, s: Settings = settings) -> AjustesOut:
    actual = efectivos(sesion, s)
    salida = []
    for clave, d in definicion().items():
        lo, hi = _limites(clave, d, s)
        salida.append(AjusteOut(clave=clave, etiqueta=d["etiqueta"], ayuda=d["ayuda"], tipo=d["tipo"], valor=getattr(actual, clave), defecto=getattr(s, clave),
                                minimo=lo, maximo=hi, paso=d["paso"], avanzado=d["avanzado"]))
    return AjustesOut(parametros=salida)


def guardar(sesion: Sesion, valores: dict, s: Settings = settings) -> AjustesOut:
    nuevos = validar(valores, s)
    with sesion.lock:
        sesion.ajustes = nuevos
    return listar(sesion, s)


def restablecer(sesion: Sesion, s: Settings = settings) -> AjustesOut:
    with sesion.lock:
        sesion.ajustes = {}
    return listar(sesion, s)
