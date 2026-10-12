"""Reranker cruzado opcional (docs/08 §Reranking): puntúa pares (artículo, sección) con el texto literal completo de ambos.

Solo ordena y descarta candidatos; no genera ni reescribe texto. Dos familias, elegidas por el nombre de `RERANK_MODEL`:
- `Qwen3-Reranker-*`: modelo causal; puntaje = P("yes") frente a "no" en el último token (formato de la ficha del modelo).
- cualquier otro (p. ej. `BAAI/bge-reranker-v2-m3`): clasificador de secuencias; puntaje = sigmoide del logit.
Los pesos salen de la caché local de Hugging Face; nunca se envía texto a un servicio externo.
"""
import logging
import time
from collections.abc import Callable

from backend.config import Settings, settings
from backend.core.errors import ComparadorError

log = logging.getLogger(__name__)

INSTRUCCION = ("Given a regulatory article from a financial norm, judge whether the bank control manual section "
               "implements or covers the obligation of the article")
_PREFIJO = ("<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. "
            'Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n')
_SUFIJO = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


class RerankerError(ComparadorError):
    """Reranker mal configurado o par que no cabe en su contexto. Es de infraestructura: la corrida **aborta**."""
    codigo = "ERR-IDX-002"
    mensaje_negocio = "No pudimos ordenar las coincidencias. Intenta de nuevo o consulta con soporte."


class Reranker:
    def __init__(self, s: Settings = settings):
        if not s.RERANK_MODEL:
            raise RerankerError("RERANK_MODEL está vacío: define el modelo del reranker en la configuración.")
        import torch
        from transformers import AutoModelForCausalLM, AutoModelForSequenceClassification, AutoTokenizer
        self.nombre, self.lote, self._torch = s.RERANK_MODEL, s.RERANK_BATCH, torch
        self.qwen = "qwen3-reranker" in s.RERANK_MODEL.lower()
        self.dispositivo = s.RERANK_DEVICE if s.RERANK_DEVICE != "auto" else (
            "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
        t0 = time.perf_counter()
        self.tok = AutoTokenizer.from_pretrained(s.RERANK_MODEL, padding_side="left")
        clase = AutoModelForCausalLM if self.qwen else AutoModelForSequenceClassification
        self.modelo = clase.from_pretrained(s.RERANK_MODEL, dtype=torch.float32).eval().to(self.dispositivo)
        self.max_pos = int(getattr(self.modelo.config, "max_position_embeddings", 8192))
        if self.qwen:
            self.si, self.no = self.tok.convert_tokens_to_ids("yes"), self.tok.convert_tokens_to_ids("no")
        log.info("Reranker %s cargado en %.0f s en %s (contexto %d tokens)", self.nombre, time.perf_counter() - t0, self.dispositivo, self.max_pos)

    def _entrada(self, consulta: str, documento: str) -> str | tuple[str, str]:
        if self.qwen:
            return f"{_PREFIJO}<Instruct>: {INSTRUCCION}\n<Query>: {consulta}\n<Document>: {documento}{_SUFIJO}"
        return consulta, documento

    def puntuar(self, pares: list[tuple[str, str]], progreso: Callable[[int, int], None] | None = None) -> list[float]:
        """Un puntaje (0-1) por par `(consulta, documento)`, en el mismo orden. No recorta: si un par no cabe en el contexto del modelo, falla."""
        entradas = [self._entrada(q, d) for q, d in pares]
        largo = [len(e) if isinstance(e, str) else len(e[0]) + len(e[1]) for e in entradas]
        orden = sorted(range(len(entradas)), key=lambda i: largo[i])       # lotes de largo parecido: menos relleno
        out = [0.0] * len(entradas)
        for a in range(0, len(orden), self.lote):
            idx = orden[a:a + self.lote]
            lote = [entradas[i] for i in idx]
            enc = self.tok(lote if self.qwen else [x[0] for x in lote], None if self.qwen else [x[1] for x in lote],
                           padding=True, return_tensors="pt")
            if enc["input_ids"].shape[1] > self.max_pos:
                raise RerankerError(f"Un par ocupa {enc['input_ids'].shape[1]} tokens y {self.nombre} admite {self.max_pos}: no se recorta, usa otro reranker.")
            with self._torch.no_grad():
                logits = self.modelo(**enc.to(self.dispositivo)).logits.cpu()
            if self.qwen:
                p = self._torch.softmax(logits[:, -1, :][:, [self.no, self.si]], dim=1)[:, 1]
            else:
                p = self._torch.sigmoid(logits[:, 0])
            for i, v in zip(idx, p.tolist()):
                out[i] = v
            if progreso:
                progreso(min(a + self.lote, len(orden)), len(orden))
        return out
