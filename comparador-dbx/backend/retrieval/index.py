"""Índices FAISS por tipo de documento (docs/08).

Un `Indice` guarda los sub-chunks de las secciones de UN tipo (normativa o manual), sus vectores
(float32, norma 1) y el mapa `subchunk -> seccion_id`. Con vectores normalizados, el producto
interno de `IndexFlatIP` es el coseno. Los embeddings son los reales del stage (`ModelClient.embed`),
por lotes de `EMB_BATCH`, con caché en memoria por SHA-256 del texto. Un índice por stage y por modelo
de embeddings: no se mezclan (OWASP LLM08).
"""
from typing import Callable
import hashlib
import logging
import os

import faiss
import numpy as np

from backend.core.errors import ComparadorError
from backend.llm.client import ModelClient
from backend.models import Seccion, SubChunk
from backend.retrieval.chunker import subchunkear, texto_a_embeber

log = logging.getLogger(__name__)

MAX_CACHE = 20000                      # vectores en memoria (acota la RAM: 20 000 x 1024 x 4 B ~ 80 MB)
_CACHE: dict[str, np.ndarray] = {}     # sha256(modelo + texto) -> vector
_DIMS: dict[str, int] = {}             # modelo -> dimensión ya vista (un modelo no cambia de dimensión)


class IndiceError(ComparadorError):
    """Embeddings o consultas inválidos. Es de infraestructura: la corrida **aborta**, nunca se mezclan modelos."""
    codigo = "ERR-IDX-001"
    mensaje_negocio = "No pudimos preparar la búsqueda de coincidencias. Intenta de nuevo o consulta con soporte."


def _modelo(cliente: ModelClient) -> str:
    """Identifica stage + proveedor + modelo de embeddings: la caché y los índices no se mezclan entre ellos (LLM08)."""
    return f"{os.environ.get('STAGE', '')}|{cliente.s.EMB_PROVIDER}|{cliente.emb()[1]}"


def _validar(vectores: np.ndarray, n: int) -> None:
    if vectores.ndim != 2 or vectores.shape[0] != n:
        raise IndiceError(f"El modelo devolvió {vectores.shape} vectores para {n} textos")
    if not np.isfinite(vectores).all() or not (np.linalg.norm(vectores, axis=1) > 0).all():
        raise IndiceError("El modelo devolvió vectores con NaN, inf o norma cero")


def embeber(textos: list[str], cliente: ModelClient, progreso: Callable[[int, int], None] | None = None) -> np.ndarray:
    """Vectores de los textos; solo los que no están en la caché llaman al modelo."""
    if not textos:
        return np.empty((0, 0), dtype=np.float32)
    modelo = _modelo(cliente)
    claves = [hashlib.sha256(f"{modelo}\x00{t}".encode("utf-8")).hexdigest() for t in textos]
    nuevos = {c: t for c, t in zip(claves, textos) if c not in _CACHE}
    vectores = {c: _CACHE[c] for c in claves if c in _CACHE}
    log.info("Embeddings: %d textos, %d nuevos (el resto sale de la caché)", len(textos), len(nuevos))
    if nuevos:
        pendientes = list(nuevos.values())   # lotes de EMB_BATCH dentro del cliente
        lote = np.asarray(cliente.embed(pendientes, progreso) if progreso else cliente.embed(pendientes), dtype=np.float32)
        _validar(lote, len(nuevos))
        if _DIMS.setdefault(modelo, lote.shape[1]) != lote.shape[1]:
            raise IndiceError(f"Dimensión {lote.shape[1]} distinta de la ya vista para {modelo} ({_DIMS[modelo]})")
        vectores.update(zip(nuevos, lote))
        for c, v in zip(nuevos, lote):
            _CACHE[c] = v
        while len(_CACHE) > MAX_CACHE:          # tope también dentro de un lote grande
            _CACHE.pop(next(iter(_CACHE)))
    return np.array([vectores[c] for c in claves], dtype=np.float32)


def limpiar_cache() -> None:
    _CACHE.clear()
    _DIMS.clear()


class Indice:
    def __init__(self, subchunks: list[SubChunk], vectores: np.ndarray):
        vectores = np.asarray(vectores, dtype=np.float32)
        _validar(vectores, len(subchunks))
        self.subchunks = subchunks
        self.vectores = vectores
        self.mapa = [sc.seccion_id for sc in subchunks]       # subchunk_idx -> seccion_id
        self.faiss = faiss.IndexFlatIP(vectores.shape[1])
        self.faiss.add(vectores)

    def __len__(self) -> int:
        return len(self.subchunks)

    def vectores_de(self, seccion_id: str) -> np.ndarray:
        """Vectores de los sub-chunks de una sección (las consultas de la vía de origen)."""
        pos = [i for i, s in enumerate(self.mapa) if s == seccion_id]
        if not pos:
            raise IndiceError(f"La sección {seccion_id!r} no está en el índice")
        return self.vectores[pos]

    def filtrar(self, seccion_ids: set[str]) -> "Indice":
        """Subíndice temporal solo con las secciones seleccionadas."""
        pos = [i for i, s in enumerate(self.mapa) if s in seccion_ids]
        if not pos:
            raise IndiceError("Ninguna de las secciones seleccionadas está en el índice")
        return Indice([self.subchunks[i] for i in pos], self.vectores[pos])

    def buscar(self, consulta: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        """`(scores, posiciones)` de los k vecinos de cada fila de `consulta`."""
        consulta = np.asarray(consulta, dtype=np.float32)
        if consulta.ndim != 2 or consulta.shape[1] != self.vectores.shape[1] or len(consulta) == 0:
            raise IndiceError(f"Consulta {consulta.shape} incompatible con índice de dimensión {self.vectores.shape[1]}")
        if not np.isfinite(consulta).all():
            raise IndiceError("La consulta contiene valores no finitos (NaN o inf)")
        return self.faiss.search(consulta, min(k, len(self)))


def construir_indice(secciones: list[Seccion], cliente: ModelClient, documentos: dict[str, str] | None = None,
                     progreso: Callable[[int, int], None] | None = None) -> Indice:
    """Sub-chunkea las secciones hoja, embebe con prefijo de contexto y arma el índice.

    `documentos` traduce `doc_id` -> nombre del documento para el prefijo (si falta, se usa el `doc_id`).
    """
    documentos = documentos or {}
    subs, textos = [], []
    for sec in secciones:
        if not sec.es_hoja or not sec.texto_literal.strip():
            continue
        for sc in subchunkear(sec, documentos.get(sec.doc_id)):
            subs.append(sc)
            textos.append(texto_a_embeber(sec, sc, documentos.get(sec.doc_id)))
    if not subs:
        raise ValueError("No hay secciones con texto para indexar")
    log.info("Indexando %d secciones en %d sub-chunks", len(secciones), len(subs))
    return Indice(subs, embeber(textos, cliente, progreso))
