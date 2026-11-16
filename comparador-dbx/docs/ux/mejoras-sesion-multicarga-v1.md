# UX · Sesión por usuario, PDF efímero y carga múltiple: mejoras (v1)

Nada implementado. Basado en lectura de código (rama `feat/sesion-usuario-pdf-efimero`): `App.tsx`, `pages/*`, `components/DocTable.tsx`, `DropZone.tsx`, `reductor.ts`, `arbol.ts`, `api.ts`, `backend/api/rutas.py`, `core/sesiones.py`, `engine/servicio.py`. No se corrió la app ni se consultaron fuentes externas en esta sesión. Respeta las 6 decisiones aprobadas y los textos de `aviso-pdf-no-guardado.md`; lo que choca con ellas está en §7.

## 1. Recorrido del auditor (qué espera · qué ve hoy · dónde tropieza)

| Paso | Espera | Hoy (evidencia) | Tropiezo |
|---|---|---|---|
| Llegada | Saber con qué cuenta entra y qué pasa con sus archivos | Cabecera sin usuario ni retención (`App.tsx`); `SesionOut` solo trae `documentos` y `comparacion_id` | No sabe si lo de ayer sigue ahí ni por cuánto tiempo |
| Llegada con cookie vieja | Empezar de nuevo sin más | `sesion_actual` responde 410 a toda petición; solo `DELETE /session` borra la cookie. El banner dice "Vuelve a cargarlos o usa el ejemplo" y ambas acciones vuelven a fallar | Queda trabado; la única salida ("Reiniciar sesión") no se menciona |
| Carga | Arrastrar, corregir si se equivocó | `DropZone` descarta en silencio lo que no es PDF; no hay "Quitar"; un PDF fallido ocupa cupo (`len(s.docs)`); el tope se avisa después de subir 20 MB | Sube el PDF equivocado y solo puede "Reiniciar sesión" (que borra todo sin confirmar) |
| Carga · ejemplo | Probar sin riesgo | `Upload.tsx` reemplaza la lista local por solo los 2 documentos de ejemplo aunque el servidor conserva los demás; `cargar_ejemplo` no valida el tope y duplica al repetir | La lista en pantalla no coincide con lo que hay; reaparece al recargar |
| Procesamiento (200 pág. ≈ 30 min; peor caso 8 × 250 pág. ≈ 5 h) | Irse a una reunión y encontrarlo listo | Avance vivo y aviso en el título de la pestaña. Pero el id del trabajo vive solo en React | F5 o cerrar pestaña: vuelve a Carga con filas "Extrayendo" y el botón **Procesar activo**; `servicio.procesar` no impide un segundo trabajo sobre los mismos documentos (doble proceso) |
| Procesamiento · servidor reiniciado con la pestaña abierta | Que le avisen | `Processing.tsx` solo trata el 410; un `ERR-JOB-404` o un corte de red se tragan | Barra congelada indefinidamente |
| Procesamiento · falla un documento | Reintentar | `Upload.tsx` excluye los de estado `error` de "Procesar"; no hay reintento | El PDF que la decisión 1 conserva "por si falla" no sirve para nada: hay que volver a subirlo y sigue ocupando cupo |
| Aviso (decisión 2) | Verlo al terminar | Solo se dispararía en la transición vista por `Processing.tsx` | Si terminó mientras estaba fuera y vuelve por recarga, entra directo a Selección sin aviso (incumple su criterio 1) |
| Selección | Marcar y comparar | Con dos manuales, ambos llegan preseleccionados (`seleccionInicial`); el pie dice "de 2 manuales" sin alerta; al pulsar Comparar sale ERR-CMP-003 | Error tardío. Además el aviso aprobado dice "los documentos nuevos llegan sin marcar" y el código los preselecciona |
| Selección · F5 / otro navegador | Conservar sus marcas | `e.seleccion` vive en React; al recargar todo documento es "nuevo" y vuelve la preselección | Pierde 20 minutos de marcado sin aviso |
| Agregar documentos | Volver sin perder nada | "1 · Carga" en la cabecera funciona y conserva marcas en la misma pestaña; no hay botón explícito | No lo descubre; teme perder lo hecho |
| Comparación | Dejarla corriendo | Igual que procesamiento: tras F5 vuelve a Selección (o a un resultado anterior); Comparar da ERR-CMP-007 "Ya hay una comparación en curso" sin forma de verla | Trabado hasta que termine, sin avance visible |
| Resultados | Descargar; probar otra selección | Solo "Guardar conclusión" y "Descargar". Volver es por la cabecera. La comparación nueva reemplaza la visible | No sabe cómo seguir ni que el resultado anterior se pierde de vista |
| Descarga | Un Excel | Enlace directo (`<a download>`); si la sesión ya no existe, baja o abre un error | Cree que descargó el papel de trabajo |
| Día siguiente | Encontrar todo | Con decisión 4, documentos y última comparación vuelven; marcas y conclusión sin guardar, no | No distingue "vacío porque es nuevo" de "se perdió" |
| Expiración / reinicio | Mensaje claro | Con sesión por correo ya no hay 410: la lista simplemente aparece vacía | Pérdida silenciosa |
| Dos pestañas o dos navegadores | Ver lo mismo | Cada pestaña guarda su copia; nada la refresca | Lista y estado desfasados; segundo trabajo en paralelo |

