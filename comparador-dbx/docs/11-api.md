# 11 · API del backend

Prefijo `/api`. FastAPI sirve además `frontend/dist` en `/`.

| Método y ruta | Descripción |
|---|---|
| `POST /api/documents` | multipart con N archivos. Valida, lee metadatos nativos, llama al clasificador. Devuelve filas con sugerencias |
| `GET /api/session` | Estado de la sesión: `documentos[]`, `comparacion_id`, `trabajo_activo` (`null` o `{id, tipo: procesamiento\|comparacion, comparacion_id}`; `id` es siempre el `job_id` de `GET /api/jobs/{id}` y `comparacion_id` solo viene en comparaciones), `usuario` (correo con la bandera de identidad; si no, «Sesión local»), `retencion_horas`, `max_documentos`, `iniciada_ts` (cambia si la sesión se recrea) y `sesion_nueva` (`true` solo si llegó una cookie desconocida y se abrió una sesión nueva). `Cache-Control: no-store`. Es el único endpoint que abre una sesión nueva en modo cookie |
| `PATCH /api/documents/{id}` | Actualiza tipo y metadatos editados por el auditor. Un documento ya procesado no cambia de tipo (`ERR-DOC-003`) |
| `DELETE /api/documents/{id}` | Quita un documento de la sesión propia (`id` con forma `D<número>`; si no existe o es de otra sesión, `404 ERR-DOC-001`). Con cualquier trabajo activo o el documento en ingesta → `409 ERR-DOC-006`. Borra su carpeta y miniaturas, invalida los índices y descarta la comparación vigente (y su Excel). Devuelve la sesión actualizada |
| `POST /api/documents/process` | Body: `doc_ids`. Encola extracción + seccionado + indexación. Devuelve `job_id`. Acepta documentos en `error` cuyo PDF sigue en disco (reintento). Con otro trabajo activo → `409 ERR-JOB-002` |
| `GET /api/jobs/{job_id}` | `{estado (en_cola/en_curso/listo/error/cancelado), etapa, doc_actual, progreso 0-1, mensaje, errores[]}` (errores en lenguaje de negocio + código) y, aditivos, el progreso en vivo (RF-20): `ahora_ts, inicio_ts, ultimo_evento_ts, cancelable, por_documento{doc_id:{etapa, paginas_hechas, paginas_total, lote[ini,fin]}}, indice{doc_id:{secciones, articulos, excluidas, por_revisar}}, indexacion_hechos/total, fase, pares_total, pares_hechos, pares_en_curso[], ultimos_veredictos[≤20], conteo_cobertura, a_revision, espera_limite{activa, hasta_ts, intento, max}`. Todo en memoria |
| `POST /api/jobs/{job_id}/cancel` | RF-21. Procesamiento: termina la lectura del PDF en curso (lo ya leído se conserva). Comparación: no se lanzan más pares; el resultado parcial se descarta |
| `GET /api/documents/{id}/pages/{n}/thumb` | PNG pequeño de la página `n` del PDF de la sesión, renderizado al pedirlo (no se guarda). Para la tira de páginas. Solo existe mientras dura el procesamiento: sin PDF → `404 ERR-DOC-001` |
| `GET /api/sections/tree?tipo=normativa\|manual_control` | Árbol por documento, sin texto completo (id, identificador, título, hijos, preview 120 chars, banderas) |
| `GET /api/sections/{id}` | Texto literal, páginas, banderas |
| `POST /api/comparisons` | Body: `articulo_ids[]`, `seccion_ids[]`. Devuelve `job_id`. Con un procesamiento o comparación activos → `409 ERR-JOB-002` |
| `GET /api/comparisons/{id}` | Resultados agregados, vistas vía 1 y vía 2, conteos, borrador de conclusión |
| `PUT /api/comparisons/{id}/conclusion` | Guarda la conclusión editada |
| `GET /api/comparisons/{id}/excel` | Genera y descarga el .xlsx |
| `POST /api/samples/load` | Carga los ejemplos precargados en la sesión. Respeta `MAX_DOCS_SESION` y, si ya están cargados, devuelve la sesión tal cual (no duplica) |
| `DELETE /api/session` | Reinicia la sesión (borra documentos, índices, comparaciones y carpeta) |
| `GET /api/settings` | Parámetros ajustables de la sesión: clave, etiqueta, ayuda, valor, defecto, mínimo, máximo, paso, tipo y si es avanzado (lista blanca en `config/ajustes.json`) |
| `PUT /api/settings` | Body `{valores: {clave: número}}`. Valida lista blanca y rangos (`CITATION_SHOW_MIN` ≤ `CITATION_FUZZY_MIN`; `MAX_PARES` nunca por encima del defecto del stage), descarta claves desconocidas y guarda en la sesión |
| `DELETE /api/settings` | Restablece los defaults de la sesión |
| `GET /api/health` | Estado + ping al gateway |

