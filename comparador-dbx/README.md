# Paquete de especificación — Comparador Normativo de Doble Vía (MVP)

Este paquete contiene la especificación para que Claude Code implemente el MVP.

## Cómo usarlo
1. Copia el contenido de este paquete en la raíz del repositorio de la aplicación (o en un repo nuevo que reutilice módulos del repo existente).
2. `CLAUDE.md` queda en la raíz: Claude Code lo lee automáticamente al iniciar sesión.
3. Pide a Claude Code: *"Lee CLAUDE.md y docs/00-INDEX.md, localiza en el repo los módulos reutilizables y ejecuta el Hito 0 de docs/13-plan-hitos.md."*

## Contenido
| Ruta | Propósito |
|---|---|
| `CLAUDE.md` | Reglas de trabajo para el agente (se carga en cada sesión) |
| `docs/` | Especificación completa por capítulos, diagramas en Mermaid |
| `backend/prompts/` | Prompts del clasificador, el juez y la conclusión, listos para cargar |
| `config/defaults.env` | Variables de configuración con valores iniciales |

El PDF "Manual técnico de implementación" es la versión para lectura humana del mismo contenido. **La fuente de verdad es este paquete Markdown.**

## Módulos reutilizados del repo de referencia
Origen: `../../comparador-normativas-ec-v1` (clon de `basaravia/comparador-normativas-ec`), rama `feature/v6-react-fastapi`, carpeta `backend/src/`.

| Módulo nuevo | Archivo de origen (v6) | Qué se cambió |
|---|---|---|
| `backend/config.py` | `settings.py` | Sin secret scope ni `databricks-sdk`; valores iniciales solo en `config/defaults.env`, sin defaults en código; carga de prompts desde archivo |
| `backend/core/errors.py` | `errors.py` | Sin ramas de LangChain/Vertex; código `ERR-*` y mensaje de negocio por error (`docs/05`) |
| `backend/extraction/docling_extractor.py`, `docling_worker.py` | `providers.py` (`_build_pdf_pipeline_options`, `build_document_converter`) | Solo las opciones de Docling (`do_ocr`, tablas, dispositivo). Nuevo: subproceso con timeout, cola de 1 worker, caché SHA-256, tandas de páginas y mapeo a los tipos de docs/07 |
| `backend/extraction/sectioner.py`, `patterns.py` | — (módulos nuevos, docs/07; la v6 no tiene seccionado equivalente) | Cascada patrones → tipografía (PyMuPDF) → longitud, con el catálogo de regex de docs/07 reescrito sin costo cuadrático |
| `backend/ingest/*` | — (módulos nuevos, docs/06) | La v6 no tiene ingesta equivalente: validación, metadatos y clasificador se escribieron según la spec |
| `backend/llm/client.py` | `providers.py` (`ProviderSpec.resuelto`, `_cliente_azure`, `_validar_azure`) | Sin LangChain: solo SDK `openai` (Groq, Ollama, Docker Model Runner, `AzureOpenAI`); JSON validado con Pydantic y 1 reintento |
| `backend/retrieval/chunker.py` | `chunking.py` (`chunk_articulo`, `_segmentar`, `_empaquetar`, `estimar_tokens`) | Sin pandas ni LangChain: opera sobre `Seccion` y devuelve `SubChunk`. Conserva el corte por párrafos, numerales y literales, el solape y la estimación de tokens por palabras (1,35 tokens/palabra). Presupuesto y solape salen de `settings`; el prefijo de contexto va en `texto_a_embeber`, no en el texto literal |
| `backend/retrieval/index.py` | `search_engine.py` (solo la idea: `IndexFlatIP` sobre vectores L2-normalizados, un sub-chunk por fila que apunta a su padre) | Sin pandas, sin guardar a disco, sin reranker ni búsqueda léxica. Dos `IndexFlatIP` de FAISS, caché de embeddings por SHA-256 y subíndice filtrado por selección (docs/08); embeddings por `ModelClient.embed` |
| `backend/engine/candidatos.py`, `pares.py` | — (módulos nuevos, docs/09 §1-§2) | La v6 no tiene doble vía; se escribieron según la spec |
