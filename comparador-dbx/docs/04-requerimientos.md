# 04 · Requerimientos

## Funcionales

| ID | Requerimiento | Prioridad |
|---|---|---|
| RF-01 | Carga múltiple de PDFs en una sola zona de arrastre o selector | DEBE |
| RF-02 | Tabla con una fila por archivo: nombre, tipo (desplegable normativa/manual), metadatos opcionales editables, estado | DEBE |
| RF-03 | Preselección automática de tipo y metadatos desde nombre, 2 primeras páginas y metadatos nativos ([06](06-ingesta-metadatos.md)) | DEBE |
| RF-04 | Validación: solo PDF, ≤ 20 MB y ≤ 100 páginas; rechazo explícito de escaneados con mensaje de negocio | DEBE |
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
| RF-16 | Botón "Nueva sesión" con confirmación | DEBERÍA |

## No funcionales

| ID | Requerimiento |
|---|---|
| RNF-01 Estado | Sin volúmenes ni tablas. Estado por sesión en memoria y `/tmp`. El Excel descargado es la persistencia |
| RNF-02 Cómputo | Extracción en cola de 1 worker. Hilos OMP/torch acotados por config. Cada PDF se extrae una vez por sesión (caché SHA-256) |
| RNF-03 Concurrencia LLM | Llamadas concurrentes con semáforo (inicial 6) `[CALIBRAR]`; reintentos con backoff exponencial ante 429/5xx |
| RNF-04 Progreso | Toda operación > 2 s expone etapa, documento, contador y porcentaje. Polling cada 1,5 s |
| RNF-05 Errores | Mensajes de negocio en pantalla; trazas a logs con código de error correlacionable |
| RNF-06 Trazabilidad | Cada fila del papel se rastrea a archivo, página y sección; el anexo registra todos los candidatos, scores y descartes |
| RNF-07 Literalidad | Textos siempre extraídos, nunca generados; citas verificadas en código |
| RNF-08 Costo | Excel y agregación sin tokens. Cada par se juzga una vez |
| RNF-09 Usabilidad | Máximo 3 pantallas de interacción; metadatos opcionales; único campo obligatorio: tipo |
| RNF-10 Resiliencia de demo | Ejemplos precargados disponibles aunque Docling o el contenedor estén lentos |
| RNF-11 Rendimiento | 100 páginas extraídas en minutos; 50×40 secciones comparadas en < 15 min `[CALIBRAR]` |
| RNF-12 Seguridad | Autenticación de Databricks Apps; sin credenciales en código; los documentos solo salen hacia el gateway |