Problemas a–g del encargo: **todos confirmados**. Precisiones: (a) es más grave de lo descrito (permite doble procesamiento); (e) desaparece al implementar la decisión 4, pero lo reemplaza la pérdida silenciosa; (f) la navegación existe en la cabecera, falta hacerla evidente.

## 2. Hallazgos priorizados

Esfuerzo S ≤ medio día, M 1–2 días, L más. "Backend" = requiere cambio en la API.

### Imprescindible

| ID | Problema | Solución | Esf. | Backend |
|---|---|---|---|---|
| I-1 | Recargar o volver pierde el avance y permite doble proceso (a) | `GET /session` informa el trabajo activo; al abrir, la app se reengancha a la vista de avance. El servidor rechaza un segundo trabajo mientras haya uno activo | M | Sí: `trabajo_activo {id, tipo}` en `SesionOut`; guarda "un trabajo a la vez por sesión" |
| I-2 | Pérdida silenciosa por expiración o reinicio; barra congelada (e) | Estados de §4. El navegador recuerda (localStorage) "tenía N documentos, última actividad"; si el servidor devuelve vacío, muestra el mensaje que corresponda. En avance: `ERR-JOB-404` = sesión perdida; corte de red = aviso de reintento | S–M | No (opcional: `retencion_horas` de I-6) |
| I-3 | No se puede quitar ni reintentar; los fallidos ocupan cupo (b) | Acción "Quitar" por fila (cualquier estado salvo en proceso) y "Reintentar" en los fallidos. Los fallidos no cuentan para el tope | M | Sí: `DELETE /documents/{id}` (invalida índices); permitir reprocesar `error`; tope cuenta solo no fallidos |
| I-4 | "Reiniciar sesión" borra todo sin confirmar (c) | Renombrar a "Borrar todo y empezar de nuevo", con confirmación; separarlo visualmente de "Cargar ejemplo" | S | No |
| I-5 | Dos manuales preseleccionados; error tardío (d) | Un solo manual activo: al marcar secciones de un manual, el otro queda sin marcas (tras confirmar si tenía). Los manuales nuevos llegan sin marcar si ya hay uno con marcas. Aviso en el panel, no al pulsar Comparar | M | No |
| I-6 | No ve cuenta ni retención (g) | Una línea fija (§5) | S | Sí: `usuario` y `retencion_horas` en `SesionOut` |
| I-7 | El aviso de PDF no guardado se salta si el proceso terminó sin la persona delante | Al abrir, si hay documentos procesados aún no avisados (lista de ids avisados en localStorage), mostrar el diálogo aprobado antes de Selección | S | No |