## Sesión y jobs
- **Identidad.** Modo cookie (por defecto, local): cookie `session_id` aleatoria, `HttpOnly`, `SameSite=Lax`, con `max_age` igual a la retención. Modo identidad (`TRUST_PROXY_IDENTITY=true`, solo `app.yaml`): no se lee ni se emite la cookie; la sesión se busca por el SHA-256 del correo de `x-forwarded-email` (`strip().lower()`). Lectura estricta: exactamente un valor, ≤ 254 caracteres, forma `a@b` sin espacios ni caracteres de control; si no, `401 ERR-SES-003` sin eco del valor. Con la bandera apagada esa cabecera no se lee nunca; `x-forwarded-access-token` no se lee en ningún modo. Con la bandera encendida y sin `DATABRICKS_APP_NAME` en el entorno la app no arranca. El correo y su hash no van a logs, errores ni nombres de carpeta; `Sesion.id` y la carpeta (`mkdtemp`) son aleatorios.
- **Sesión desconocida (modo cookie).** `GET /api/session` con cookie ausente o desconocida abre una sesión nueva con id propio (el valor recibido no se adopta) y responde `sesion_nueva`; el resto de endpoints responde `410 ERR-SES-001`.
- **Retención.** Estado en memoria, expira por inactividad (`SESSION_TTL_HOURS=48`); nunca se borra una sesión con trabajo activo (job en cola o en curso, comparación o ingesta). Al terminar un trabajo se renueva el último uso.
- **Servidor lleno.** Con `MAX_SESIONES` vivas, una sesión nueva expulsa a la más inactiva solo si lleva sin uso al menos `SESION_EXPULSABLE_MIN` minutos y no tiene trabajo activo; si ninguna cumple → `503 ERR-SES-002`.
- **Limpieza al arrancar.** Con `LIMPIAR_TMP_AL_ARRANCAR=true`, en el evento de arranque (nunca al importar), se borran las carpetas `comparador_*` de `tempfile.gettempdir()` que sean directorios reales (no enlaces) del mismo usuario del proceso: restos de un reinicio anterior.
- **PDF y miniaturas.** El PDF se borra cuando el documento queda `listo` al terminar el job; se conserva si falla o se cancela. La miniatura se renderiza del PDF mientras exista; luego `ERR-DOC-001`.
- **Un trabajo por sesión.** Procesamiento: `ThreadPoolExecutor(max_workers=1)` (CPU). Comparación: hilo del pool de comparaciones. No hay dos trabajos activos en la misma sesión (`409 ERR-JOB-002`).
- **Protección de origen.** Toda solicitud que no sea GET/HEAD/OPTIONS bajo `/api` con `Sec-Fetch-Site` distinto de `same-origin` o `none` recibe `403 ERR-SEG-001`; sin la cabecera se permite.
- El frontend hace polling a `/api/jobs/{id}` cada 1,5 s.
