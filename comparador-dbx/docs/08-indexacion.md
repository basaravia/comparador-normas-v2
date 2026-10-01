# 08 · Indexación semántica

> La recuperación semántica es la pieza más crítica: una sección relevante que no entra en los candidatos **no existe para el juez**. Priorizar recall.

- **Sub-chunking** por sección con el chunker del repo: ~500 tokens, solapamiento ~15 % `[CALIBRAR]`. Una sección corta es un único sub-chunk. Esto normaliza longitudes (un artículo de 3 líneas vs una sección de 2 páginas) y evita que una obligación puntual se diluya.
- **Prefijo de contexto** en el texto a embeber (no altera el texto literal guardado):
  `"{documento} > {ruta} > {identificador}: {texto}"`
- **Embeddings** con `text-embedding-3-large` vía gateway, por lotes (`EMB_BATCH=64` `[CALIBRAR]`), normalizados L2.
- **Dos índices FAISS `IndexFlatIP`** por sesión: normativa y manual, cada uno con arreglo paralelo `subchunk_idx → seccion_id`.
- **Filtrado por selección:** antes de consultar, construir un subíndice temporal solo con sub-chunks de las secciones seleccionadas del lado opuesto (con cientos de vectores es instantáneo).
- **Caché** de embeddings en memoria por hash del texto. Los ejemplos precargados traen `.npy`.

```python
class SubChunk(BaseModel):
    id: str
    seccion_id: str
    texto: str
    orden: int
    # vector se guarda aparte en numpy (float32, normalizado)
```
