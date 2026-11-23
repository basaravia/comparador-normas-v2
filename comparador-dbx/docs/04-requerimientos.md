# 04 · Requerimientos

## Funcionales

| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-01 | Carga múltiple de PDFs en una sola zona de arrastre o selector. Se puede **volver de Selección a Carga y agregar documentos** sin perder lo procesado ni las marcas; contador «n de máximo documentos» ([14](14-puntos-abiertos.md) #37) | DEBE |
| RF-02 | Tabla con una fila por archivo: nombre, tipo (desplegable normativa/manual), metadatos opcionales editables, estado, y acciones **Quitar** y **Reintentar** (documento fallido) | DEBE |
| RF-03 | Preselección automática de tipo y metadatos desde nombre, 2 primeras páginas y metadatos nativos ([06](06-ingesta-metadatos.md)) | DEBE |
| RF-04 | Validación: solo PDF, ≤ 20 MB y ≤ 250 páginas; rechazo explícito de escaneados con mensaje de negocio | DEBE |
| RF-05 | Un único botón "Procesar": extracción + seccionado + indexación, con progreso por documento y etapa | DEBE |
| RF-06 | Seccionado flexible: Artículo, ART., Sección, SEC., numerales jerárquicos, romanos, letras, viñetas; fallback tipográfico y por longitud ([07](07-extraccion-seccionado.md)) | DEBE |
| RF-07 | Cada sección conserva texto literal, ruta jerárquica, páginas inicio/fin y bandera de seccionado incierto | DEBE |
| RF-08 | Selector dual: izquierda normativas, derecha manuales; cada panel es árbol colapsable agrupado por documento, con casillas y vista previa breve | DEBE |
| RF-09 | Marcar un nodo padre marca sus hijos; contador por panel; buscador por panel | DEBERÍA |
| RF-10 | Ejecución de la doble vía sobre la selección con progreso de pares evaluados | DEBE |
| RF-11 | Por par evaluado: marca, cita literal norma, cita literal manual, comentario y confianza | DEBE |
| RF-12 | Resultados en pantalla filtrables por marca, con vista por artículo (vía 1) o por sección del manual (vía 2) | DEBERÍA |
| RF-13 | Borrador de conclusión generado y editable antes de exportar, rotulado como propuesta | DEBE |
| RF-14 | Descarga del .xlsx con Hoja 1 (papel) y Hoja 2 (anexo técnico) ([10](10-papel-de-trabajo.md)) | DEBE |
| RF-15 | Botón "Cargar ejemplo" con documentos pre-procesados, sin ejecutar Docling | DEBE |
| RF-16 | Botón «Borrar todo y empezar de nuevo» con confirmación que indica cuántos documentos se borran | DEBERÍA |
| RF-17 | Secciones no comparables (carátula, preámbulo, índice, control de versiones, anexos…): se **identifican automáticamente**, quedan en la tabla con su motivo, **no entran** a la recuperación ni a la doble vía, y el auditor puede reincluir o excluir cualquiera (decisión del usuario, 8 oct 2026; [14](14-puntos-abiertos.md) #24) | DEBE |
| RF-19 | Panel **Ajustes** (menú de la barra superior): el auditor cambia por sesión un conjunto acotado de parámetros de búsqueda y verificación, con etiqueta de negocio, rango validado en el servidor, «Restablecer» y exportar/importar un archivo JSON para reutilizarlos. Cada comparación muestra los ajustes que usó | DEBERÍA |
| RF-20 | **Progreso en vivo**, solo con eventos reales (nada decorativo que finja razonamiento). Paso 1: etapas, una celda por página del PDF (miniatura de la página ya leída; pulso en la tanda que se está leyendo), **un solo tiempo, «Tiempo transcurrido»** (sin segundo reloj ni «última novedad»), estimado con rango tras la primera medición y los conteos reales del índice armado. Paso 2 ([ux/comparacion-en-curso-v1](ux/comparacion-en-curso-v1.md)): resumen fijo con fase, barra y contador **de pares** resueltos, el mismo tiempo transcurrido, estimado con rango solo desde `ESTIMADO_DESDE_PARES` pares resueltos y **Cancelar**; filtros-chips con el conteo por cobertura (provisional por par; las marcas A/L/R/X/P se calculan al final, por artículo); y una **lista única con una fila por par** (en análisis arriba, luego resueltos, el más reciente primero) cuyo detalle muestra la cita de la norma y la del manual, verificadas contra el texto (documento, sección y página), «Qué falta» y, plegado y como texto plano, el comentario del modelo. Los resultados nuevos no mueven la lista bajo el ojo del lector (se retienen con «Mostrar») y se pintan `PARES_POR_PAGINA` a la vez; los avisos a lector de pantalla son solo por hitos; aviso de espera cuando el proveedor limita el uso (429). Aviso al terminar en el título de la pestaña. Tras recargar la página, el avance del trabajo en curso se **recupera**, con el historial completo de pares resueltos (el servidor informa el trabajo activo) | DEBERÍA |
| RF-21 | **Cancelar** el procesamiento de documentos (se termina la lectura del PDF en curso; lo ya leído se conserva) o la comparación (no se lanzan más pares y el resultado parcial se **descarta**; la cancelación actúa en ≤ ~1 s aunque haya llamadas al modelo en vuelo, cuyos resultados se ignoran) | DEBERÍA |
| RF-22 | **Aviso de PDF no guardado:** al terminar cada procesamiento se informa que los PDF no se conservan y que lo procesado se mantiene hasta `SESSION_TTL_HOURS` sin actividad o hasta que la aplicación se reinicie; casilla «No volver a mostrar en esta sesión» (`docs/ux/aviso-pdf-no-guardado.md`) | DEBE |
| RF-23 | **Quitar un documento** (no se permite con un trabajo en curso). Si ya estaba procesado, pide confirmación y **descarta la comparación vigente** (su Excel deja de descargarse); los índices se rehacen con los documentos restantes | DEBE |
| RF-24 | **Cuenta y retención visibles** en todas las pantallas: usuario (correo o «Sesión local») y el texto de conservación con las horas reales de la configuración | DEBERÍA |
| RF-25 | **Cancelar con estado visible** (comparación): el botón «Cancelar comparación» está siempre visible en el resumen fijo; sin pares resueltos cancela sin preguntar y con ≥ 1 pide confirmación en línea indicando cuántos; tras confirmar muestra «Cancelando…» (el botón no se oculta) y lo conserva si se recarga la página (`cancelando`); si la petición falla, muestra `ERR-JOB-003` y permite reintentar. Al terminar: «Comparación cancelada. Los {N} pares resueltos no se conservan» ([14](14-puntos-abiertos.md) #39, [15](15-roadmap-v2.md) H) | DEBERÍA |

## No funcionales

| ID | Requerimiento |
|---|---|
| RNF-01 Estado | Sin volúmenes ni tablas. Estado **por usuario** (sesión) en memoria y `/tmp`; retención de **48 h** de inactividad o hasta reiniciar. El **PDF se borra al terminar con éxito su procesamiento**; solo se conserva si falla o se cancela. El Excel descargado es la persistencia |
| RNF-02 Cómputo | Extracción en cola de 1 worker. Hilos OMP/torch acotados por config. Cada PDF se extrae una vez por sesión (caché SHA-256) |
| RNF-03 Concurrencia LLM | Llamadas concurrentes con semáforo (inicial 6) `[CALIBRAR]`; reintentos con backoff exponencial ante 429/5xx |
| RNF-04 Progreso | Toda operación > 2 s expone etapa, documento, contador y porcentaje; en la comparación el porcentaje y la barra son **de pares resueltos**, no una mezcla de fases. Polling cada 1,5 s |
| RNF-05 Errores | Mensajes de negocio en pantalla; trazas a logs con código de error correlacionable |
| RNF-06 Trazabilidad | Cada fila del papel se rastrea a archivo, página y sección; el anexo registra todos los candidatos, scores y descartes |
| RNF-07 Literalidad | Textos siempre extraídos, nunca generados; citas verificadas en código |
| RNF-08 Costo | Excel y agregación sin tokens. Cada par se juzga una vez |
| RNF-09 Usabilidad | Máximo 3 pantallas de interacción; metadatos opcionales; único campo obligatorio: tipo |
| RNF-10 Resiliencia de demo | Ejemplos precargados disponibles aunque Docling o el contenedor estén lentos |
| RNF-11 Rendimiento | 100 páginas extraídas en minutos; el tope de 250 páginas puede tardar hasta `DOCLING_TIMEOUT_S` (3000 s; ≈ 39 min en la Raspberry, sin medir en Databricks) `[CALIBRAR]`; 50×40 secciones comparadas en < 15 min `[CALIBRAR]` |
| RNF-12 Seguridad | Autenticación de Databricks Apps; sin credenciales en código; los documentos solo salen hacia el gateway. **Identidad:** con `TRUST_PROXY_IDENTITY` la sesión se liga al correo de `x-forwarded-email`; el correo solo existe como hash SHA-256 en memoria y **nunca va a logs**, errores ni nombres de carpeta; sin identidad válida → 401. Las solicitudes que cambian estado rechazan `Sec-Fetch-Site` de otro origen |
