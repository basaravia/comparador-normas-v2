# Evaluación de IA · L3 Recuperación

- **Fecha:** 7 oct 2026 · **rama:** `test/l3-recuperacion` (commit base `5fae52a`)
- **Stage:** sandbox · embeddings Ollama `bge-m3` (reales) · FAISS `IndexFlatIP` (real) · sin LLM evaluador (L3 no lo necesita)
- **Configuración:** `SIM_THRESHOLD=0.50` (del stage; hubo que fijarlo por variable porque `config/.env` lo pisa con 0,30), `K_SUBCHUNKS=10`, `MIN_FLOOR=3`, `MAX_CANDIDATES=10`, `SUBCHUNK_TOKENS=500`, `EMB_BATCH=8`, `LLM_TIMEOUT_S=900`, `taskset -c 3`
- **Comando:** `STAGE=sandbox SIM_THRESHOLD=0.50 EMB_BATCH=8 LLM_TIMEOUT_S=900 taskset -c 3 pytest -m integracion tests/test_integracion_l3.py -s`

## Entrada (provisional)
- Normativa: bloques de Docling real de `/tmp/claude-1000/motor-l3/lafit.json` (LA/FT págs. 19-24) -> `parsear_bloques` de esta rama (seccionador de L1; la cascada de L2 no está aquí) tras partir los "Artículo N.-" pegados en un bloque. 26 secciones; 18 seleccionadas (arts. 31-48).
- Manuales: los 3 MOCK de `samples/` con las secciones provisionales del notebook 03 (una `Seccion` por encabezado romano o numeral, texto hasta el siguiente encabezado, índice del PDF descartado, `seccionado_incierto=True`): M1 21, M2 14, M3 24 secciones.
- Golden: `tests/golden_pairs.csv`, 51 filas = 30 con sección (recall) + 21 omisiones (no recuperables, no cuentan).

## Resultados
| Métrica | Valor | Umbral |
|---|---|---|
| recall@candidatos (30 pares) | **28/30 = 93,3 %** | >= 90 % |
| recall@candidatos sin las 2 filas `por_confirmar` | **28/28 = 100 %** | — |
| recall@k (mejor rank de las dos vías) k=1/3/5/10/20 | 53,3 / 80,0 / 83,3 / 96,7 / 100 % | informativo |
| precision@k vía 1, k=1/3/5/10 | 64,7 / 37,3 / 25,9 / 13,5 % | informativo |
| precision@candidatos (28 aciertos / 483 pares únicos) | 5,8 % | informativo (el diseño prioriza recall) |
| Pares ingenuos -> únicos | 637 -> 483 (solo_v1 20, solo_v2 309, ambas 154; -24 % de llamadas al juez) | — |
| Tiempo | indexar 393 s (norma + manual, Pi con Ollama compartido) · pares 0,01 s | — |

Fallos (los 2 esperados): Artículo 31 -> MOCK-DEMO-01 4.1 y Artículo 37 -> MOCK-DEMO-01 V, ambas `parcial` y `por_confirmar` en el golden.
Margen: 93,3 % queda a 3,3 puntos del umbral; la métrica es determinista dado el modelo, pero depende de la sección provisional.

## Qué sustituiría RAGAS (tarjeta P-11, cuando exista `comparador_eval`)
| Métrica propia (hoy) | Métrica RAGAS equivalente | Nota |
|---|---|---|
| recall@candidatos | `IDBasedContextRecall` (o `NonLLMContextRecall`) | recuperado = ids de sección candidatos; referencia = ids del golden. Sin LLM evaluador |
| precision@k / @candidatos | `IDBasedContextPrecision` (o `NonLLMContextPrecisionWithReference`) | idem |
| (L4) citas y comentarios | `Faithfulness`, `AspectCritic`/`RubricsScore` | con el LLM real del stage; no aplica en L3 |

Confirmar los nombres exactos contra la versión de RAGAS que fije `requirements-eval.txt`; no se instaló (el entorno no existe). Las métricas propias seguirán como contraste: deben coincidir con las de RAGAS sobre los mismos ids.
