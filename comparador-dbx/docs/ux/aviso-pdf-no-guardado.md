# UX · Aviso "el PDF no queda guardado" al terminar el paso 1 (v1)

Wireframe: `wireframes/aviso-pdf-no-guardado-v1.svg`. Nada implementado. Estado del código leído: `Processing.tsx` (al `listo` hace `paso: seleccion` sin pausa), `Upload.tsx` (ya existe "Continuar a la selección" cuando no hay pendientes), `Selector.tsx` (`seleccionLista` + `seleccionTrasRecarga` ya conservan marcas al recargar árboles), `DocTable.tsx` (estados solo "Listo").

## Patrón recomendado: diálogo modal con confirmación + recordatorio persistente pequeño
- Decisión del usuario: "popup". Se cumple con un `dialog` modal **una vez al terminar cada procesamiento**; el mensaje es crítico (pérdida de evidencia), por eso exige un clic consciente.
- Un modal solo se olvida: se añade (barato) una **franja informativa fija** en Selección y el estado "Indexado" en la lista. Así "no volver a mostrar" no deja a la persona sin recordatorio.
- Alternativa descartada: solo banner. Se ignora (ceguera a banners) y no deja constancia de que lo leyó.

## Texto (español de negocio)
- Título: **Tus documentos están listos. Guarda tus PDF.**
- Cuerpo: "Esta aplicación no guarda tus PDF. Solo conserva los datos de cada documento y su contenido preparado para buscar, hasta {retencion_horas} horas sin actividad o hasta que la aplicación se reinicie. Después tendrás que cargarlos de nuevo." (Corrección por exactitud del 16 nov 2026, informada al usuario y reversible: el texto aprobado decía "mientras la aplicación siga abierta", que dejó de ser cierto con la sesión por usuario.)
- "Conserva tu PDF original y anota qué archivo es (nombre, versión y fecha). Lo necesitarás para respaldar tu papel de trabajo."
- Lista de los documentos recién procesados (nombre · páginas).
- Casilla: "No volver a mostrar en esta sesión". Botón: **Entendido, continuar**.
- Franja en Selección: "Los PDF no se guardan en esta aplicación. Conserva los originales." + enlaces "Ver aviso" y "Agregar documentos".

## Cuándo aparece
- Cada vez que un procesamiento termina en `listo` (con documentos nuevos), salvo que la casilla se marcó. Esa preferencia vive en `sessionStorage` (por pestaña/sesión, no persistente: coherente con regla 8, sin guardar nada en servidor). "Cargar ejemplo" también lo muestra (ejemplo = mismo comportamiento; PO decide si lo omite).
- No aparece en "Continuar a la selección" sin documentos nuevos. "Ver aviso" lo reabre siempre.
- Franja: siempre visible mientras haya documentos indexados; no se puede ocultar en el MVP.

## Foco, teclado, ARIA
- `<dialog>`/`role="dialog" aria-modal="true"`, `aria-labelledby` = título, `aria-describedby` = cuerpo. (`alertdialog` no: no es un error destructivo.)
- Al abrir: foco al botón "Entendido, continuar"; Tab queda atrapado dentro; fondo `inert`. Esc = igual que confirmar (no hay acción destructiva). Al cerrar: foco a la cabecera de Selección (`h2` con `tabindex=-1`); no al botón anterior, que ya no existe.
- El título del documento y la lista se leen con el diálogo; objetivos ≥ 24 px; contraste AA; el icono ⓘ lleva texto, no solo color. Sin temporizador de cierre automático.
- Reutiliza el aviso de título de pestaña ya existente (✔ Listo) si la persona está en otra pestaña; el modal espera su vuelta.

## Volver al paso 1 y regresar con las marcas
1. En Selección, botón secundario "Agregar documentos" (pie y franja) → `paso: carga`. No se llama a `reiniciar`; `e.seleccion` no se toca.
2. En Carga, los documentos ya indexados aparecen en la tabla con estado "Indexado" (abajo); se suben y tipifican los nuevos; "Procesar" solo envía los pendientes (ya ocurre en `Upload.tsx`).
3. Al terminar, se muestra el aviso (solo con los documentos nuevos) y se entra a Selección: `seleccionLista` se reinicia y `seleccionTrasRecarga` conserva las marcas de los nodos que siguen existiendo. Mensaje breve: "Se conservaron tus N marcas. Los documentos nuevos llegan sin marcar."
4. Si no hay nada nuevo, "Continuar a la selección" vuelve directo, con las marcas intactas. Cancelar el procesamiento vuelve a Carga sin perder marcas (criterio 10 de mejora-experiencia-v1).

## Lista de documentos: PDF no disponible
- Estado visible **"Indexado"** (hoy el código muestra "Listo"; renombrar el texto `listo` → "Indexado" en `ESTADOS`, sin cambiar el valor de la API) con icono de candado/ojo tachado y texto: "Indexado · PDF no guardado".
- Tooltip/ayuda accesible (no solo hover; botón "?" con `aria-describedby`): "La aplicación conserva los datos y el contenido buscable, no el archivo PDF original."
- No hay acción "Descargar/Abrir PDF". En vez de ella, cada fila muestra el nombre original del archivo (ya existe `nombre`) y "pág. N": ayuda a identificar el PDF a conservar. Opcional: botón "Copiar nombre".
- Excel (docs/10): recomendar incluir nombre del archivo, páginas y fecha de proceso en la hoja de documentos, para que el papel de trabajo identifique el PDF. Requiere confirmar con PO.

## Criterios de aceptación
1. Al pasar a `listo` el procesamiento, aparece el diálogo antes de Selección, con la lista de documentos nuevos; no se puede seguir sin pulsar "Entendido" (o Esc).
2. Foco inicial en "Entendido"; Tab/Shift+Tab no salen del diálogo; al cerrar, el foco queda en el encabezado de Selección; lector de pantalla anuncia título y cuerpo.
3. Con la casilla marcada, el diálogo no reaparece en la misma sesión del navegador; "Ver aviso" lo reabre; la franja de Selección sigue visible.
4. El texto no contiene jerga (sin "FAISS", "vectorizado", "embeddings", trazas).
5. Desde Selección con 12 marcas, "Agregar documentos" → cargar 1 PDF → procesar → regreso a Selección conserva las 12 marcas válidas y avisa cuántas.
6. La tabla de documentos muestra "Indexado" con icono y texto "PDF no guardado"; no hay botón de descarga del PDF.
7. Todo operable con teclado; objetivos ≥ 24 px; contraste AA; sin depender solo del color.
8. Tras "Reiniciar sesión" la preferencia "no volver a mostrar" se borra y el diálogo vuelve a aparecer.

## Esfuerzo y backend
S–M, frontend solamente (diálogo, franja, texto de estado, botón "Agregar documentos"). Backend: no. Dependencia: ninguna nueva; `seleccionTrasRecarga` ya existe (verificar que conserve marcas cuando se agregan árboles, caso de prueba nuevo).

## Decisiones para el usuario / PO
- Frecuencia: ¿cada procesamiento con casilla de omitir por sesión (propuesto) o solo una vez por sesión sin casilla?
- ¿El ejemplo también muestra el aviso?
- ¿Incluir nombre de archivo, páginas y fecha en el Excel para identificar el PDF?
- Renombrar "Listo" a "Indexado" en la UI (mantiene valor de API).

## Fuentes
No se consultaron fuentes externas en esta sesión. Patrón de diálogo modal: WAI-ARIA APG (Dialog Modal), no verificado aquí.
