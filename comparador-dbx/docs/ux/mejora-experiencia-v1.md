# UX · Selección como índice, progreso del paso 1 y del paso 2 (v1)

Wireframes (SVG, baja fidelidad; ábrelos en el navegador): `wireframes/seleccion-indice-v1.svg`, `wireframes/procesamiento-v1.svg`, `wireframes/comparacion-v1.svg`.
Penpot no estaba disponible. Nada de esto está implementado; "requiere backend" = el job o la API hoy no entrega el dato.

## (a) Por qué hoy se pierde la atención (evidencia en el código)

| Pantalla | Hallazgo | Evidencia |
|---|---|---|
| Selección | Solo se ve el primer nivel abierto: el árbol nace con `useState(nivel < 1)`, así que capítulos y artículos están cerrados y nada indica que hay más. | `DualTree.tsx` línea del `useState(nivel < 1)` |
| Selección | Las ramas no dicen cuánto contienen ni cuánto está marcado; no hay "expandir todo", búsqueda ni "solo marcados". El chevron mide 20 px (WCAG 2.2: ≥ 24 px) y no hay navegación por teclado de árbol. | `.plegar{width:20px}` en `estilos.css`; no hay `role="tree"` |
| Selección | No parece un índice: sin número de página alineado, sin líneas guía, y la previsualización aparece solo al abrir hojas. | `NodoOut.pagina_inicio` existe pero no se muestra |
| Paso 1 | Una barra + un texto. Docling avanza por tandas, así que la barra queda quieta decenas de segundos (en la Pi, ~9 s/página según docs/14 #22) y parece colgada. No hay tiempo transcurrido ni estimado ni "última novedad". | `Processing.tsx`: solo `pct`, `etapa`, `doc_actual`; sondeo cada 1,5 s |
| Paso 2 | Misma barra para minutos de espera; no se ve qué se analiza, ni que se espera por límite de tasa (429): el auditor lo interpreta como bloqueo. | `juez.py`: el `time.sleep` por 429 no se comunica al job |
| Ambos | No se puede cancelar ni salir con confianza; no hay aviso al terminar si cambió de pestaña. | `Processing.tsx`: solo "Volver" en error |

## (b) Propuesta recomendada

Principio (NN/g): la barra de porcentaje sirve para procesos largos, pero si el avance se estanca el beneficio se pierde; conviene mostrar pasos, estimaciones con margen y evitar "Cargando…" estático. Se aplica así: **toda animación es un evento real o está rotulada como decorativa**.

1. **Selección = índice** (`seleccion-indice-v1.svg`). Callouts: 1 barra de herramientas (buscar, expandir todo, contraer, nivel N, solo marcados); 2 contador global "12 de 40 marcados"; 3 casilla tri-estado (con el símbolo, no solo color); 4 por rama: `marcados/total` y página alineada a la derecha, como un índice; 5 abierta por defecto hasta el artículo si el documento tiene ≤ 150 nodos, y hasta nivel 2 si tiene más; 6 excluidas atenuadas con motivo y enlace "Incluir"; 7 teclado según patrón ARIA tree (↑↓, →, ←, Espacio marca, `*` abre hermanos); 8 vista previa en panel fijo que no desplaza el árbol (Esc cierra). Todo sale de `ArbolDocOut` actual.
2. **Paso 1 = tira de páginas real** (`procesamiento-v1.svg`). Callouts: 1 tres etapas (Leyendo → Armando el índice → Preparando la búsqueda); 2 una celda por página: leída / lote en lectura (pulso suave) / pendiente; 3 barra con %; 4 transcurrido, estimado con rango y "última novedad hace N s" (prueba de vida con reloj local); 5 tabla de todos los documentos; 6 "Lo que vamos encontrando": conteos reales del índice ya armado (artículos, excluidas, por revisar); 7 Cancelar. **No se marcan cajas sobre el PDF**: Docling no entrega texto ni geometría hasta terminar. Se recomienda la tira de páginas porque es el evento más fino que existe; el pulso del lote en curso cubre el hueco entre tandas y no finge nada.
3. **Paso 2 = actividad real del juez** (`comparacion-v1.svg`). Callouts: 1 aviso "Esperando al servicio de IA… reanuda en 18 s" cuando hay 429; 2 Cancelar; 3 "Ahora se analizan" (hasta `LLM_CONCURRENCY` pares) con ambos fragmentos literales, página, similitud y origen; 4 "Últimos veredictos" (cobertura con icono + palabra, confianza, citas verificadas o por revisar, comentario del juez bajo demanda); 5 nota fija "no mostramos razonamiento: el modelo no lo produce"; 6 conteos provisionales por par (Total/Parcial/Nula/A revisión), rotulados como provisionales y con palabras distintas a las marcas A/L/R/X/P, que se calculan al final.

Alternativa descartada: vista en vivo del PDF con cajas resaltadas o animación "pensando" del juez. Requeriría geometría que Docling no emite hasta el final y sugeriría razonamiento inexistente (contradice "modelos reales, nada simulado").

Mejores prácticas aplicadas (resumen): progreso por etapas con significado; transparencia (qué hace el sistema, con cuántos pares, con qué texto); confianza (citas verificadas vs. por revisar siempre visibles, la IA propone y la persona decide); cancelar sin perder lo hecho; tiempo estimado con rango y solo tras la primera medición; aviso al terminar (título de pestaña); accesibilidad (WCAG 4.1.3: región `role="status"` con texto completo, `aria-atomic`, anuncios espaciados cada ~10 s o por cambio de etapa, no por cada par; `prefers-reduced-motion` desactiva el pulso; iconos y palabras junto al color; foco visible; objetivos ≥ 24 px). Patrones de GRC (AuditBoard, TeamMate+, etc.) no se consultaron en esta sesión; no se citan.

## (c) Lista priorizada

| # | Mejora | Esfuerzo | Resuelve | Backend |
|---|---|---|---|---|
| 1 | Árbol como índice: abierto hasta artículo, conteos por rama, página, buscar, expandir/contraer, solo marcados, teclado ARIA tree, chevron ≥ 24 px | S–M | Petición 1; RF Pantalla 2 de docs/05 | No |
| 2 | Paso 1: etapas + tira de páginas + transcurrido + última novedad + tabla por documento | M | Petición 2 | Sí (S) |
| 3 | Paso 2: "ahora se analizan" + últimos veredictos + conteos provisionales | M–L | Petición 3 | Sí (M) |
| 4 | Aviso "esperando al servicio de IA" (429) | S (con #3) | Explicabilidad | Sí (S) |
| 5 | Estimado de tiempo con rango | S | Ambos pasos | Se calcula en el frontend con los contadores de #2 y #3 |
| 6 | Aviso al terminar (título de pestaña, opcional `Notification`) y región `role="status"` | S | "Se desconecta" | No |
| 7 | Cancelar (paso 1: termina el subproceso; paso 2: cancela tareas) | M | Control y confianza | Sí (M) |
| Después | SSE en lugar de sondeo; miniaturas de página (render MuPDF bajo demanda); resultados parciales al cancelar | M–L | — | Sí |

## (d) Eventos nuevos del job (campos aditivos de `JobOut`)

Todo en memoria dentro del job de la sesión (regla 8). Sin llamadas extra al LLM ni a Docling.

**Procesamiento**
| Campo | Origen real | Costo |
|---|---|---|
| `por_documento: {doc_id: {etapa, paginas_hechas, paginas_total, lote: [ini, fin]}}` | callback `progreso(hechas, total)` ya existente + `DOCLING_CHUNK_PAGES` | Trivial. Latencia = una tanda de Docling (el estado no cambia dentro de una tanda) |
| `inicio_ts`, `ultimo_evento_ts` | reloj del servidor | Trivial |
| `indice: {secciones, articulos, excluidas, por_revisar}` (al terminar el seccionado) | resultado del seccionado determinista | Trivial; aparece al final de la extracción |
| `indexacion: {hechos, total}` | lotes de embeddings existentes | Trivial |
| `cancelable: bool` | — | — |

Menor latencia posible: Docling no emite por debajo de una tanda. Reducir `DOCLING_CHUNK_PAGES` da actualizaciones más frecuentes pero con más sobrecarga; medir en la Pi antes de decidir (calibración, no se cambia aquí). El resto de latencia es el sondeo de 1,5 s; SSE lo baja a ~0 pero no cambia la granularidad de Docling (no se justifica en el MVP).

**Comparación**
| Campo | Dónde se emite (`engine/juez.py`) | Costo |
|---|---|---|
| `fase`: `recuperando`/`juzgando`/`verificando`/`armando` | inicio de cada etapa | Trivial |
| `pares_total`, `pares_hechos` | ya existen (`progreso`) | — |
| `pares_en_curso[]` (máx. `LLM_CONCURRENCY`): `par_id`, `articulo{id, identificador, doc, pagina, preview≤160}`, `seccion{…}`, `score`, `origen`, `desde_ts` | al entrar al semáforo en `uno()` | Trivial; preview es texto literal del documento |
| `ultimos_veredictos[]` (anillo de 20, con `seq`): `par_id`, identificadores, `cobertura`, `naturaleza`, `confianza`, `cita_norma_ok`, `cita_manual_ok`, `requiere_revision`, `comentario≤200` | tras `juzgar_par` | ~6–10 KB por sondeo; opcional `?desde=seq` para reenviar solo lo nuevo. `comentario` es texto del modelo: mostrar solo como texto plano (riesgo aceptado, docs/14 #32) |
| `conteo_cobertura{total, parcial, nula}`, `a_revision` | acumulado en `uno()` | Trivial |
| `espera_limite{activa, hasta_ts, intento, max}` | rama 429 de `juzgar_par` (hoy un `time.sleep` silencioso) | Trivial |
| `cancelable`, `ritmo_pares_min` | — | — |

Cancelar: `POST /jobs/{id}/cancel`. Procesamiento: se termina el subproceso; los documentos ya listos se conservan. Comparación: se cancelan las tareas pendientes, pero las llamadas en vuelo (≤ 6) no son interrumpibles (`chat_json` corre en hilo) y terminan, con su costo. Los resultados parciales se descartan en el MVP.

## (e) Criterios de aceptación y medición

1. Selección: tras cargar, el auditor ve al menos un artículo (no solo títulos) sin hacer clic en ningún chevron. *Medición:* prueba con 5 auditores; 0 piden ayuda para "abrir hasta el artículo".
2. Marcar un capítulo marca todos sus artículos y la rama muestra `n/total` y estado tri-estado con símbolo. *Medición:* prueba automatizada de componente.
3. Encontrar y marcar un capítulo indicado en un documento de 100 nodos toma ≤ 30 s (con buscar). *Medición:* cronometrado, mediana de 5 usuarios.
4. Todo el árbol se opera solo con teclado y cada control mide ≥ 24 px. *Medición:* recorrido manual + axe-core.
5. Paso 1: dentro de 2 s de pulsar Procesar aparece el estado por etapa; el indicador "última novedad" nunca supera 2 × (duración del lote) sin mostrar el aviso de lote lento. *Medición:* prueba con el PDF de 55 páginas en la Pi.
6. La tira de páginas coincide con `paginas_hechas/total` del job en todo momento (sin celdas inventadas). *Medición:* prueba de componente con jobs de ejemplo.
7. Paso 2: cada elemento de "ahora se analizan" y "últimos veredictos" corresponde a un par real del job; el conteo mostrado = suma de veredictos recibidos. *Medición:* prueba de API (qa-ia) que compara `ultimos_veredictos` con `ComparacionOut` final.
8. Con un 429 real (plan gratuito de Groq y `LLM_CONCURRENCY` alto; sin dobles del modelo), el aviso aparece ≤ 3 s y desaparece al reanudar. *Medición:* prueba de integración (`-m integracion`) o ensayo manual; la prueba de componente del aviso usa un job de ejemplo, que es solo el contrato JSON.
9. Ningún texto sugiere razonamiento ("pensando…") y la nota del punto 5 está visible. *Medición:* revisión de copy.
10. Cancelar devuelve al paso anterior en ≤ 5 s sin perder marcas de selección ni documentos listos. *Medición:* prueba manual.
11. Los anuncios de lector de pantalla ocurren por cambio de etapa o cada ≥ 10 s, nunca por par. *Medición:* NVDA/VoiceOver.
12. Resultado de negocio: en sesiones de prueba, ≥ 80 % de los auditores dice qué está haciendo el sistema (cuestionario de una pregunta) y ninguno abandona la pestaña por "parece colgado". Se mide en prueba moderada, no con telemetría (no existe en el MVP).

## Decisiones para el usuario / PO
- Miniaturas de página renderizadas en servidor (MuPDF, sin guardar) y SSE: ¿entran en MVP o "después"? Propuesta: después.
- ¿Mostrar el `comentario` del juez en vivo? Es salida del modelo y el riesgo de inyección está aceptado (docs/14 #32); propuesta: sí, texto plano, bajo demanda.
- Cancelar en comparación descarta lo hecho y puede costar hasta 6 llamadas ya enviadas. ¿Se acepta?
- Aviso con `Notification` del navegador (pide permiso): ¿se acepta o solo título de pestaña?

## Fuentes consultadas
- NN/g, Progress Indicators: https://www.nngroup.com/articles/progress-indicators/
- W3C, WCAG 2.2 Understanding 4.1.3 Status Messages: https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html
- Patrón ARIA tree (APG) y las referencias GRC: no consultados en esta sesión.
