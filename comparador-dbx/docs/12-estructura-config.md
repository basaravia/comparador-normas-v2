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
│   ├── llm/                     # client.py (repo): Groq | Ollama | Docker Model Runner | Foundry | Databricks | OpenRouter (solo respaldo del LLM) por configuración
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
`fastapi`, `uvicorn`, `python-multipart`, `pydantic>=2`, `pymupdf`, `docling` (2.145.0: la 2.55.1 de la v1 tenía 59 CVE, docs/14 #22; la 2.145 es la primera que admite `pillow>=13`), `faiss-cpu`, `numpy`, `pandas`, `openpyxl`, `openai` (un solo SDK para Groq, Ollama, Docker Model Runner, Foundry y los modelos de Databricks, que exponen API compatible con OpenAI; `httpx` ya viene con él), `python-dotenv`, `pytest`, `httpx`.
Solo para desarrollo: `jupyter` (notebooks de la fase L), `pytest-cov` (coverage) y `ragas` (evaluación de IA, en `requirements-eval.txt` y entorno propio: exige `openai<2` y la app usa `openai` 3.x; sin telemetría). `deepeval` se descartó porque `deepeval 4.2.8` exige `click<8.4` y choca con `transformers 5.x`.
Cualquier otra requiere justificación.

## Dependencias permitidas (frontend)
Todas con versión exacta en `frontend/package.json`.
- **Producción:** `react` y `react-dom` (18.3.1).
- **Compilación y tipos:** `vite`, `@vitejs/plugin-react`, `typescript`, `@types/react`, `@types/react-dom`.
- **Pruebas de componentes** (decisión del usuario, 25 nov 2026, D-49; solo `devDependencies`): `vitest`, `@testing-library/react`, `@testing-library/dom` y `jsdom`. Se usa jsdom 29 y no la 31 porque la 31 exige Node ≥ 24.15. La lógica pura sigue con `node --test`, sin dependencias.
- **Herramienta externa, no dependencia:** `playwright-core` solo lo usa `scripts/prueba_navegador.mjs` (prueba de navegador real con Brave o Chromium, perfil limpio); no está en `package.json` ni en el bundle: se toma el que ya tenga la máquina (`NODE_PATH`, p. ej. el de `npx playwright`).
- Cualquier otra requiere justificación en el commit (CLAUDE.md regla 2) y pasar `npm audit`.

## Variables de configuración
Ver [`config/defaults.env`](../config/defaults.env).

### Sesión e identidad (docs/14 #37)
| Variable | defaults.env | `app.yaml` (mvp) | Nota |
|---|---|---|---|
| `SESSION_TTL_HOURS` | 48 | — | retención por inactividad |
| `MAX_PAGES_SESION` | 500 `[CALIBRAR]` | — | páginas sumadas de los documentos de una sesión (los fallidos no cuentan); sin tope, una sesión con PDF de 250 páginas podía ocupar la cola de Docling (1 worker) hasta ~6,7 h (appsec S-18). El documento que no cabe queda como fallido con `ERR-ING-005` |
| `SESION_EXPULSABLE_MIN` | 120 `[CALIBRAR]` | — | inactividad mínima para expulsar una sesión cuando `MAX_SESIONES` está lleno |
| `TRUST_PROXY_IDENTITY` | `false` | `false` (pasa a `true` solo tras la comprobación S-21 de [16](16-despliegue.md)) | liga la sesión al correo de `x-forwarded-email`; exige `DATABRICKS_APP_NAME` (la inyecta Databricks Apps); ver [16](16-despliegue.md) |
| `LIMPIAR_TMP_AL_ARRANCAR` | `false` | `true` | borra al iniciar las carpetas `comparador_*` huérfanas de `/tmp` |

`app.yaml` es el mismo para todos los stages (hoy `STAGE=mvp`, Foundry); en dev y sandbox valen los de `defaults.env`. `app.free.yaml` es la variante para Databricks Free (modelos del workspace, sin Foundry): ver [16](16-despliegue.md).

### Comparación en curso (docs/14 #39)
| Variable | Valor inicial | Nota |
|---|---|---|
| `ESTIMADO_DESDE_PARES` | 3 `[CALIBRAR]` | pares resueltos desde los que se muestra el estimado de tiempo restante; el servidor lo entrega en `JobOut.estimado_desde_pares` ([11](11-api.md)) |
| `PARES_POR_PAGINA` | 50 `[CALIBRAR]` | pares resueltos que se pintan a la vez («Mostrar 50 más»); se entrega en `JobOut.pares_por_pagina` |

Van en `config/defaults.env` y no entran al panel Ajustes (RF-19).

### Colores de las marcas del papel de trabajo (docs/10, docs/14 #12)
| Variable | Valor inicial | Nota |
|---|---|---|
| `COLOR_MARCA_A`, `_L`, `_R`, `_X`, `_P` | `C6EFCE`, `FFEB9C`, `F8CBAD`, `E7E6E6`, `DDEBF7` `[CALIBRAR]` | relleno suave de cada marca en el Excel (verde, ámbar, rojo, gris, azul). 6 dígitos hexadecimales **sin `#`**; un valor inválido detiene el arranque con un mensaje que nombra la variable. Junto con `COLOR_PRIMARIO` y `COLOR_FONDO` se sustituyen por los del brand kit del banco |

### Marca e identidad visual (docs/14 #40)
Todas opcionales; vacías = cabecera «⚖ Comparador Normativo» sin logos. Los logos los copia el servicio de destino; **no se versionan** (`marca/LEEME.md` explica las medidas).

| Variable | Valor inicial | Nota |
|---|---|---|
| `NOMBRE_PRODUCTO` | `Comparador Normativo` | texto de la cabecera (≤ 80 caracteres, sin caracteres de control) |
| `TEXTO_ALTERNATIVO` | vacío | nombre de la organización para el alt del logo («Logo de …»; ≤ 120 caracteres); vacío = «Logo» |
| `LOGO_DIR` | `marca` | carpeta de los logos; relativa a `comparador-dbx/` (`carpeta_marca()` en `config.py`) |
| `LOGO_ORG_URL`, `LOGO_PRODUCTO_URL`, `LOGO_PIE_URL` | vacío | ruta `/marca/<archivo>.svg` o `.png` (solo letras, números, `.`, `_`, `-`; ≤ 64). Cualquier otro valor (https, `data:`, `..`) se descarta con un aviso en el log que nombra la variable y no el valor |

Los colores, radios, espaciado y tipografía **no** son variables de entorno: viven en el bloque `:root` de `frontend/src/estilos.css` (`docs/ux/identidad-visual-v1.md` §6).
