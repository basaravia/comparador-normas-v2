# 10 · Papel de trabajo (salida Excel)

Es el **entregable de auditoría** y debe respetar el formato del banco.
- Generado **100 % en Python** con pandas + openpyxl. **Cero tokens.** El modelo no interviene en el formato.
- Las **etiquetas** del encabezado son estándar y van fijas en la plantilla. Los **valores** se prellenan cuando hay metadatos; si no, quedan en blanco para el auditor.

## Hoja 1 — "Papel de trabajo"

### Encabezado (de arriba hacia abajo)
| Campo | Valor |
|---|---|
| Nombre de la revisión | En blanco; lo llena el auditor |
| Nombre del papel de trabajo | Plantilla: "Evaluación de cumplimiento normativo — {manual}" |
| Objetivo | Texto estándar, editable por el auditor: «Evaluar el cumplimiento de la normativa regulatoria aplicable por parte del manual de control interno de la entidad, identificando brechas y evidencia de respaldo en ambas vías (norma → manual y manual → norma).» (aprobado por el usuario, 7 oct 2026; se cambia cuando el banco entregue su plantilla) |
| Corte o periodo | En blanco; lo llena el auditor |
| Fuente | Libro, título y capítulo de cada normativa analizada **versus** el manual analizado |
| Marcas de verificación | Leyenda fija (ver abajo) |
| Conclusiones | Borrador editado en pantalla 3; si no se editó, prefijo "[Borrador generado automáticamente — validar]" |
| Elaborado por | En blanco |
| Revisado por | En blanco |
| Fecha de ejecución | Fecha de generación, editable |

### Leyenda de marcas (fija)
| Código | Significado |
|---|---|
| **A** | Sí cumple |
| **R** | No cumple |
| **X** | No aplica |
| **L** | Parcialmente |
| **P** | Información obtenida de la normativa |

### Matriz de detalle — una fila por artículo evaluado
| # | Columna | Contenido |
|---|---|---|
| 1 | Nombre de la normativa | Libro, capítulo, norma: identificación de la fuente |
| 2 | Sección / Artículo | Una fila por artículo: ruta completa + identificador y debajo el **texto en claro literal** extraído. Nunca generado. No se combina por sección porque una celda combinada guarda un solo texto y se perdería el literal de cada artículo (decisión del usuario, 7 oct 2026) |
| 3 | Manual interno | Sección del manual de respaldo (1) con identificador y **cita literal verificada**. Vacío si la marca es R, X o P |
| 4 | Verificación | Marca codificada A / L / R / X / P, centrada, color suave por marca |
| 5 | Comentario | Razonamiento del juez: por qué la evidencia satisface la obligación o qué elementos faltan |
| 6 | Referencias / Evidencias | Archivo y página de la norma; archivo, sección y página del manual; similitud semántica del candidato elegido; aviso si la cita no se verificó |

### Reglas de formato
- Árbol en Excel: celdas **combinadas verticalmente** en col. 1 (por normativa y libro/título) cuando agrupan varios artículos; la col. 2 lleva la ruta completa en cada fila; ruta con separador `›` (ej. `Capítulo III › Sección 2 › Art. 15`) y el texto literal en la misma celda tras un salto de línea.
- Encabezado de la matriz: fondo verde institucional (`COLOR_PRIMARIO`), texto blanco, negrita. Paleta base verde y blanco, en configuración, hasta recibir el brand kit del banco.
- `wrap_text=True`, alineación superior, paneles congelados bajo el encabezado de la matriz.
- Anchos orientativos: 18 / 45 / 45 / 10 / 40 / 28.
- Colores suaves de marca (configurables): A verde, L ámbar, R rojo, X gris, P azul.
- Límite de Excel: 32.767 caracteres por celda → truncar con aviso `[texto truncado, ver página N]`.
- Orden de filas: el orden del documento normativo (no por marca).

## Hoja 2 — "Anexo técnico"
Registra **todo** candidato evaluado. Defiende ante el regulador que no hubo selección sesgada de evidencia y sirve para calibrar el recall.

| Columna | Contenido |
|---|---|
| ID par | Identificador estable |
| Artículo | id, identificador, documento |
| Sección manual | id, identificador, documento |
| Origen | v1, v2 o ambas |
| Similitud v1 / v2 / máxima | Scores coseno |
| Rango v1 / v2 | Posición en el top-K de cada vía |
| Naturaleza / Cobertura / Confianza | Salida del juez |
| Elegido para el papel | `Sí` o `No: <motivo>` (cobertura menor, confianza menor, cobertura nula, informativo, no aplica). Solo A y L tienen un par `Sí`; en R, X y P la columna 3 del papel queda **vacía** (decisión del usuario, 7 oct 2026) |
| Comentario del juez | Texto completo |
| Banderas | `cita_no_verificada`, `requiere_revision`, `seccionado_incierto` |

Al final del anexo, bloque **"Vía 2 — Controles del manual sin base normativa identificada"** con las secciones del manual sin pares con cobertura. Va en la Hoja 2, sin tercera hoja.

## Borrador de conclusión
- Prompt: [`backend/prompts/conclusion.md`](../backend/prompts/conclusion.md). **1 sola llamada.**
- Entrada calculada en Python: conteos por marca, totales, artículos R y L con identificador y `elementos_faltantes`, controles sin base normativa, normativas y manual evaluados.
- Salida: `{"borrador_conclusion": str}`, 120–220 palabras, tono de auditoría, sin cifras distintas a las entregadas.
- Editable en la pantalla 3 antes de exportar.

## Criterios de aceptación del Excel
- Abre sin advertencias de reparación en Excel.
- Columnas en el orden exacto de la matriz; leyenda presente.
- Todo texto de norma/manual es subcadena del texto extraído (o está marcado).
- Conteos por marca de la Hoja 1 = conteos derivables de la Hoja 2.
- Ninguna llamada al modelo durante la generación del archivo.