### Importante

| ID | Problema | Solución | Esf. | Backend |
|---|---|---|---|---|
| P-1 | Las marcas de selección se pierden al recargar o al día siguiente | Guardar las marcas en el navegador (localStorage, ligadas al usuario y al inicio de sesión del servidor para no aplicarlas a documentos distintos). En otro navegador no viajan: decirlo | S–M | Sí, mínimo: `sesion_iniciada_ts` en `SesionOut` |
| P-2 | Desde Resultados no es claro cómo seguir (f) | Dos botones secundarios junto a Descargar + nota de reemplazo | S | No |
| P-3 | Descarga que falla en silencio | Descargar con verificación previa; si falla, mensaje de §4 | S | No |
| P-4 | Tope avisado tarde; lote rechazado entero | Contador "N de 8" en Carga; zona de carga desactivada al llegar al tope; si el lote excede, decir cuántos caben | S | Sí, mínimo: `max_documentos` en `SesionOut` (o constante) |
| P-5 | Archivos no PDF descartados sin aviso | Mensaje con los nombres omitidos | S | No |
| P-6 | Dos pestañas/navegadores desfasados (más frecuente con decisión 4) | Al volver a la pestaña (`visibilitychange`), refrescar `GET /session`; con I-1 la segunda pestaña ve el avance en vez de lanzar otro trabajo | S | No (usa I-1) |
| P-7 | Sin botón "Agregar documentos" (decisión 3; ya previsto en el aviso aprobado) | Botón en pie y franja de Selección; al volver, mensaje de marcas conservadas | S | No |
| P-8 | "Cargar ejemplo" desordena la lista y se duplica | Tras cargarlo, refrescar la lista completa; ocultar el botón si el ejemplo ya está o si hay documentos propios (ofrecerlo solo en estado vacío) | S | Sí, mínimo: validar tope y duplicado |

### Deseable

| ID | Problema | Solución | Esf. | Backend |
|---|---|---|---|---|
| D-1 | Cancelar por error un proceso de 30 min | Confirmar solo si lleva más de 1 minuto: "¿Cancelar el procesamiento? Los documentos ya leídos se conservan; el que está en curso se pierde." Botones: **Sí, cancelar** / **Seguir procesando** | S | No |
| D-2 | Mismo PDF subido dos veces | Aviso en la fila: "Este archivo ya está en la lista." (hay `sha256`) | S | Sí |
| D-3 | Conclusión sin guardar se pierde al navegar | Guardado automático al salir del campo, con "Guardado" discreto | S | No |
| D-4 | Estimación al irse a la reunión | En el avance: "Puedes cerrar esta pestaña; el proceso sigue. Vuelve a entrar con tu cuenta para ver el resultado." (solo válido con I-1 y decisión 4) | S | No |
| D-5 | Tipo equivocado tras procesar (ERR-DOC-003 manda a reiniciar) | Cambiar el texto a: "Este documento ya se procesó. Para cambiar su tipo, quítalo y cárgalo de nuevo." | S | Sí (texto) |

## 3. Textos exactos

**I-1 Reenganche.** Al abrir con trabajo activo se entra directo a la vista de avance, con una línea arriba: "Este proceso sigue en marcha desde antes. Puedes esperar aquí o volver más tarde." Si se intenta lanzar otro (otra pestaña): "Ya hay un proceso en marcha con tu cuenta. Espera a que termine." + botón **Ver avance**. En Carga, mientras haya trabajo activo, "Procesar" se reemplaza por **Ver avance**.

