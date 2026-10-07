# Matriz de trazabilidad (QA)

Requisitos de `docs/04-requerimientos.md` y criterios de aceptación de `docs/13-plan-hitos.md` frente a las pruebas que los verifican. La escribe el agente `qa-ia`; la lee el `product-owner`. No hay historias de usuario (decisión del usuario).

Estados: `verificado` (hay prueba y pasa) · `falla` (hay prueba y no pasa) · `parcial` (cubre solo una parte; se dice cuál) · `sin prueba` (hay código pero no se prueba) · `pendiente` (su hito aún no llega).

Pasada base sobre L0 y L1 (cerrados antes de existir la regla de QA) y re-verificación tras la corrección de QA-01 y del PDF truncado (rama `fix/neutralizar-marcas-pdf-truncado`). Las rutas de pruebas son relativas a `comparador-dbx/`.

Pasada de L2 · Seccionado (rama `test/l2-seccionado`): pruebas de `backend/extraction/` y su integración con Docling real.

## 1. Requisitos

| ID | Requisito (resumen) | Prioridad | Hito | Pruebas | Estado |
|---|---|---|---|---|---|
| RF-01 | Carga múltiple de PDFs en una zona de arrastre | DEBE | D0 / U0 | — | pendiente |
| RF-02 | Tabla por archivo: nombre, tipo, metadatos editables, estado | DEBE | D0 / U0 | — (la fila que devuelve `ingerir` se prueba en RF-03) | pendiente |
| RF-03 | Preselección de tipo y metadatos desde nombre, 2 primeras páginas y metadatos nativos | DEBE | L1 | `tests/test_classifier.py::test_tipo_sugerido_*`, `::test_desconocido_nunca_se_preselecciona`, `::test_sin_respuesta_queda_desconocido_y_sin_preseleccion`, `::test_fecha_invalida_queda_vacia_sin_invalidar_la_respuesta`, `::test_textos_del_modelo_se_acotan_a_500`, `::test_respuesta_fuera_del_esquema_no_valida`; `tests/test_pdf_metadata.py` (todas); `tests/test_integracion_modelos.py::test_ingerir_clasifica_segun_criterio_l1[MOCK-DEMO-01|02|03|norma-LAFT]` | parcial: preselección verificada con el modelo real para los 3 manuales y la normativa LA/FT; la prioridad "LLM > metadato nativo" de `ingerir` no tiene aserción; el respaldo `SIN_RESPUESTA` cuando `clasificar` recibe `LLMOutputError` (`classifier.py:63-64`) no tiene prueba |
| RF-04 | Solo PDF, ≤ 20 MB, ≤ 100 páginas, rechazo de escaneados con mensaje de negocio | DEBE | L1 | `tests/test_config.py::test_limites_de_ingesta_coinciden_con_rf04`; `tests/test_validation.py::test_justo_max_pages_se_acepta`, `::test_max_pages_mas_uno_se_rechaza`, `::test_justo_max_mb_pasa_el_control_de_tamano`, `::test_max_mb_mas_un_byte_se_rechaza_sin_abrirlo`, `::test_proporcion_de_paginas_con_texto_en_el_limite`, `::test_una_pagina_cuenta_con_texto_desde_50_caracteres`, `::test_pdf_solo_con_imagen_se_rechaza_como_escaneado`, `::test_cabecera_falsa_vacio_o_corrupto`, `::test_pdf_con_contrasena`, `::test_pdf_sin_paginas`, `::test_pdf_truncado_se_rechaza`, `::test_pdf_sin_tabla_xref_se_acepta_con_advertencia`, `::test_pdf_de_varias_paginas_truncado_a_la_mitad_es_err_ing_003_no_001`, `::test_mock_sano_se_acepta_sin_advertencia` (docs/14 #21: reparado con texto suficiente → ok + `advertencia`; sin texto suficiente → ERR-ING-003; sano → sin advertencia; la clave `advertencia` de `ingerir()` se verifica en `test_integracion_modelos.py::test_ingerir_clasifica_segun_criterio_l1`), `::test_nombre_seguro*`; `tests/test_classifier.py::test_ingerir_rechaza_sin_llamar_al_modelo` | verificado (mensajes comparados con el literal de docs/05) |
| RF-05 | Botón "Procesar": extracción + seccionado + indexación con progreso | DEBE | L2 / L3 / D0 | `tests/test_docling_extractor.py::test_progreso_se_informa_por_tanda_y_el_ruido_de_stdout_se_ignora`, `::test_sin_callback_de_progreso_no_falla`; `tests/test_integracion_extraccion.py::test_docling_real_extrae_cap_iii_y_informa_progreso` (Docling real: progreso `[(3, 3)]`) | parcial: verificado el progreso por tanda de páginas de la extracción (L2); el botón, el progreso por documento y etapa y la indexación son de L3 / D0 / U0 |
| RF-06 | Seccionado flexible: Artículo, ART., Sección, SEC., numerales, romanos, letras, viñetas; fallback tipográfico y por longitud | DEBE | L2 | `tests/test_sectioner.py` (`test_articulo`, `test_art_abreviado_y_mayusculas`, `test_seccion_y_sec`, `test_romanos`, `test_letras_*`, `test_numeracion_jerarquica_3_2_1`, `test_ordinales_*`, `test_capitulo_primero_en_palabras`, `test_articulo_con_sufijo_5a_*`, `test_articulo_duplicado_*`, `test_literales_quedan_dentro_del_articulo`, `test_disposiciones_*`, `test_patron_con_menos_de_3_*`, `test_numeral_con_menos_de_3_*`, `test_encabezado_validado_*`, `test_tipografia_*`, `test_longitud_*`, `test_numero_*`, `test_regex_hostiles_*`); `tests/test_integracion_extraccion.py::test_cap_iii_tiene_8_articulos_*`, `::test_laft_99_de_99_*` | verificado (viñetas = literales a), b) que quedan dentro del artículo; hallazgo QA-03 Baja, ver abajo) |
| RF-07 | Sección con texto literal, ruta jerárquica, páginas y bandera de incierto | DEBE | L2 | `tests/test_sectioner.py::test_cada_seccion_es_subcadena_*`, `::test_texto_literal_de_secciones_por_longitud_*`, `::test_ids_con_todas_las_abreviaturas_*`, `::test_nivel_ausente_se_omite_*`, `::test_capitulo_hermano_de_un_articulo_*`, `::test_numeracion_decreciente_*`, `::test_capitulo_que_no_empieza_en_1_*`, `::test_los_articulos_deben_crecer_*`, `::test_numeral_bajo_un_padre_*`, `::test_longitud_agrupa_*`; `tests/test_integracion_extraccion.py` (rutas 8/8 y 98/99; toda ruta errónea viene marcada incierta) | verificado |
| RF-08 | Selector dual normativas / manuales | DEBE | U0 | — | pendiente |
| RF-09 | Marcar padre marca hijos; contador y buscador | DEBERÍA | U0 | — | pendiente |
| RF-10 | Ejecución de la doble vía con progreso de pares | DEBE | L4 | — | pendiente |
| RF-11 | Por par: marca, citas literales, comentario y confianza | DEBE | L4 | — (`test_citations`) | pendiente |
| RF-12 | Resultados filtrables por marca, por artículo o por sección | DEBERÍA | U0 | — | pendiente |
| RF-13 | Borrador de conclusión editable, rotulado como propuesta | DEBE | L5 | — | pendiente |
| RF-14 | Descarga del .xlsx con Hoja 1 y Hoja 2 | DEBE | L5 | — (`test_excel`) | pendiente |
| RF-15 | "Cargar ejemplo" sin ejecutar Docling | DEBE | D2 | — | pendiente |
| RF-16 | "Nueva sesión" con confirmación | DEBERÍA | U0 | — | pendiente |
| RNF-01 | Estado en memoria y `/tmp`, sin volúmenes ni tablas | — | D0 | — | pendiente |
| RNF-02 | Extracción en cola de 1 worker, hilos acotados, caché SHA-256 | — | L1 / L2 | `tests/test_docling_extractor.py::test_la_cola_tiene_un_solo_worker`, `::test_dos_extracciones_simultaneas_nunca_corren_en_paralelo`, `::test_el_mismo_pdf_pedido_a_la_vez_*`, `::test_reprocesar_el_mismo_pdf_usa_la_cache`, `::test_la_clave_es_el_contenido_*`, `::test_la_cache_tiene_tope_max_cache_*`, `::test_el_hijo_recibe_un_entorno_minimo_*` (`OMP_NUM_THREADS` = `DOCLING_THREADS`); `tests/test_validation.py::test_mismo_contenido_mismo_sha256`; `tests/test_integracion_extraccion.py::test_reprocesar_el_mismo_pdf_usa_la_cache` (Docling real: 47,1 s → 0,015 s) | parcial: cola, caché, tope y hilos verificados; el timeout no se aplica si el trabajador ignora SIGTERM (QA-02, Media) |
| RNF-03 | Concurrencia LLM con semáforo; reintentos con backoff ante 429/5xx | — | L0 / L4 | `tests/test_client.py::test_groq_devuelve_cliente_y_modelo_con_reintentos_y_timeout` (`max_retries = LLM_RETRIES`) | parcial: se comprueba que el SDK recibe `LLM_RETRIES` y el timeout; el semáforo es de L4 |
| RNF-04 | Progreso en operaciones > 2 s, polling 1,5 s | — | D0 / U0 | — | pendiente |
| RNF-05 | Mensajes de negocio en pantalla; trazas al log con código | — | L0 / L1 / D0 | `tests/test_errors.py` (todas); `tests/test_client.py::test_ping_sin_servicio_devuelve_mensaje_de_negocio_y_el_detalle_va_al_log`, `::test_chat_json_sin_servicio_aborta_como_no_disponible`, `::test_embed_sin_servicio_aborta_como_no_disponible`; `tests/test_validation.py::test_cabecera_falsa_vacio_o_corrupto`; `tests/test_integracion_modelos.py::test_clave_invalida_es_error_de_configuracion` | parcial: verificado en el backend de L0/L1; la pantalla y la API llegan en D0/U0 |
| RNF-06 | Cada fila del papel rastreable a archivo, página y sección; anexo completo | — | L4 / L5 | — | pendiente |
| RNF-07 | Textos extraídos, nunca generados; citas verificadas en código | — | L4 | — (`test_citations`) | pendiente |
| RNF-08 | Excel y agregación sin tokens; cada par se juzga una vez | — | L4 / L5 | — (`test_aggregate`, `test_excel`) | pendiente |
| RNF-09 | Máximo 3 pantallas; único campo obligatorio: tipo | — | U0 | — | pendiente |
| RNF-10 | Ejemplos precargados aunque Docling esté lento | — | D2 | — | pendiente |
| RNF-11 | 100 páginas en minutos; 50×40 secciones en < 15 min | — | L6 | — (se mide en notebook) | pendiente |
| RNF-12 | Autenticación de Apps; sin credenciales en código; documentos solo hacia el gateway | — | L0 / L1 / D1 | `tests/test_config.py::test_publico_oculta_secretos_con_valor_y_deja_el_resto`, `::test_es_secreto`, `::test_redact_*`, `::test_rellenar_prompt_*`; `tests/test_client.py::test_foundry_exige_https`; `tests/test_validation.py::test_nombre_seguro*`. Evidencia externa: auditoría `appsec` de L0 y L1 en `implementacion/README.md` (OBSERVACIONES, sin bloqueos) | parcial: verificado en el backend de L0/L1; QA-01 **corregido** (commit `eda0014`): `test_rellenar_prompt_marca_anidada_no_reconstruye_el_cierre` y `test_rellenar_prompt_quita_marca_con_atributos` pasan. La autenticación de Apps es de D1 |

