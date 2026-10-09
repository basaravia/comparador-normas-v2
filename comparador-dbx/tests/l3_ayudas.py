"""Ayudas de las pruebas unitarias de L3. Todo es entrada escrita a mano: textos y vectores.

`ClienteVectores` NO imita un modelo: entrega los vectores que la prueba le dicta, para ejercitar la
validación y la caché de `embeber` (código determinista nuestro). Los embeddings reales van en
`test_integracion_l3.py`. FAISS siempre es el real.
"""
from dataclasses import replace

import numpy as np

from backend.config import settings
from backend.models import Seccion, SubChunk
from backend.retrieval.index import Indice


def cfg(**cambios):
    """`settings` con los valores que la prueba fija (así no dependen de config/.env)."""
    return replace(settings, **cambios)


def seccion(id_="D:1", texto="Texto.", doc_id="D", ident="Artículo 1", ruta=("Título I",), es_hoja=True):
    return Seccion(id=id_, doc_id=doc_id, tipo_doc="normativa", nivel="articulo", identificador=ident,
                   ruta=list(ruta), texto_literal=texto, pagina_inicio=1, pagina_fin=1,
                   seccionado_incierto=False, estrategia="patron", es_hoja=es_hoja)


def indice_a_mano(vectores_por_seccion: dict[str, list[list[float]]]) -> Indice:
    """Un `Indice` real (IndexFlatIP) con los vectores dictados: {seccion_id: [vector de cada sub-chunk]}."""
    subs, vecs = [], []
    for sid, lista in vectores_por_seccion.items():
        for i, v in enumerate(lista):
            subs.append(SubChunk(id=f"{sid}#c{i}", seccion_id=sid, texto=f"{sid} sub {i}", orden=i))
            vecs.append(v)
    return Indice(subs, np.array(vecs, dtype=np.float32))


class ClienteVectores:
    """Misma interfaz que usa `embeber` (`s`, `emb()`, `embed()`); cuenta llamadas y textos recibidos."""

    def __init__(self, respuesta=None, modelo="modelo-a", dim=4):
        self.s = settings
        self.modelo, self.dim = modelo, dim
        self.respuesta = respuesta or self._un_vector_por_texto
        self.llamadas, self.textos = 0, []
        self._ids: dict[str, int] = {}

    def emb(self):
        return None, self.modelo

    def embed_multi(self, textos, progreso=None):
        """Una matriz por texto; `respuesta` puede dar una matriz (1 fila por texto) o una lista de matrices (ventanas)."""
        self.llamadas += 1
        self.textos.append(list(textos))
        r = self.respuesta(textos)
        if isinstance(r, np.ndarray) and r.ndim == 2:         # un vector por texto
            return [fila[None, :] for fila in r]
        return r

    def _un_vector_por_texto(self, textos):
        ids = [self._ids.setdefault(t, len(self._ids)) for t in textos]
        return np.array([np.eye(self.dim, dtype=np.float32)[i % self.dim] for i in ids])