**I-3 Quitar / Reintentar.**
- Botón de fila: **Quitar**. Documento sin procesar o fallido: se quita sin confirmar, con aviso breve "Se quitó «{nombre}»." 
- Documento ya procesado: confirmación. Título: "¿Quitar «{nombre}»?" Cuerpo: "Se borrará su contenido preparado y las marcas que hiciste en él. Si lo necesitas después, tendrás que cargarlo y procesarlo de nuevo (el PDF no está guardado aquí)." Botones: **Quitar documento** / **Cancelar** (foco inicial en Cancelar).
- Si el documento participa en el resultado visible: añadir "El resultado actual no cambia, pero ya no podrás repetir la comparación con este documento."
- Fila fallida: **Reintentar** · **Quitar**. Nota bajo el error: "Este documento no cuenta para el máximo de {max}."
- Durante un proceso: "Quitar" desactivado, con ayuda "Espera a que termine el proceso o cancélalo."

**I-4 Borrar todo.** Enlace: **Borrar todo y empezar de nuevo**. Diálogo (`role="alertdialog"`): título "¿Borrar todo y empezar de nuevo?" Cuerpo: "Se borrarán tus {n} documentos, tus marcas de selección y el resultado de la comparación, en todos tus dispositivos. No se puede deshacer." Si hay resultado: "Si aún no lo hiciste, descarga antes el papel de trabajo." Botones: **Sí, borrar todo** / **Cancelar** (foco inicial en Cancelar; Esc = Cancelar). Si hay un proceso activo, el enlace está desactivado: "Cancela el proceso en curso antes de borrar."

**I-5 Un solo manual.**
- Nota fija bajo el título "Manuales de control" cuando hay más de uno: "La comparación usa un manual a la vez. Elige en cuál trabajar."
- Cada manual se muestra con un selector de opción única ("Usar este manual"); el no elegido queda plegado con el rótulo "No se usará en esta comparación".
- Al cambiar de manual teniendo marcas: "¿Cambiar a «{manual}»? Se quitarán las {n} marcas de «{anterior}»." Botones: **Cambiar de manual** / **Cancelar**.
- Pie: "Vas a comparar {a} artículos de {n} normativas contra {s} secciones de «{manual}»."

**I-7 Aviso pendiente.** Mismo diálogo aprobado, sin cambiar sus textos; la lista muestra los documentos procesados aún no avisados.

**P-1 Marcas.** Al restaurar: "Recuperamos tus {n} marcas de la última vez." Si no hay marcas guardadas y sí documentos (otro navegador): "Tus documentos siguen aquí. Las marcas de selección se guardan en cada navegador: revisa la selección propuesta."

**P-2 Resultados.** Botones: **Cambiar la selección y comparar de nuevo** · **Agregar documentos**. Nota junto a Descargar: "Al comparar de nuevo, este resultado se reemplaza. Lo único que se conserva es el papel de trabajo que descargues."

**P-4 Tope.** Contador en Carga: "{n} de {max} documentos". Lote que excede: "Solo caben {k} documentos más (máximo {max}). No se agregó ninguno; elige hasta {k} o quita alguno de la lista."

**P-5.** "Solo se aceptan archivos PDF. No se agregó: {nombres}."

**P-7.** Al volver a Selección tras agregar: "Se conservaron tus {n} marcas." y, según I-5, "«{manual nuevo}» llegó sin marcar porque ya trabajas con «{manual}»." (ver §7 sobre "llegan sin marcar").

## 4. Estados vacíos y de error clave