## 2. Criterios de aceptación por hito

| Hito | Criterio | Evidencia (prueba o notebook) | Estado |
|---|---|---|---|
| L0 · Base | Una llamada al LLM devuelve JSON válido y un lote de embeddings sale normalizado L2, con Groq + `bge-m3` | `tests/test_integracion_modelos.py::test_ping_llm_y_embeddings`, `::test_lote_de_embeddings_normalizado_l2` (sandbox, Groq + Ollama `bge-m3`, pasan); `notebooks/00_modelos.ipynb` celda 12 ("L0 cumplido") | verificado |
| L1 · Ingesta | Los 3 MOCK salen como `manual_control` | `tests/test_integracion_modelos.py::test_ingerir_clasifica_segun_criterio_l1[MOCK-DEMO-01]`, `[MOCK-DEMO-02]`, `[MOCK-DEMO-03]` (sandbox, Groq + Ollama `bge-m3`, pasan) | verificado |
| L1 · Ingesta | La norma LA/FT sale como `normativa` | `tests/test_integracion_modelos.py::test_ingerir_clasifica_segun_criterio_l1[norma-LAFT]` (pasa; lee el PDF del clon de la v1 o de `NORMAS_DIR`, skip si no existe); `notebooks/01_ingesta.ipynb` celdas 5 y 9 | verificado |
| L1 · Ingesta | Un PDF fuera de límites (o escaneado) se rechaza con su mensaje | `tests/test_validation.py` (límites de páginas y MB, escaneo, cabecera, corrupto, contraseña, truncado → ERR-ING-003; mensajes literales de docs/05) | verificado |
| L2 · Seccionado | Artículos de LA/FT ≥ 95 % del conteo manual | `tests/test_integracion_extraccion.py::test_laft_99_de_99_articulos_y_rutas_98_de_99_con_los_bloques_ya_extraidos` (99/99 = 100 %, 0 FP, 0 FN; rutas 98/99, la que falla es el Artículo 1 y viene marcada incierta); `::test_cap_iii_tiene_8_articulos_y_8_de_8_rutas_contra_la_referencia` (Docling real). Referencia: regex propia sobre texto PyMuPDF. Para la LA/FT se usaron los bloques extraídos por el desarrollador (`/tmp/claude-1000/extraccion-l2/lafit.json`), no se re-ejecutó Docling (12 min) | verificado |
| L2 · Seccionado | Volver a procesar el mismo PDF usa la caché | `tests/test_integracion_extraccion.py::test_reprocesar_el_mismo_pdf_usa_la_cache` (Docling real, cap-III: 47,1 s → 0,015 s); unitarias `tests/test_docling_extractor.py::test_reprocesar_el_mismo_pdf_usa_la_cache` | verificado |
| L3 · Recuperación | Recall en candidatos ≥ 90 % sobre el golden set; pares antes y después de deduplicar | — | pendiente |
| L4 · Juez | Toda cita es subcadena del texto fuente o está marcada; MOCK-03 mayormente A, MOCK-01 L, MOCK-02 R | — | pendiente |
| L5 · Papel | Excel sin advertencias; Hoja 1 cuadra con Hoja 2; cero llamadas al modelo | — | pendiente |
| L6 · Extremo a extremo | PDFs → Excel en una celda, con tiempos y RAM | — | pendiente |
| D0 · API | El E2E de L6 corre por la API en local | — | pendiente |
| D1 · App Free | La App arranca en Databricks Free, health OK, Docling dentro del contenedor | — | pendiente |
| D2 · Ejemplos | "Cargar ejemplo" funciona sin Docling | — | pendiente |
| U0 · UI mínima | Un auditor completa el flujo sin ayuda con el ejemplo | — | pendiente |

