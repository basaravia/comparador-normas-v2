# 13 · Plan de implementación por hitos

Revisado el 1 oct 2026. Principio: **MVP lo más sencillo posible, mejorado por iteraciones**. Primero el backend, validado de punta a punta con notebooks en local; después el despliegue; la UI al final. Se avanza **paso a paso**: no se pasa de hito sin cumplir su criterio de aceptación.

Entornos y modelos: ver [14](14-puntos-abiertos.md) puntos 13–15.

## Fase L · Backend en local (notebooks; stages dev y sandbox)

Cada hito trae su notebook en `notebooks/` que lo ejercita con los documentos MOCK, sin API ni UI.

**Cierre de cada hito: en el stage sandbox** (Raspberry, Groq + Ollama `bge-m3`). El stage dev (MacBook con DMR) es opcional: el usuario lo prueba cuando quiera y no bloquea el avance (decisión del 2 oct 2026).

| Hito | Entregable | Notebook | Criterio de aceptación |
|---|---|---|---|
| **L0 · Base** | Estructura de `backend/`, `config.py`, `core/errors.py`, cliente de modelos con proveedor por configuración y stages (DMR / Groq / Ollama / Foundry) | `00_modelos.ipynb` | Una llamada al LLM devuelve JSON válido y un lote de embeddings sale normalizado L2, con Groq + `bge-m3` |
| **L1 · Ingesta** | Validación (límites, escaneo), metadatos nativos, clasificador LLM | `01_ingesta.ipynb` | Los 3 MOCK salen como `manual_control` y la norma LA/FT como `normativa`; un PDF fuera de límites se rechaza con su mensaje |
| **L2 · Seccionado** | Docling (`do_ocr=False`, 1 worker) + cascada de seccionado | `02_seccionado.ipynb` | Los artículos de la norma LA/FT coinciden con el conteo manual (≥ 95 %); volver a procesar el mismo PDF usa la caché |
| **L3 · Recuperación** | Sub-chunks, embeddings, FAISS, candidatos, pares únicos | `03_recuperacion.ipynb` | Recall en candidatos ≥ 90 % sobre el golden set; se registran los pares antes y después de deduplicar |
| **L3b · Recuperación robusta por stage** | Ventanas multi-vector (sin promediar ni recortar), calibración de umbral/K/candidatos por stage con validación cruzada por artículo, golden ampliado (≥100 positivos, con estratos), métricas (recall por vía, MRR, nDCG, IC de Wilson), ablación de híbrida y reranker (se miden, no se adoptan salvo mejora clara) | `03b_recuperacion_robusta.ipynb` | Recall en candidatos ≥ 90 % **en cada stage**; cero textos recortados o rechazados por largo y cero vectores promediados; las 2 filas `por_confirmar` resueltas por el usuario |
| **L4 · Juez** | Juez concurrente, validación, verificación de citas, agregación A/L/R/X/P, vía 2 | `04_juez.ipynb` | Toda cita es subcadena del texto fuente o está marcada; MOCK-DEMO-03 sale mayormente **A**, MOCK-DEMO-01 **L** y MOCK-DEMO-02 **R** |
| **L5 · Papel** | Hoja 1 + Hoja 2 (con bloque vía 2) + borrador de conclusión | `05_papel.ipynb` | El Excel abre sin advertencias; los conteos de la Hoja 1 cuadran con la Hoja 2; cero llamadas al modelo al generarlo |
| **L6 · Extremo a extremo** | Servicio que encadena L1–L5 | `06_e2e.ipynb` | PDFs → Excel en una sola celda, con tiempos y RAM medidos en la Raspberry |

## Fase D · Despliegue en Databricks Free

| Hito | Entregable | Criterio de aceptación |
|---|---|---|
| **D0 · API** | FastAPI con los endpoints de [11](11-api.md), sesión en memoria, `/api/health` | El E2E de L6 corre por la API en local |
| **D1 · App Free** | `app.yaml` (sin `--port`, ver [14](14-puntos-abiertos.md) punto 17), paquete de menos de 10 MB, deploy | La App arranca en Databricks Free, health OK y Docling convierte un PDF **dentro del contenedor** |
| **D2 · Ejemplos** | `samples/` precomputados (secciones `.json` + embeddings `.npy`) | "Cargar ejemplo" funciona sin ejecutar Docling |

## Fase U · Interfaz

| Hito | Entregable | Criterio de aceptación |
|---|---|---|
| **U0 · UI mínima** | Carga, procesamiento, selector dual, resultados y descarga ([05](05-ux.md)), en verde y blanco | Un auditor completa el flujo sin ayuda con el ejemplo |