| Estado | Cómo se detecta | Texto | Acción |
|---|---|---|---|
| Primera vez (vacío) | Sin documentos y sin recuerdo local | Solo la zona de carga y la línea de §5 | **Cargar ejemplo** como secundaria |
| Sesión expirada (48 h) | Servidor vacío; recuerdo local con documentos y última actividad hace más de 48 h | Título: "Tus documentos se borraron por inactividad". Cuerpo: "Pasaron más de 48 horas sin uso y, por seguridad, se borraron tus documentos procesados y el resultado. Los papeles de trabajo que descargaste no cambian. Para seguir, carga de nuevo tus PDF." | **Entendido** (cierra y borra el recuerdo). Código: ERR-SES-003 |
| Servidor reiniciado | Servidor vacío; recuerdo local con actividad hace menos de 48 h y sin "borrar todo" propio; o `ERR-JOB-404` / `ERR-CMP-404` en una vista abierta | Título: "Se perdió lo que tenías cargado". Cuerpo: "La aplicación se reinició y no guarda copias: tus documentos procesados, tus marcas y el resultado que no hayas descargado ya no están. No fue por algo que hiciste. Para seguir, carga de nuevo tus PDF originales y vuelve a procesarlos." Si había un proceso en marcha: "El proceso que estaba en curso también se detuvo." | **Cargar documentos de nuevo** (va a Carga, foco en la zona de carga). Código: ERR-SES-001 |
| Sin conexión durante el avance | Fallo de red en el sondeo (3 seguidos) | "No logramos consultar el avance. Seguimos intentando; el proceso continúa en el servidor." | Automático; desaparece al reconectar |
| Tope alcanzado | n = max | Zona de carga desactivada: "Llegaste al máximo de {max} documentos. Quita alguno de la lista para agregar otro." | **Quitar** en cada fila (I-3). Código: ERR-ING-004 (cambiar su texto actual, que manda a reiniciar la sesión) |
| PDF ya no disponible | Documento procesado (sin archivo) | Estado de fila ya aprobado: "Indexado · PDF no guardado". Si se pide algo que requiere el archivo (miniatura, reprocesar): "El PDF de «{nombre}» ya no está en la aplicación; solo se conserva su contenido preparado. Si necesitas procesarlo otra vez, cárgalo de nuevo desde tu equipo." | Ninguna acción de abrir o descargar PDF. Código: ERR-DOC-001 |
| Descarga imposible | P-3 falla | "No pudimos generar el papel de trabajo porque el resultado ya no está disponible. Tendrás que cargar los documentos y comparar de nuevo." | **Ir a Carga** |
| Servicio lleno | ERR-SES-002 | Mantener texto actual, pero ver §7 (con 48 h "unos minutos" puede no ser cierto) | Reintentar |

Reglas comunes: banner con `role="alert"` en errores y `role="status"` en avisos; icono + texto (no solo color); el rojo se reserva para brechas (RF-18), estos estados usan el estilo de aviso; código corto al final; sin trazas.

## 5. Cuenta y retención: una línea

Bajo la cabecera, en todas las pantallas, texto pequeño y neutro (no banner):

> **{correo}** · Tus documentos procesados se conservan 48 horas desde tu último uso. Los PDF no se guardan.

- En local/sin correo: "Sesión de este navegador · …" (mismo resto).
- No lleva cuenta regresiva ni fecha: evita ruido y promesas falsas (un reinicio borra antes). El detalle va en un "?" accesible: "Si la aplicación se reinicia, se pierde todo antes de ese plazo. Lo único permanente es el papel de trabajo que descargues."
- Sustituye a la franja de Selección del aviso aprobado solo si el PO lo acepta; si no, conviven (la franja mantiene "Ver aviso" y "Agregar documentos").

## 6. Criterios de aceptación

**I-1** (1) Con un procesamiento en curso, F5 muestra la vista de avance en ≤ 3 s, con el porcentaje real. (2) Lo mismo con una comparación. (3) Cerrar la pestaña, abrir otra con la misma cuenta: se ve el avance o, si terminó, el resultado del paso. (4) Con trabajo activo no existe en ninguna pantalla un botón habilitado que lance otro; por API el segundo intento devuelve error de negocio y ningún documento se procesa dos veces. (5) Al terminar un trabajo reenganchado se cumple el flujo normal (aviso, Selección o Resultados).

**I-2** (1) Tras reiniciar el servidor, quien tenía documentos ve "Se perdió lo que tenías cargado" al abrir, no una lista vacía muda. (2) Con más de 48 h de inactividad ve el mensaje de expiración. (3) Tras "Borrar todo" propio no aparece ninguno de los dos. (4) Con la vista de avance abierta y el servidor reiniciado, en ≤ 10 s aparece el estado de reinicio; la barra no queda congelada. (5) Desde cualquiera de esos estados, subir un PDF funciona al primer intento (no se repite el error). (6) Ningún mensaje contiene "sesión 410", "cookie" ni trazas.

