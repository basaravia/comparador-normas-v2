# 13 · Plan de implementación por hitos

Revisado el 1 oct 2026. Principio: **MVP lo más sencillo posible, mejorado por iteraciones**. Primero el backend, validado de punta a punta con notebooks en local; después el despliegue; la UI al final. Se avanza **paso a paso**: no se pasa de hito sin cumplir su criterio de aceptación.

Entornos y modelos: ver [14](14-puntos-abiertos.md) puntos 13–15.

## Fase L · Backend en local (Raspberry, notebooks, Groq + Ollama)

Cada hito trae su notebook en `notebooks/` que lo ejercita con los documentos MOCK, sin API ni UI.

| Hito | Entregable | Notebook | Criterio de aceptación |
|---|---|---|---|
| **L0 · Base** | Estructura de `backend/`, `config.py`, `core/errors.py`, cliente de modelos con proveedor por configuración (Groq / Ollama / Foundry) | `00_modelos.ipynb` | Una llamada al LLM devuelve JSON válido y un lote de embeddings sale normalizado L2, con Groq + `bge-m3` |
| **L1 · Ingesta** | Validación (límites, escaneo), metadatos nativos, clasificador LLM | `01_ingesta.ipynb` | Los 3 MOCK salen como `manual_control` y la norma LA/FT como `normativa`; un PDF fuera de límites se rechaza con su mensaje |
| **L2 · Seccionado** | Docling (`do_ocr=False`, 1 worker) + cascada de seccionado | `02_seccionado.ipynb` | Los artículos de la norma LA/FT coinciden con el conteo manual (≥ 95 %); volver a procesar el mismo PDF usa la caché |
| **L3 · Recuperación** | Sub-chunks, embeddings, FAISS, candidatos, pares únicos | `03_recuperacion.ipynb` | Recall en candidatos ≥ 90 % sobre el golden set; se registran los pares antes y después de deduplicar |
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
- `test_sectioner`: fixtures con Artículo, ART., SEC., romanos, letras, numeración 3.2.1 y un `ARTÍCULO` duplicado.
- `test_aggregate`: tablas de verdad de la agregación de marcas y de los controles sin base normativa.
- `test_citations`: cita exacta, con espacios distintos, parafraseada (debe marcarse) y truncada.
- `test_excel`: columnas y orden, leyenda, celdas combinadas, truncado a 32.767 caracteres.
- Humo extremo a extremo con los manuales MOCK, **LLM real (Groq) y embeddings reales (Ollama `bge-m3`) sobre FAISS real**.

> **Sin simulaciones de modelos.** Ni el LLM ni los embeddings ni el índice vectorial se simulan en ningún hito ni prueba de integración: los notebooks y el humo E2E usan Groq, `bge-m3` y FAISS reales. Solo las pruebas unitarias de lógica determinista (seccionado, citas, agregación, Excel) corren sin modelo, porque no lo necesitan. "MOCK" se refiere únicamente a los **documentos** de prueba ficticios de la v1.

## Golden set (L3 y L4)
`tests/golden_pairs.csv`, construido desde la matriz de `LEEME-MANUALES-MOCK.md` de la v1: norma LA/FT (arts. 31–48) contra MOCK-DEMO-01/02/03, con la cobertura esperada.
- `recall@candidatos = pares_golden_en_candidatos / total_golden`.
- Reportar los fallos con sus scores para ajustar `SIM_THRESHOLD` y `K_SUBCHUNKS`.