## Resumen

- **RF/RNF verificados: 3 de 28** (RF-04, RF-06, RF-07). Parciales: RF-03, RF-05, RNF-02, RNF-03, RNF-05, RNF-12 (partes de hitos futuros, sin aserción, o QA-02; ver cada fila). Falla: ninguno. Pendientes (su hito no llega): 19.
- **Criterios de hito verificados: 6 de 6 de L0–L2** (L0; L1 ×3; L2 ×2: artículos LA/FT ≥ 95 % y caché). Resto de hitos: pendiente.
- **Defectos abiertos (L2):** QA-02 (Media): con el timeout vencido, si el trabajador ignora SIGTERM no se aplica el SIGKILL (`docling_extractor.py:109-125`); `tests/test_docling_extractor.py::test_timeout_se_aplica_aunque_el_trabajador_ignore_sigterm` (xfail). QA-03 (Baja): `ARTÍCULO ÚNICO` se numera como 1 y colisiona con `Artículo 1` (id `ART-1#2`, incierto, aviso de duplicado). Conocido e inalcanzable: `numero('9'*5000)` lanza `ValueError` (xfail con motivo).
- **Coverage de la última corrida** (`pytest -m "not integracion" --cov=backend`): **96 %** (`TOTAL 784 33 96%`, 317 passed, 12 deselected, 2 xfailed), umbral 80 %. `extraction/`: `docling_extractor.py` 94 %, `docling_worker.py` 100 %, `patterns.py` 100 %, `sectioner.py` 99 %. **Exclusión anotada:** `docling_worker.main()` (y su `__main__`) se excluye con `exclude_also` en `tests/.coveragerc` porque solo se ejecuta con Docling real; sin la exclusión el módulo da 21 %. Lo cubre `test_integracion_extraccion.py`. Fuera de L2, `ingest/classifier.py` está en 79 % (L1, líneas 57-64 y 82-89, preexistente).
- Integración de L2 (Docling real, `taskset -c 3`, 1 hilo): `4 passed in 48.76s`.
- **Fecha:** 7 oct 2026 · **commit:** `0e1ef19` (rama `test/l2-seccionado`; pruebas y matriz sin commitear).