**I-3** (1) Un documento cargado, fallido o procesado se puede quitar desde su fila con teclado. (2) Quitar uno procesado pide confirmación con foco en Cancelar; quitar uno sin procesar no. (3) Tras quitar, el contador baja y el documento desaparece de Carga y de Selección; las marcas de los demás se conservan. (4) Con 8 documentos, uno fallido, se puede subir uno más. (5) "Reintentar" en un fallido lo procesa sin volver a subirlo. (6) Tras quitar un documento procesado, una comparación nueva no lo usa como respaldo ni lo cita.

**I-4** (1) Ningún clic único borra la sesión. (2) El diálogo indica cuántos documentos se borran y que afecta a todos los dispositivos. (3) Esc y Cancelar no borran nada. (4) Con resultado sin descargar aparece la frase de descarga. (5) El enlace no queda contiguo a "Cargar ejemplo" ni comparte estilo con el botón primario.

**I-5** (1) Con dos manuales procesados, al entrar a Selección solo uno tiene marcas y se ve la nota. (2) Es imposible llegar a ERR-CMP-003 desde la interfaz. (3) Cambiar de manual con marcas pide confirmación y conserva las marcas de las normativas. (4) El pie nombra el manual que se usará. (5) Agregar un segundo manual no altera las marcas del primero.

**I-6** (1) La línea se ve en las cinco pantallas sin desplazar. (2) Muestra el correo real de la cuenta. (3) El plazo sale de la configuración del servidor, no de un texto fijo. (4) Contraste AA; se lee con lector de pantalla una vez, no en cada actualización.

**I-7** (1) Si un procesamiento termina con la pestaña cerrada, al volver aparece el diálogo aprobado antes de Selección con esos documentos. (2) Una vez confirmado no reaparece para los mismos documentos en ese navegador. (3) Se cumplen los 8 criterios de `aviso-pdf-no-guardado.md`.

**P-1** (1) Con 12 marcas, F5 las conserva y muestra "Recuperamos tus 12 marcas". (2) Tras reinicio del servidor no se aplican marcas viejas a documentos nuevos. (3) En otro navegador aparece el texto que explica que las marcas no viajan.
**P-2** (1) Desde Resultados se llega a Selección con las marcas intactas en un clic. (2) La nota de reemplazo es visible junto a Descargar.
**P-3** (1) Con el resultado ya inexistente, pulsar Descargar muestra el mensaje y no baja ningún archivo. (2) En el caso normal baja `papel_de_trabajo.xlsx` igual que hoy.
**P-4** (1) El contador coincide con la lista. (2) En el tope no se puede iniciar una subida. (3) Un lote que excede informa cuántos caben antes de enviar los archivos.
**P-5** (1) Soltar un .docx junto a un PDF agrega el PDF y nombra el archivo omitido.
**P-6** (1) Con dos pestañas, lo hecho en una se refleja en la otra al volver a ella, sin recargar.
**P-7** (1) Criterio 5 del aviso aprobado. (2) El botón existe en el pie de Selección y en Resultados.
**P-8** (1) Tras "Cargar ejemplo" con documentos propios, la lista muestra todos. (2) No se puede cargar el ejemplo dos veces.

## 7. Choques con las decisiones aprobadas (para el usuario / PO)

