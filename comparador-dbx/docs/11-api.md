# 11 · API del backend

Prefijo `/api`. FastAPI sirve además `frontend/dist` en `/`.

| Método y ruta | Descripción |
|---|---|
| `POST /api/documents` | multipart con N archivos. Valida, lee metadatos nativos, llama al clasificador. Devuelve filas con sugerencias |
| `PATCH /api/documents/{id}` | Actualiza tipo y metadatos editados por el auditor |
| `POST /api/documents/process` | Body: `doc_ids`. Encola extracción + seccionado + indexación. Devuelve `job_id` |
| `GET /api/jobs/{job_id}` | `{estado, etapa, doc_actual, progreso 0-1, mensaje, errores[]}` (errores en lenguaje de negocio + código) |
| `GET /api/sections/tree?tipo=normativa\|manual_control` | Árbol por documento, sin texto completo (id, identificador, título, hijos, preview 120 chars, banderas) |
| `GET /api/sections/{id}` | Texto literal, páginas, banderas |
| `POST /api/comparisons` | Body: `articulo_ids[]`, `seccion_ids[]`. Devuelve `job_id` |
| `GET /api/comparisons/{id}` | Resultados agregados, vistas vía 1 y vía 2, conteos, borrador de conclusión |
| `PUT /api/comparisons/{id}/conclusion` | Guarda la conclusión editada |
| `GET /api/comparisons/{id}/excel` | Genera y descarga el .xlsx |
| `POST /api/samples/load` | Carga los ejemplos precargados en la sesión |
| `DELETE /api/session` | Reinicia la sesión |
| `GET /api/health` | Estado + ping al gateway |

## Sesión y jobs
- Cookie `session_id`; estado en `SESSIONS[session_id]` con expiración por inactividad (`SESSION_TTL_HOURS=4`).
- Jobs de extracción: `ThreadPoolExecutor(max_workers=1)` (CPU). Jobs de comparación: tareas `asyncio` (I/O al gateway).
- El frontend hace polling a `/api/jobs/{id}` cada 1,5 s.
- Si el `session_id` no existe (contenedor reiniciado) → `410 Gone` con mensaje "sesión perdida".