## Fase Demo · Azure de pago + Foundry

Cambiar por configuración a los endpoints de Foundry, recalibrar el umbral para `text-embedding-3-large` y ensayar con los documentos reales.

> **Contingencia.** Si la extracción en vivo no es estable, la demo usa los ejemplos precargados de D2 y la carga en vivo se muestra con un documento corto.

## Pruebas mínimas (pytest)

Las escribe y ejecuta el agente `qa-ia` al cerrar cada hito. **Un hito no se cierra sin coverage ≥ 80 % en la lógica determinista** (`pytest -m "not integracion" --cov`) y sin **APROBADO** de `qa-ia` (decisión del usuario, 6 oct 2026). Las pruebas con modelos reales llevan la marca `integracion` y no cuentan para el porcentaje. Desde L3 se evalúan recuperación y juez con **RAGAS** (solo desarrollo, sin telemetría). Trazabilidad RF/RNF ↔ pruebas en `qa/trazabilidad.md`; no hay historias de usuario.

- `test_sectioner`: fixtures con Artículo, ART., SEC., romanos, letras, numeración 3.2.1 y un `ARTÍCULO` duplicado.
- `test_aggregate`: tablas de verdad de la agregación de marcas y de los controles sin base normativa.
- `test_citations`: cita exacta, con espacios distintos, parafraseada (debe marcarse) y truncada.
- `test_excel`: columnas y orden, leyenda, celdas combinadas, truncado a 32.767 caracteres.
- Humo extremo a extremo con los manuales MOCK, **LLM y embeddings reales del stage** (sandbox: Groq + Ollama `bge-m3`; dev: DMR) **sobre FAISS real**.

> **Sin simulaciones de modelos.** Ni el LLM ni los embeddings ni el índice vectorial se simulan en ningún hito ni prueba de integración: los notebooks y el humo E2E usan los modelos reales del stage y FAISS real. Solo las pruebas unitarias de lógica determinista (seccionado, citas, agregación, Excel) corren sin modelo, porque no lo necesitan. "MOCK" se refiere únicamente a los **documentos** de prueba ficticios de la v1.

## Golden set (L3 y L4)
`tests/golden_pairs.csv`, construido desde la matriz de `LEEME-MANUALES-MOCK.md` de la v1: norma LA/FT (arts. 31–48) contra MOCK-DEMO-01/02/03, con la cobertura esperada.
- `recall@candidatos = pares_golden_en_candidatos / total_golden`.
- Reportar los fallos con sus scores para ajustar `SIM_THRESHOLD` y `K_SUBCHUNKS`.

## Deuda técnica marcada (limpieza pendiente; usuario, 12 oct 2026: "luego podamos, de momento se deja como está")
Nada de esto bloquea un hito. Se poda cuando el usuario lo decida (solo él desestima o cancela).
- **Ramas integradas en `main` que se pueden podar** (la remota y la local): `chore/pool-dev-ia`, `feat/exclusion-secciones`, `feat/l2-extraccion-docling`, `feat/l2-seccionado`, `fix/docling-cve`, `fix/l2-estado-real`, `legacy/equipo-ia` (esta guarda el pool de IA retirado el 7 oct: decidir si se conserva como referencia).
- **Ramas con trabajo propio sin decidir:** `aux/docling-modelos` y `chore/ci-github-actions` (con sus worktrees `wt-aux-docling` y `wt-chore-ci`).
- **Qué va a `main` desde `test/qwen3-embedding`, `docs/reranker-qwen3` y `feat/zonas-test-val`** (zonas, 03d, límite de 250 páginas, reranker opcional, `validacion.py`, 03c y scripts de comparación): se decide con los resultados del 03d y del 03c en la máquina de desarrollo. Candidatos a salir: `scripts/ablacion_recuperacion.py` (BM25, no se adopta) y `scripts/medir_recuperacion.py`.
- **Docs:** falta la fila #25 (reranker) de `docs/14` en la rama de zonas (está en `docs/reranker-qwen3`); las filas #26 y #27 no cierran con `|`.
- **Endurecimientos opcionales** (guardián): exigir que `--salida` de `comparar_recuperacion.py` quede dentro de `output/<zona>/`; rechazar enlaces simbólicos en `zona_de`; aceptar solo `int` y no `bool` en `resolver()`.
- **Proceso:** `appsec` y `product-owner` no revisaron los commits de estas ramas (no estaban disponibles) y el tablero (`tablero/datos.js`) no se actualizó en sus pushes.
- **Medir:** RAM y tiempo de Docling con 250 páginas reales (docs/14 #10 y #27).
