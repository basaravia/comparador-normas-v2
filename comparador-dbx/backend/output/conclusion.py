"""Borrador de conclusión (docs/10): UNA llamada al LLM, con el resumen calculado en Python.

El modelo solo redacta; el código calcula las cifras y verifica que el texto no traiga otras
(docs/09 §4, OWASP LLM09). Si el borrador no cumple, `LLMOutputError`: la conclusión queda
vacía para que la escriba el auditor (el fallo de contenido degrada, no aborta).
"""
import json
import re

from pydantic import BaseModel, field_validator

from backend.config import cargar_prompt, rellenar_prompt
from backend.core.errors import LLMOutputError
from backend.output.workpaper import EntradaPapel, conteos_papel

MIN_PALABRAS, MAX_PALABRAS = 120, 220
MAX_LISTA = 10          # artículos R o L que se envían al modelo (acota los tokens, LLM10)
MAX_FALTANTES = 3       # elementos faltantes por artículo
MAX_TEXTO = 200         # caracteres por elemento faltante


class BorradorConclusion(BaseModel):
    borrador_conclusion: str

    @field_validator("borrador_conclusion")
    @classmethod
    def no_vacio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("borrador vacío")
        return v.strip()


def _lista(entrada: EntradaPapel, marca: str) -> list[dict]:
    return [{"identificador": f.articulo.identificador,
             "elementos_faltantes": [e[:MAX_TEXTO] for e in f.elementos_faltantes[:MAX_FALTANTES]]}
            for f in entrada.filas if f.marca == marca]


def resumen_conclusion(entrada: EntradaPapel) -> dict:
    """Todas las cifras del borrador salen de aquí (Python determinista)."""
    c = conteos_papel(entrada)
    evaluables = c["A"] + c["L"] + c["R"]
    r, l = _lista(entrada, "R"), _lista(entrada, "L")
    return {
        "manual": entrada.manual.nombre,
        "normativas": [d.nombre for d in entrada.normativas],
        "total_articulos": len(entrada.filas),
        "conteos_por_marca": c,
        "articulos_evaluables_A_L_R": evaluables,
        "porcentaje_por_marca_sobre_total": {m: round(100 * n / len(entrada.filas), 1) if entrada.filas else 0
                                             for m, n in c.items()},
        "porcentaje_cumple_sobre_evaluables": round(100 * c["A"] / evaluables, 1) if evaluables else 0,
        "porcentaje_parcial_sobre_evaluables": round(100 * c["L"] / evaluables, 1) if evaluables else 0,
        "porcentaje_no_cumple_sobre_evaluables": round(100 * c["R"] / evaluables, 1) if evaluables else 0,
        "articulos_R": r[:MAX_LISTA], "otros_articulos_R": max(0, len(r) - MAX_LISTA),
        "articulos_L": l[:MAX_LISTA], "otros_articulos_L": max(0, len(l) - MAX_LISTA),
        "controles_sin_base_normativa": [s.identificador for s in entrada.controles_sin_base[:MAX_LISTA]],
        "total_controles_sin_base": len(entrada.controles_sin_base),
    }


def _numeros(texto: str) -> set[float]:
    return {float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", texto)}


def cifras_no_entregadas(texto: str, resumen: dict) -> list[float]:
    """Cifras del borrador que no están en el resumen (debe salir vacía)."""
    return sorted(_numeros(texto) - _numeros(json.dumps(resumen, ensure_ascii=False)))


def validar_borrador(texto: str, resumen: dict) -> None:
    """Función pura: 120–220 palabras y ninguna cifra fuera del resumen. Si no, `LLMOutputError`."""
    palabras = len(texto.split())
    if not MIN_PALABRAS <= palabras <= MAX_PALABRAS:
        raise LLMOutputError(f"Borrador de {palabras} palabras (se piden {MIN_PALABRAS}-{MAX_PALABRAS})")
    if extra := cifras_no_entregadas(texto, resumen):
        raise LLMOutputError(f"El borrador trae cifras que no están en el resumen: {extra}")


def generar_borrador(entrada: EntradaPapel, cliente) -> str:
    """Una sola llamada a `cliente.chat_json`. Devuelve el borrador SIN prefijo (lo añade el papel)."""
    resumen = resumen_conclusion(entrada)
    sistema, usuario = cargar_prompt("conclusion")
    usuario = rellenar_prompt(usuario, resumen_json=json.dumps(resumen, ensure_ascii=False, indent=1))
    texto = cliente.chat_json(sistema, usuario, BorradorConclusion).borrador_conclusion
    validar_borrador(texto, resumen)
    return texto
