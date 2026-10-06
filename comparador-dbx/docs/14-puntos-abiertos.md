# 14 · Puntos abiertos para calibrar

Estado al 1 oct 2026. **Decidido** = ya no se discute; **Calibrar** = valor inicial que se mide y ajusta.

## Decisiones de producto

| # | Tema | Estado | Decisión |
|---|---|---|---|
| 3 | Marca P | Decidido | Se respetan las marcas del banco tal como están en [09](09-motor-doble-via.md) §5: **P** = artículo `informativo` (definiciones, objeto, ámbito) |
| 4 | Vía 2 en el papel | Decidido | Bloque **al final del anexo** (Hoja 2), sin tercera hoja |
| 5 | Respaldo múltiple | Decidido | **1 sección** de manual como respaldo por artículo, también para **L** |
| 6 | Literales a), b) | Decidido | **Dentro del artículo**; un literal no cubierto aparece en `elementos_faltantes` |
| 7 | Encabezado | Decidido | Nombre de la revisión y corte quedan **en blanco** en el Excel; el auditor los llena a mano |
| 11 | Citas no verificadas | Decidido | Si el ratio está entre `CITATION_SHOW_MIN` (0,75) y `CITATION_FUZZY_MIN` (0,90): se muestra el fragmento real más cercano **con aviso** y `requiere_revision=True`. Por debajo de 0,75: celda vacía con aviso |
| 12 | Colores | Decidido | **Verde y blanco** como base, definidos en configuración. Se reemplazan con el brand kit del banco cuando llegue |

## Entornos y proveedores

| # | Tema | Estado | Decisión |
|---|---|---|---|
| 13 | Stages | Decidido | **dev**: MacBook con Docker Desktop, LLM y embeddings en Docker Model Runner · **sandbox**: Raspberry Pi, Groq + Ollama `bge-m3`, con notebooks · **mvp**: cluster Databricks con Azure AI Foundry (pruebas en Databricks Free y demo en Azure de pago). Cada stage es un archivo `config/stages/<stage>.env` y se elige con `STAGE` |
| 14 | Modelos | Decidido | dev: **Docker Model Runner** (`ai/qwen3.5:9B-UD-Q4_K_XL` + `ai/granite-embedding-multilingual`). sandbox: LLM **Groq** (como en la v1) + embeddings **Ollama `bge-m3`**. mvp: **Azure AI Foundry directo** (endpoint + token en secret, como en la v1), no el AI Gateway. Se cambia solo por configuración |
| 15 | Documentos de prueba | Decidido | Manuales MOCK de la v1 y normativas cortas de `Normativa2026/`. Los documentos reales solo en la demo |
| 16 | Tamaño del paquete | Restricción | Databricks Apps rechaza paquetes de **más de 10 MB** (visto en la v1). Los artefactos de Docling (~1,5 GB) se descargan al primer uso; no van en `models_cache/` |
| 17 | `app.yaml` | Restricción | El `command` **no pasa por shell**: nada de `--port $PORT`. Uvicorn toma `UVICORN_HOST`/`UVICORN_PORT` del entorno (visto en la v1) |
| 18 | Prompt injection residual | Decidido | En L4, chequeo simple en Python: si la sección del manual contiene frases dirigidas al evaluador ("ignora las instrucciones", "responde total", "cumple totalmente"…), la fila queda `requiere_revision` y aparece en el anexo. Los prompts ya delimitan el texto del documento como dato (auditoría `appsec`, 2 oct 2026) |
| 19 | QA | Decidido | Agente `qa-ia` (QA de IA para auditoría financiera): valida los **RF/RNF de docs/04** y los criterios de docs/13, sin historias de usuario nuevas · coverage **≥ 80 %** de la lógica determinista al cerrar cada hito · **DeepEval** instalado solo en desarrollo, sin telemetría · Databricks CLI: lectura libre y ejecución de pruebas en el workspace Free solo con aprobación del usuario |
| 20 | Ramas y versiones | Decidido | GitHub flow: ramas cortas desde `main`, una por tarea, con prefijo de Conventional Commits y worktree propio (también para `qa-ia`), que se borran al integrarse. Tags SemVer 0.x por hito en `main` (`v0.1.0` = L0 … `v0.7.0` = L6, parches `v0.x.y`, `v1.0.0` = demo). La rama larga `feat/fase-l-local` se integró en `main` y se retira |

## Calibración empírica

| # | Tema | Valor inicial | Cómo se mide |
|---|---|---|---|
| 1 | Umbral de similitud | 0,30 | Depende del modelo de embeddings: se calibra por separado para `bge-m3` (dev) y `text-embedding-3-large` (demo) con los MOCK y la Hoja 2 |
| 2 | Tamaño de sub-chunk | ~500 tokens, 15 % solapamiento | Recall en candidatos con los MOCK |
| 8 | Detección de escaneo | 0,6 de páginas con texto | Con las normativas de `Normativa2026/` |
| 9 | Concurrencia | 6 | Se ajusta al **límite de tasa del plan gratuito** (Groq / Databricks Free); en la demo, al del deployment de Foundry |
| 10 | Rendimiento Docling | — | Tiempo y RAM con 100 páginas, primero en la Raspberry y luego en Databricks. Referencia de la v1: pico de 4,2 GB |
