# 12 · Estructura del repositorio y configuración

```text
comparador-dbx/
├── CLAUDE.md
├── app.yaml                     # command: [uvicorn, backend.main:app, --workers, "1"]  (sin --host/--port: ver 14 #17)
├── requirements.txt             # versiones fijadas
├── config/defaults.env             # valores por defecto; el programa lo lee siempre (stages/<stage>.env lo pisa; .env.example es solo guía)
├── backend/
│   ├── main.py                  # FastAPI, monta /api y estáticos de frontend/dist
│   ├── config.py                # lee variables de entorno (pydantic-settings o os.environ)
│   ├── api/                     # routes_documents.py, routes_sections.py, routes_comparisons.py
│   ├── core/                    # session_store.py, jobs.py, errors.py, progreso.py (barras y logs de los procesos largos)
│   ├── ingest/                  # validation.py, pdf_metadata.py, classifier.py
│   ├── extraction/              # docling_extractor.py (repo), docling_worker.py, sectioner.py, patterns.py, lector.py (PDF → secciones)
│   ├── retrieval/               # chunker.py (repo), embeddings.py (repo), index.py, tabla.py (tabla de recuperación), exclusion.py (secciones no comparables), seleccion.py
│   ├── engine/                  # candidates.py, pairs.py, judge.py, citations.py, aggregate.py, conclusion.py
│   ├── output/                  # workpaper.py, annex.py, styles.py
│   ├── llm/                     # client.py (repo): Groq | Ollama | Docker Model Runner | Foundry por configuración
│   ├── prompts/                 # clasificador.md, juez.md, conclusion.md
│   └── models/schemas.py        # Documento, Seccion, SubChunk, Par, Veredicto, MetadatosLLM (Seccion sin cambios; SeccionExcluida vive en output/workpaper.py)
├── frontend/
│   ├── src/pages/               # Upload.tsx, Processing.tsx, Selector.tsx, Results.tsx
│   ├── src/components/          # DropZone.tsx, DocTable.tsx, DualTree.tsx, MarkBadge.tsx
│   └── dist/                    # build desplegado
├── qa/                         # trazabilidad RF/RNF ↔ pruebas y reportes de evaluación (agente qa-ia)
├── tablero/                    # tablero de avance (lo actualiza el product-owner)
├── documentos/                  # normas/ (NORMAS_DIR, sin versionar) y manuales/ (MANUALES_DIR, solo los MOCK en git): entrada de los notebooks
├── samples/                     # secciones .json + embeddings .npy precomputados (fase D2)
├── notebooks/                   # 00_modelos … 06_e2e: validación de cada hito en local (fase L)
├── scripts/precompute_samples.py
└── tests/                       # test_sectioner.py, test_aggregate.py, test_citations.py, test_excel.py
```
Los módulos marcados `(repo)` se toman del repositorio existente.

## Dependencias permitidas (backend)
`fastapi`, `uvicorn`, `python-multipart`, `pydantic>=2`, `pymupdf`, `docling` (2.134.0: la 2.55.1 de la v1 tenía 59 CVE, docs/14 #22), `faiss-cpu`, `numpy`, `pandas`, `openpyxl`, `openai` (un solo SDK para Groq, Ollama, Docker Model Runner y Foundry, que exponen API compatible con OpenAI), `python-dotenv`, `pytest`, `httpx`.
Solo para desarrollo: `jupyter` (notebooks de la fase L), `pytest-cov` (coverage) y `ragas` (evaluación de IA, en `requirements-eval.txt` y entorno propio: exige `openai<2` y la app usa `openai` 3.x; sin telemetría). `deepeval` se descartó porque `deepeval 4.2.8` exige `click<8.4` y choca con `transformers 5.x`.
Cualquier otra requiere justificación.

## Variables de configuración
Ver [`config/defaults.env`](../config/defaults.env).
