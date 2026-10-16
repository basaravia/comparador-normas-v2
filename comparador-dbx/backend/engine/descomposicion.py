"""Paso 3a (docs/09 §3a): el LLM descompone cada artículo en requisitos atómicos; Python verifica, renumera y controla.

Reutiliza `ModelClient.chat_json` (JSON validado con Pydantic, 1 reintento). Prompt: backend/prompts/requisitos.md.
"""
import hashlib
import logging
import re
from pathlib import Path

from backend.config import Settings, settings
from backend.engine.verificacion import verificar_fragmento
from backend.llm.client import ModelClient
from backend.models.schemas import Descomposicion, DescomposicionLLM, Requisito, Seccion

log = logging.getLogger(__name__)
PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "requisitos.md"
LITERAL = re.compile(r"(?m)^\s*([a-z])\)\s")


def armar_descomposicion(articulo: Seccion, d: DescomposicionLLM, s: Settings = settings) -> Descomposicion:
    """Parte determinista: verifica cada fragmento contra el artículo, renumera R1…Rn y aplica los controles de §3a."""
    texto = articulo.texto_literal
    motivos: list[str] = []
    if d.naturaleza_articulo != "obligacion":
        return Descomposicion(articulo_id=articulo.id, naturaleza_articulo=d.naturaleza_articulo)
    propuestos = d.requisitos
    if len(propuestos) > s.MAX_REQUISITOS:
        motivos.append(f"El artículo trae más de {s.MAX_REQUISITOS} requisitos; se conservan los primeros.")
        propuestos = propuestos[:s.MAX_REQUISITOS]
    reqs, desde, cubierto = [], 0, [False] * len(texto)
    for k, r in enumerate(propuestos, 1):
        v = verificar_fragmento(r.fragmento, texto, desde, s)
        if v.verificado:
            desde = v.fin
            for i in range(v.inicio, v.fin):
                cubierto[i] = True
        else:
            motivos.append(f"El requisito R{k} no se pudo ubicar en el texto del artículo.")
        reqs.append(Requisito(id=f"R{k}", fragmento=v.texto_real if v.verificado else r.fragmento, obligatorio=r.obligatorio,
                              verificado=v.verificado, inicio=v.inicio, fin=v.fin))
    sin_cubrir = sum(1 for c, ch in zip(cubierto, texto) if not c and not ch.isspace())
    if sin_cubrir > s.MAX_TEXTO_SIN_REQUISITO:
        motivos.append("Parte del texto del artículo no quedó en ningún requisito.")
    marcas = list(LITERAL.finditer(texto))                # cada literal a), b)… (hasta el siguiente) debe tocar al menos un requisito
    for k, m in enumerate(marcas):
        fin_literal = marcas[k + 1].start() if k + 1 < len(marcas) else len(texto)
        if not any(r.inicio is not None and r.inicio < fin_literal and r.fin > m.start() for r in reqs):
            motivos.append(f"El literal {m.group(1)}) no quedó en ningún requisito.")
    if not any(r.obligatorio for r in reqs):
        motivos.append("Un artículo de obligación no trae requisitos obligatorios.")
    return Descomposicion(articulo_id=articulo.id, naturaleza_articulo="obligacion", requisitos=reqs, requiere_revision=bool(motivos), motivos=motivos)


def _huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def descomponer(articulo: Seccion, cliente: ModelClient, cache: dict[str, Descomposicion] | None = None, s: Settings = settings) -> Descomposicion:
    """1 llamada al LLM por artículo (con caché por SHA-256 del texto, §3a d). Un artículo `obligacion` sin requisitos obligatorios se reintenta
    una vez; si persiste queda `requiere_revision` y nunca A (decisión del usuario, 15 oct 2026)."""
    clave = _huella(articulo.texto_literal)
    if cache is not None and clave in cache:
        return cache[clave].model_copy(update={"articulo_id": articulo.id})
    sistema = PROMPT.read_text(encoding="utf-8")
    usuario = f"<articulo>\nRuta: {' > '.join(articulo.ruta)}\n{articulo.texto_literal}\n</articulo>"
    for intento in (1, 2):
        d = cliente.chat_json(sistema, usuario, DescomposicionLLM)
        if d.naturaleza_articulo != "obligacion" or any(r.obligatorio for r in d.requisitos):
            break
        log.warning("Paso 3a sin requisitos obligatorios en %s (intento %d)", articulo.identificador, intento)
    res = armar_descomposicion(articulo, d, s)
    if cache is not None:
        cache[clave] = res
    return res
