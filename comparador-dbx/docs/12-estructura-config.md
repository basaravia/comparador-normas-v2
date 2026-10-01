# 12 · Estructura del repositorio y configuración

```text
comparador-dbx/
├── CLAUDE.md
├── app.yaml                     # command: [uvicorn, backend.main:app, --workers, "1"]  (sin --host/--port: ver 14 #17)
├── requirements.txt             # versiones fijadas
├── config/.env.example
├── backend/
│   ├── main.py                  # FastAPI, monta /api y estáticos de frontend/dist
│   ├── config.py                # lee variables de entorno (pydantic-settings o os.environ)
│   ├── api/                     # routes_documents.py, routes_sections.py, routes_comparisons.py
│   ├── core/                    # session_store.py, jobs.py, errors.py
│   ├── ingest/                  # validation.py, pdf_metadata.py, classifier.py
│   ├── extraction/              # docling_extractor.py (repo), sectioner.py, patterns.py
│   ├── retrieval/               # chunker.py (repo), embeddings.py (repo), index.py
│   ├── engine/                  # candidates.py, pairs.py, judge.py, citations.py, aggregate.py, conclusion.py
│   ├── output/                  # workpaper.py, annex.py, styles.py
│   ├── llm/                     # client.py (repo): Groq | Ollama | Foundry por configuración
│   ├── prompts/                 # clasificador.md, juez.md, conclusion.md
│   └── models/schemas.py        # Documento, Seccion, SubChunk, Par, Veredicto, MetadatosLLM
├── frontend/
│   ├── src/pages/               # Upload.tsx, Processing.tsx, Selector.tsx, Results.tsx
│   ├── src/components/          # DropZone.tsx, DocTable.tsx, DualTree.tsx, MarkBadge.tsx
│   └── dist/                    # build desplegado
├── samples/                     # secciones .json + embeddings .npy precomputados
├── notebooks/                   # 00_modelos … 06_e2e: validación de cada hito en local (fase L)
├── scripts/precompute_samples.py
└── tests/                       # test_sectioner.py, test_aggregate.py, test_citations.py, test_excel.py
```
Los módulos marcados `(repo)` se toman del repositorio existente.

## Dependencias permitidas (backend)
`fastapi`, `uvicorn`, `python-multipart`, `pydantic>=2`, `pymupdf`, `docling` (versión del repo: 2.55.1), `faiss-cpu`, `numpy`, `pandas`, `openpyxl`, `openai` (un solo SDK para Groq, Ollama y Foundry, que exponen API compatible con OpenAI), `python-dotenv`, `pytest`, `httpx`.
Solo para desarrollo: `jupyter` (notebooks de la fase L).
Cualquier otra requiere justificación.

## Variables de configuración
Ver [`config/.env.example`](../config/.env.example).
