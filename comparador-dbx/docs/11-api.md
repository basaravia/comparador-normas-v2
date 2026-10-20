# 11 · API del backend

Prefijo `/api`. FastAPI sirve además `frontend/dist` en `/`.

| Método y ruta | Descripción |
|---|---|
| `POST /api/documents` | multipart con N archivos. Valida, lee metadatos nativos, llama al clasificador. Devuelve filas con sugerencias |
| `PATCH /api/documents/{id}` | Actualiza tipo y metadatos editados por el auditor |
| `POST /api/documents/process` | Body: `doc_ids`. Encola extracción + seccionado + indexación. Devuelve `job_id` |
| `GET /api/jobs/{job_id}` | `{estado (en_cola/en_curso/listo/error/cancelado), etapa, doc_actual, progreso 0-1, mensaje, errores[]}` (errores en lenguaje de negocio + código) y, aditivos, el progreso en vivo (RF-20): `ahora_ts, inicio_ts, ultimo_evento_ts, cancelable, por_documento{doc_id:{etapa, paginas_hechas, paginas_total, lote[ini,fin]}}, indice{doc_id:{secciones, articulos, excluidas, por_revisar}}, indexacion_hechos/total, fase, pares_total, pares_hechos, pares_en_curso[], ultimos_veredictos[≤20], conteo_cobertura, a_revision, espera_limite{activa, hasta_ts, intento, max}`. Todo en memoria |
| `POST /api/jobs/{job_id}/cancel` | RF-21. Procesamiento: termina la lectura del PDF en curso (lo ya leído se conserva). Comparación: no se lanzan más pares; el resultado parcial se descarta |
| `GET /api/documents/{id}/pages/{n}/thumb` | PNG pequeño de la página `n` del PDF de la sesión, renderizado al pedirlo (no se guarda). Para la tira de páginas |
| `GET /api/sections/tree?tipo=normativa\|manual_control` | Árbol por documento, sin texto completo (id, identificador, título, hijos, preview 120 chars, banderas) |
| `GET /api/sections/{id}` | Texto literal, páginas, banderas |
| `POST /api/comparisons` | Body: `articulo_ids[]`, `seccion_ids[]`. Devuelve `job_id` |
| `GET /api/comparisons/{id}` | Resultados agregados, vistas vía 1 y vía 2, conteos, borrador de conclusión |
| `PUT /api/comparisons/{id}/conclusion` | Guarda la conclusión editada |
| `GET /api/comparisons/{id}/excel` | Genera y descarga el .xlsx |
| `POST /api/samples/load` | Carga los ejemplos precargados en la sesión |
| `DELETE /api/session` | Reinicia la sesión |
| `GET /api/settings` | Parámetros ajustables de la sesión: clave, etiqueta, ayuda, valor, defecto, mínimo, máximo, paso, tipo y si es avanzado (lista blanca en `config/ajustes.json`) |
| `PUT /api/settings` | Body `{valores: {clave: número}}`. Valida lista blanca y rangos (`CITATION_SHOW_MIN` ≤ `CITATION_FUZZY_MIN`; `MAX_PARES` nunca por encima del defecto del stage), descarta claves desconocidas y guarda en la sesión |
| `DELETE /api/settings` | Restablece los defaults de la sesión |
| `GET /api/health` | Estado + ping al gateway |

## Sesión y jobs
- Cookie `session_id`; estado en `SESSIONS[session_id]` con expiración por inactividad (`SESSION_TTL_HOURS=4`).
- Jobs de extracción: `ThreadPoolExecutor(max_workers=1)` (CPU). Jobs de comparación: tareas `asyncio` (I/O al gateway).
- El frontend hace polling a `/api/jobs/{id}` cada 1,5 s.
- Si el `session_id` no existe (contenedor reiniciado) → `410 Gone` con mensaje "sesión perdida".