1. **Decisión 1 vs. reintento.** Conservar el PDF "si falla" hoy no sirve: la interfaz no permite reintentar un fallido. O se implementa "Reintentar" (I-3) o conviene borrar también el fallido. Además, un PDF fallido o cancelado puede quedar hasta 48 h en el servidor: confirmar con appsec que es aceptable o borrarlo antes (por ejemplo, al quitarlo o a las pocas horas).
2. **Decisión 2, texto del aviso.** "…mientras la aplicación siga abierta" se lee como "mientras no cierre la pestaña", lo contrario de las decisiones 4 y 5; y no menciona las 48 horas. No se cambió el texto (está aprobado). Propuesta para decidir: "…durante 48 horas desde tu último uso, o hasta que la aplicación se reinicie."
3. **Decisión 2, casilla "No volver a mostrar en esta sesión".** Con sesión por usuario, "sesión" ya no es la pestaña. La preferencia seguiría por pestaña (`sessionStorage`); decidir si el rótulo pasa a "…en esta pestaña" o si la preferencia dura lo que dura la sesión del usuario.
4. **Aviso aprobado vs. código.** El aviso afirma "Los documentos nuevos llegan sin marcar"; `seleccionTrasRecarga` les aplica la preselección propuesta. Decidir cuál vale. Recomendación: normativas nuevas con la preselección propuesta (rotulada "propuesta"), manuales nuevos sin marcar si ya hay uno en uso (I-5), y ajustar el mensaje.
5. **Decisiones 3 y 4 vs. marcas.** "Recupera sus documentos" no incluye las marcas de selección ni la conclusión sin guardar: viven en el navegador. Sin P-1, cerrar la pestaña las pierde; con P-1 no viajan entre navegadores. Guardarlas en el servidor (memoria) es posible pero amplía la API: decisión de alcance.
6. **Decisión 5 vs. capacidad.** Con 48 h de retención las sesiones se acumulan; al llegar a `MAX_SESIONES`, ERR-SES-002 promete "unos minutos" y puede tardar horas. Revisar el tope y la memoria con el equipo técnico, y el texto si no cambia el tope.
7. **Decisión 4, simultaneidad.** La misma cuenta en dos pestañas o navegadores comparte todo: I-1 y P-6 dejan de ser comodidad y pasan a ser necesarios para no duplicar trabajos.
8. Pendiente de PO: código ERR-SES-003 nuevo; si la línea de §5 reemplaza a la franja de Selección; si "Cargar ejemplo" se oculta cuando hay documentos propios.

## 8. Qué NO hacer

- **Reanudar o "guardar el proyecto"** en el servidor, historial de comparaciones, "mis documentos": no hay base de datos; prometerlo es mentir tras un reinicio.
- **Cuenta regresiva de expiración** o "se borra el día X a las HH:MM": un reinicio borra antes; un plazo exacto es una promesa falsa.
- **Avisar por correo o notificación del navegador** cuando termina: servicio nuevo, permisos, y el título de pestaña ya cubre el caso.
- **Ver o descargar el PDF, miniaturas en Selección o Resultados, resaltar sobre la página**: después de procesar no hay PDF (decisiones 1 y 6). La evidencia es el texto literal con documento, sección y página.
- **Guardar el PDF en el navegador** (IndexedDB) para "recuperarlo": contradice el espíritu de no retener el archivo y complica el código.
- **Papelera o "deshacer" al quitar o borrar todo**: exige conservar lo borrado. La confirmación previa es suficiente.
- **Varias comparaciones a la vez, cola de comparaciones o comparar contra varios manuales en un clic**: un solo proceso, una comparación y un manual por vez.
- **Subir en segundo plano mientras se procesa** o reemplazar un documento en caliente: los índices se reconstruyen; mantener "un trabajo a la vez".
- **Renovar la sesión con un sondeo permanente** de una pestaña olvidada: anula la retención de 48 h. Solo cuenta el uso real y el sondeo de un trabajo activo.
- **Asistente paso a paso, recorrido guiado o panel de actividad**: el flujo tiene tres pasos; basta con textos claros y los estados de §4.
- **Librerías de diálogos, notificaciones o estado**: `<dialog>` nativo y el CSS propio alcanzan.
- **Mostrar códigos HTTP, "cookie", "sesión 410", "índice", "embeddings"** en cualquier mensaje.
