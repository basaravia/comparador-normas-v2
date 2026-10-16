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
| 2 | Sección / Artículo | Una fila por artículo: ruta completa + identificador y debajo el **texto en claro literal** extraído, en **texto enriquecido**: los fragmentos de los requisitos obligatorios **no cubiertos o cubiertos parcialmente** van en **rojo, negrita y subrayado** (brechas, docs/09 §5); el resto en negro. Lo cubierto no se resalta (auditoría no aprueba controles). Nunca generado. No se combina por sección porque una celda combinada guarda un solo texto y se perdería el literal de cada artículo (decisión del usuario, 7 oct 2026) |
| 3 | Manual interno | **Todas** las secciones del manual que respaldan algún requisito (cubierto o parcial), una por línea: identificador, requisitos que respalda (`R1, R3`) y **cita literal verificada**, sin resaltar. Vacío si la marca es R, X o P |
| 4 | Verificación | Marca codificada A / L / R / X / P, centrada, color suave por marca |
| 5 | Comentario | Por cada brecha: requisito (`R2`) y qué falta según el juez; después el razonamiento general |
| 6 | Referencias / Evidencias | Archivo y página de la norma; archivo, sección y página del manual; similitud semántica de cada sección de respaldo; aviso si la cita no se verificó |

### Reglas de formato
- Árbol en Excel: celdas **combinadas verticalmente** en col. 1 (por normativa y libro/título) cuando agrupan varios artículos; la col. 2 lleva la ruta completa en cada fila; ruta con separador `›` (ej. `Capítulo III › Sección 2 › Art. 15`) y el texto literal en la misma celda tras un salto de línea.
- Encabezado de la matriz: fondo verde institucional (`COLOR_PRIMARIO`), texto blanco, negrita. Paleta base verde y blanco, en configuración, hasta recibir el brand kit del banco.
- `wrap_text=True`, alineación superior, paneles congelados bajo el encabezado de la matriz.
- Anchos orientativos: 18 / 45 / 45 / 10 / 40 / 28.
- Colores suaves de marca (configurables): A verde, L ámbar, R rojo, X gris, P azul.
- **Entrada única al Excel también para texto enriquecido (appsec, CWE-1236):** toda celda `CellRichText` pasa por una función de `styles.py` (`escribir_enriquecido`, hermana de `escribir`) que aplica `ILLEGAL_CHARACTERS_RE` a cada tramo, trunca, fuerza `data_type="s"`, pone `quotePrefix` si el texto completo empieza por un prefijo de fórmula y descarta tramos vacíos. Sin esto, un carácter de control impide guardar el libro y un texto que empieza por `=` se evalúa al editar la celda. Los textos libres del juez (`falta`, `comentario`) también entran por `escribir`.
- **Resaltado de brechas (texto enriquecido, `openpyxl.cell.rich_text.CellRichText`, sin dependencias nuevas):** rojo (`COLOR_BRECHA`, configurable), **negrita y subrayado** para que se lea también impreso en blanco y negro o con daltonismo. Python pinta usando las posiciones verificadas de cada fragmento (docs/09 §4); un fragmento sin verificar no se pinta y la fila lleva la bandera `requiere_revision`. Nunca hay verde: lo cubierto queda en negro.
- Si una celda se trunca (32.767 caracteres), se conservan los tramos resaltados que caben y el aviso indica que hay brechas fuera del texto visible.
- Límite de Excel: 32.767 caracteres por celda → truncar con aviso `[texto truncado, ver página N]`.
- Un artículo sin resolver (tiempo o costo agotado, o par sin veredicto válido) deja la celda de marca **vacía** con la bandera `requiere_revision`; se retoma en la segunda pasada (docs/09 §5).
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
| Naturaleza / Requisitos / Confianza | Naturaleza (paso 3a), estado de cada requisito en este par, con `*` en los obligatorios (`R1* cubierto · R2* parcial · R3 no cubierto`), para que la marca se pueda derivar de la Hoja 2; y confianza |
| Elegido para el papel | `Sí` si respalda al menos un requisito **obligatorio** (cubierto o parcial); si no, `No: <motivo>` (sin requisitos cubiertos, solo requisitos enunciativos, informativo, no aplica). Un artículo puede tener **varios** pares `Sí` (usuario, 15 oct 2026; antes uno solo). En R, X y P la columna 3 del papel queda **vacía** |
| Comentario del juez | Texto completo |
| Banderas | `cita_no_verificada`, `requiere_revision`, `seccionado_incierto` |

Al final del anexo, bloque **"Vía 2 — Controles del manual sin base normativa identificada"**: las secciones sin pares con cobertura y, en las que sí tienen, el texto literal de la sección con los **fragmentos sin base** (los que ningún artículo juzgado respalda, docs/09 §5) en rojo, negrita y subrayado. Va en la Hoja 2, sin tercera hoja.
Tras ese bloque, otro **"Secciones excluidas como no comparables"** (documento, identificador, ruta, páginas y motivo) para que la exclusión quede rastreable (RNF-06).

## Borrador de conclusión
- Prompt: [`backend/prompts/conclusion.md`](../backend/prompts/conclusion.md). **1 sola llamada.**
- Entrada calculada en Python: conteos por marca, totales, artículos R y L con identificador y sus brechas (requisitos obligatorios no cubiertos o parciales, con lo que falta según el juez), controles sin base normativa, normativas y manual evaluados.
- Salida: `{"borrador_conclusion": str}`, 120–220 palabras, tono de auditoría, sin cifras distintas a las entregadas.
- Editable en la pantalla 3 antes de exportar.

## Criterios de aceptación del Excel
- Abre sin advertencias de reparación en Excel.
- Columnas en el orden exacto de la matriz; leyenda presente.
- Todo texto de norma/manual es subcadena del texto extraído (o está marcado).
- Toda brecha verificada aparece en rojo, y toda fila L o R tiene al menos un tramo en rojo o la bandera `requiere_revision`.
- La concatenación de los tramos de cada celda enriquecida es idéntica al texto saneado de la celda.
- Todo tramo en rojo corresponde a un fragmento verificado de un requisito obligatorio con estado `parcial` o `no_cubierto` (o, en el bloque vía 2, a un fragmento sin base); ningún tramo cubierto aparece resaltado.
- Conteos por marca de la Hoja 1 = conteos derivables de la Hoja 2.
- Ninguna llamada al modelo durante la generación del archivo.
