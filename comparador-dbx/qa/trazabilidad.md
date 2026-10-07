# Matriz de trazabilidad (QA)

Requisitos de `docs/04-requerimientos.md` y criterios de aceptación de `docs/13-plan-hitos.md` frente a las pruebas que los verifican. La escribe el agente `qa-ia`; la lee el `product-owner`. No hay historias de usuario (decisión del usuario).

Estados: `verificado` (hay prueba y pasa) · `falla` (hay prueba y no pasa) · `parcial` (cubre solo una parte; se dice cuál) · `sin prueba` (hay código pero no se prueba) · `pendiente` (su hito aún no llega).

Pasada base sobre L0 y L1 (cerrados antes de existir la regla de QA) y re-verificación tras la corrección de QA-01 y del PDF truncado (rama `fix/neutralizar-marcas-pdf-truncado`). Las rutas de pruebas son relativas a `comparador-dbx/`.

## 1. Requisitos

| ID | Requisito (resumen) | Prioridad | Hito | Pruebas | Estado |
|---|---|---|---|---|---|
| RF-01 | Carga múltiple de PDFs en una zona de arrastre | DEBE | D0 / U0 | — | pendiente |
| RF-02 | Tabla por archivo: nombre, tipo, metadatos editables, estado | DEBE | D0 / U0 | — (la fila que devuelve `ingerir` se prueba en RF-03) | pendiente |
| RF-03 | Preselección de tipo y metadatos desde nombre, 2 primeras páginas y metadatos nativos | DEBE | L1 | `tests/test_classifier.py::test_tipo_sugerido_*`, `::test_desconocido_nunca_se_preselecciona`, `::test_sin_respuesta_queda_desconocido_y_sin_preseleccion`, `::test_fecha_invalida_queda_vacia_sin_invalidar_la_respuesta`, `::test_textos_del_modelo_se_acotan_a_500`, `::test_respuesta_fuera_del_esquema_no_valida`; `tests/test_pdf_metadata.py` (todas); `tests/test_integracion_modelos.py::test_ingerir_clasifica_segun_criterio_l1[MOCK-DEMO-01|02|03|norma-LAFT]` | parcial: preselección verificada con el modelo real para los 3 manuales y la normativa LA/FT; la prioridad "LLM > metadato nativo" de `ingerir` no tiene aserción; el respaldo `SIN_RESPUESTA` cuando `clasificar` recibe `LLMOutputError` (`classifier.py:63-64`) no tiene prueba |
| RF-04 | Solo PDF, ≤ 20 MB, ≤ 100 páginas, rechazo de escaneados con mensaje de negocio | DEBE | L1 | `tests/test_config.py::test_limites_de_ingesta_coinciden_con_rf04`; `tests/test_validation.py::test_justo_max_pages_se_acepta`, `::test_max_pages_mas_uno_se_rechaza`, `::test_justo_max_mb_pasa_el_control_de_tamano`, `::test_max_mb_mas_un_byte_se_rechaza_sin_abrirlo`, `::test_proporcion_de_paginas_con_texto_en_el_limite`, `::test_una_pagina_cuenta_con_texto_desde_50_caracteres`, `::test_pdf_solo_con_imagen_se_rechaza_como_escaneado`, `::test_cabecera_falsa_vacio_o_corrupto`, `::test_pdf_con_contrasena`, `::test_pdf_sin_paginas`, `::test_pdf_truncado_se_rechaza`, `::test_pdf_sin_tabla_xref_se_acepta_con_advertencia`, `::test_pdf_de_varias_paginas_truncado_a_la_mitad_es_err_ing_003_no_001`, `::test_mock_sano_se_acepta_sin_advertencia` (docs/14 #21: reparado con texto suficiente → ok + `advertencia`; sin texto suficiente → ERR-ING-003; sano → sin advertencia; la clave `advertencia` de `ingerir()` se verifica en `test_integracion_modelos.py::test_ingerir_clasifica_segun_criterio_l1`), `::test_nombre_seguro*`; `tests/test_classifier.py::test_ingerir_rechaza_sin_llamar_al_modelo` | verificado (mensajes comparados con el literal de docs/05) |
| RF-05 | Botón "Procesar": extracción + seccionado + indexación con progreso | DEBE | L2 / L3 / D0 | Indexación (L3): `tests/test_chunker.py` (todas), `tests/test_index.py` (todas), `tests/test_integracion_l3.py::test_recall_de_candidatos_cumple_el_criterio_de_l3` (embeddings reales bge-m3, FAISS real) | parcial: verificada la indexación (sub-chunks, embeddings por lotes, caché, FAISS); el botón, el progreso por etapa y el encadenado con la extracción llegan en L2/D0 |
| RF-06 | Seccionado flexible (Artículo, ART., SEC., numerales, romanos, letras…) | DEBE | L2 | `tests/test_sectioner.py` | verificado |
| RF-07 | Sección con texto literal, ruta jerárquica, páginas y bandera de incierto | DEBE | L2 | `tests/test_sectioner.py` | verificado |
| RF-08 | Selector dual normativas / manuales | DEBE | U0 | — | pendiente |
| RF-09 | Marcar padre marca hijos; contador y buscador | DEBERÍA | U0 | — | pendiente |
| RF-10 | Ejecución de la doble vía con progreso de pares | DEBE | L4 | Parte L3 (candidatos y pares únicos de las dos vías): `tests/test_candidatos.py` (todas), `tests/test_pares.py` (todas), `tests/test_integracion_l3.py::test_pares_antes_y_despues_de_deduplicar` | parcial: verificada la construcción de pares de las dos vías; el juicio por par y el progreso son de L4 |
| RF-11 | Por par: marca, citas literales, comentario y confianza | DEBE | L4 | — (`test_citations`) | pendiente |
| RF-12 | Resultados filtrables por marca, por artículo o por sección | DEBERÍA | U0 | — | pendiente |
| RF-13 | Borrador de conclusión editable, rotulado como propuesta | DEBE | L5 | — | pendiente |
| RF-14 | Descarga del .xlsx con Hoja 1 y Hoja 2 | DEBE | L5 | — (`test_excel`) | pendiente |
| RF-15 | "Cargar ejemplo" sin ejecutar Docling | DEBE | D2 | — | pendiente |
| RF-16 | "Nueva sesión" con confirmación | DEBERÍA | U0 | — | pendiente |
| RNF-01 | Estado en memoria y `/tmp`, sin volúmenes ni tablas | — | D0 | — | pendiente |
| RNF-02 | Extracción en cola de 1 worker, hilos acotados, caché SHA-256 | — | L1 / L2 | `tests/test_validation.py::test_pdf_valido_devuelve_paginas_sha256_y_metadatos`, `::test_mismo_contenido_mismo_sha256`; `tests/test_integracion_modelos.py::test_ingerir_clasifica_segun_criterio_l1` (sha256 de 64) | parcial: solo la clave SHA-256 (L1); la cola de 1 worker y la caché llegan en L2 |
| RNF-03 | Concurrencia LLM con semáforo; reintentos con backoff ante 429/5xx | — | L0 / L4 | `tests/test_client.py::test_groq_devuelve_cliente_y_modelo_con_reintentos_y_timeout` (`max_retries = LLM_RETRIES`) | parcial: se comprueba que el SDK recibe `LLM_RETRIES` y el timeout; el semáforo es de L4 |
| RNF-04 | Progreso en operaciones > 2 s, polling 1,5 s | — | D0 / U0 | — | pendiente |
| RNF-05 | Mensajes de negocio en pantalla; trazas al log con código | — | L0 / L1 / D0 | `tests/test_errors.py` (todas); `tests/test_client.py::test_ping_sin_servicio_devuelve_mensaje_de_negocio_y_el_detalle_va_al_log`, `::test_chat_json_sin_servicio_aborta_como_no_disponible`, `::test_embed_sin_servicio_aborta_como_no_disponible`; `tests/test_validation.py::test_cabecera_falsa_vacio_o_corrupto`; `tests/test_integracion_modelos.py::test_clave_invalida_es_error_de_configuracion` | parcial: verificado en el backend de L0/L1; la pantalla y la API llegan en D0/U0 |
| RNF-06 | Cada fila del papel rastreable a archivo, página y sección; anexo completo | — | L4 / L5 | `tests/test_pares.py::test_scores_y_rangos_por_via` (cada `Par` guarda score y rank por vía, insumo del anexo) | parcial: solo el insumo de L3; el anexo y la ruta archivo/página/sección son de L5 |
| RNF-07 | Textos extraídos, nunca generados; citas verificadas en código | — | L4 | — (`test_citations`) | pendiente |
| RNF-08 | Excel y agregación sin tokens; cada par se juzga una vez | — | L4 / L5 | `tests/test_pares.py::test_union_de_las_dos_vias_sin_duplicados`, `::test_estadisticas_ingenuo_contra_unicos`; `tests/test_integracion_l3.py::test_pares_antes_y_despues_de_deduplicar` (637 ingenuos → 483 únicos) | parcial: verificada la deduplicación (un par = una llamada al juez); Excel y agregación (`test_aggregate`, `test_excel`) son de L4/L5 |
| RNF-09 | Máximo 3 pantallas; único campo obligatorio: tipo | — | U0 | — | pendiente |
| RNF-10 | Ejemplos precargados aunque Docling esté lento | — | D2 | — | pendiente |
| RNF-11 | 100 páginas en minutos; 50×40 secciones en < 15 min | — | L6 | — (se mide en notebook). Dato de L3, no es verificación: indexar 26 secciones LA/FT + 59 MOCK con bge-m3 en la Pi (`EMB_BATCH=8`) tardó 393 s (`qa/eval-l3.md`) | pendiente |
| RNF-12 | Autenticación de Apps; sin credenciales en código; documentos solo hacia el gateway | — | L0 / L1 / D1 | `tests/test_config.py::test_publico_oculta_secretos_con_valor_y_deja_el_resto`, `::test_es_secreto`, `::test_redact_*`, `::test_rellenar_prompt_*`; `tests/test_client.py::test_foundry_exige_https`; `tests/test_validation.py::test_nombre_seguro*`. Evidencia externa: auditoría `appsec` de L0 y L1 en `implementacion/README.md` (OBSERVACIONES, sin bloqueos) | parcial: verificado en el backend de L0/L1; QA-01 **corregido** (commit `eda0014`): `test_rellenar_prompt_marca_anidada_no_reconstruye_el_cierre` y `test_rellenar_prompt_quita_marca_con_atributos` pasan. La autenticación de Apps es de D1 |

## 2. Criterios de aceptación por hito

| Hito | Criterio | Evidencia (prueba o notebook) | Estado |
|---|---|---|---|
| L0 · Base | Una llamada al LLM devuelve JSON válido y un lote de embeddings sale normalizado L2, con Groq + `bge-m3` | `tests/test_integracion_modelos.py::test_ping_llm_y_embeddings`, `::test_lote_de_embeddings_normalizado_l2` (sandbox, Groq + Ollama `bge-m3`, pasan); `notebooks/00_modelos.ipynb` celda 12 ("L0 cumplido") | verificado |
| L1 · Ingesta | Los 3 MOCK salen como `manual_control` | `tests/test_integracion_modelos.py::test_ingerir_clasifica_segun_criterio_l1[MOCK-DEMO-01]`, `[MOCK-DEMO-02]`, `[MOCK-DEMO-03]` (sandbox, Groq + Ollama `bge-m3`, pasan) | verificado |
| L1 · Ingesta | La norma LA/FT sale como `normativa` | `tests/test_integracion_modelos.py::test_ingerir_clasifica_segun_criterio_l1[norma-LAFT]` (pasa; lee el PDF del clon de la v1 o de `NORMAS_DIR`, skip si no existe); `notebooks/01_ingesta.ipynb` celdas 5 y 9 | verificado |
| L1 · Ingesta | Un PDF fuera de límites (o escaneado) se rechaza con su mensaje | `tests/test_validation.py` (límites de páginas y MB, escaneo, cabecera, corrupto, contraseña, truncado → ERR-ING-003; mensajes literales de docs/05) | verificado |
| L2 · Seccionado | Artículos de LA/FT ≥ 95 % del conteo manual; reproceso usa la caché | — | pendiente |
| L3 · Recuperación | Recall en candidatos ≥ 90 % sobre el golden set; pares antes y después de deduplicar | `tests/test_integracion_l3.py::test_recall_de_candidatos_cumple_el_criterio_de_l3` (sandbox, Ollama `bge-m3`, `SIM_THRESHOLD=0.50`, `EMB_BATCH=8`): **28/30 = 93,3 %**; sin las 2 filas `por_confirmar` (art. 31→4.1, art. 37→V de MOCK-01): **28/28 = 100 %**. `::test_pares_antes_y_despues_de_deduplicar`: 637 ingenuos → 483 únicos. Secciones de entrada provisionales (ver `qa/eval-l3.md`) | verificado (con reservas: seccionado provisional, no la cascada de L2) |
| L4 · Juez | Toda cita es subcadena del texto fuente o está marcada; MOCK-03 mayormente A, MOCK-01 L, MOCK-02 R | — | pendiente |
| L5 · Papel | Excel sin advertencias; Hoja 1 cuadra con Hoja 2; cero llamadas al modelo | — | pendiente |
| L6 · Extremo a extremo | PDFs → Excel en una celda, con tiempos y RAM | — | pendiente |
| D0 · API | El E2E de L6 corre por la API en local | — | pendiente |
| D1 · App Free | La App arranca en Databricks Free, health OK, Docling dentro del contenedor | — | pendiente |
| D2 · Ejemplos | "Cargar ejemplo" funciona sin Docling | — | pendiente |
| U0 · UI mínima | Un auditor completa el flujo sin ayuda con el ejemplo | — | pendiente |

## 3. Defectos abiertos de L3 (todos BAJA; no bloquean)

| ID | Defecto | Prueba (xfail estricta) |
|---|---|---|
| QA-L3-01 | `subchunkear`: el solape se suma sobre el presupuesto; sub-chunks de ~562 tokens estimados con `SUBCHUNK_TOKENS=500` (`chunker.py`, `_empaquetar`) | `tests/test_chunker.py::test_ningun_subchunk_pasa_de_subchunk_tokens` |
| QA-L3-02 | `Indice.buscar` no valida NaN/inf en la consulta; FAISS devuelve índice -1 y `candidatos` da `[]` en silencio (`index.py` `buscar`, `candidatos.py:20`). Hoy no se alcanza: las consultas salen de `vectores_de`, ya validado | `tests/test_index.py::test_consulta_con_nan_o_inf_deberia_ser_err_idx_001`, `tests/test_candidatos.py::test_consulta_con_nan_no_deberia_dar_cero_candidatos_en_silencio` |
| QA-L3-03 | `K_SUBCHUNKS` cuenta sub-chunks, no secciones: una sección larga que ocupa los K deja menos de `MIN_FLOOR` candidatos | `tests/test_candidatos.py::test_min_floor_se_cumple_aunque_una_seccion_larga_ocupe_los_k_subchunks` |

Observación de entorno (no es del código): `config/.env` define `SIM_THRESHOLD`, que gana a `config/stages/sandbox.env` (0,50): una corrida normal de sandbox usa el valor de `.env`, no el calibrado. La prueba de integración lo detecta y exige `SIM_THRESHOLD=0.50` explícito.

## Resumen

- **RF/RNF verificados: 1 de 28** (RF-04). Parciales: RF-03, RF-05, RF-10, RNF-02, RNF-03, RNF-05, RNF-06, RNF-08, RNF-12 (partes de hitos futuros o sin aserción, ver cada fila; RF-05, RF-10, RNF-06 y RNF-08 avanzan con L3). Falla: ninguno. Pendientes (su hito no llega): 22.
- **Criterios de hito verificados: 5 de 6 de L0–L3** (L0; L1: los 3 criterios; L3: recall 93,3 % con embeddings reales, ver reservas). L2 pendiente de verificación en esta rama; resto de hitos: pendiente.
- **Defectos:** QA-01 corregido y re-verificado. Abiertos: QA-L3-01, QA-L3-02, QA-L3-03 (BAJA, con prueba xfail estricta; ver sección 3).
- **Coverage de la última corrida** (`pytest -m "not integracion" --cov=backend`, rama `test/l3-recuperacion`): módulos de L3 `candidatos.py` 100 %, `pares.py` 100 %, `chunker.py` 97 %, `index.py` 100 % (umbral 80 %). `TOTAL 743 158 79%`: por debajo del 80 % quedan módulos que no son de L3 y se ejercitan en integración: `docling_parser.py` 0 % y `docling_worker.py` 0 % (L2, sin pruebas unitarias en esta rama) y `classifier.py` 79 %. Sin exclusiones.
- Unitarias: `273 passed, 12 deselected, 5 xfailed in 9.96s` (5 xfail estrictas = QA-L3-01..03). Integración L3 (sandbox, Ollama `bge-m3`): `4 passed in 393.71s`.
- **Fecha:** 7 oct 2026 · **commit base:** `5fae52a` (rama `test/l3-recuperacion`; pruebas y matriz sin commitear).
