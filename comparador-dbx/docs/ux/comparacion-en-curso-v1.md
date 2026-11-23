# UX · Comparación en curso: una lista, un resumen, un tiempo (v1)

Wireframe: `wireframes/comparacion-en-curso-v1.svg` (baja fidelidad; Penpot no se usó). Sustituye la pantalla 2b de `mejora-experiencia-v1.md`. Nada está implementado. "API" = requiere cambio de backend.

## 1. Diagnóstico: por qué satura (evidencia: `ProgresoVivo.tsx`, `Processing.tsx`)
| Qué compite o se repite | Dónde |
|---|---|
| La misma fase se dice tres veces: «25 % · Juzgando cada par…», «Evaluando cada par» y el anuncio oculto. | `Processing.tsx` + `ProgresoComparacion` |
| «25 %» con «par 0 de 2»: el % mezcla fases (0,3 + 0,55·h/t), no es de pares. Parece un error. | `cb()` en `servicio._ejecutar` |
| Dos relojes (Transcurrido, Última novedad) más un aviso condicional «Sigue trabajando…» que con ~3 min por par aparece siempre. | `Tiempos` |
| Tres bloques con el mismo par: «Ahora se analizan» (con textos), «Últimos veredictos» (sin textos) y conteos provisionales + «a revisión». Cada par cambia de sitio al resolverse. | `ProgresoComparacion` |
| El veredicto no trae documento, página ni citas: el auditor ve «Art. 12 ↔ 5.2» sin poder comprobar nada; solo hay 20 (anillo) y se pierden al crecer. | `VeredictoVivo`, `servicio.termina` |
| Metadatos de bajo valor siempre visibles (similitud, «encontrado por la norma y el manual»). | `.par-meta` |
| Cancelar y la nota quedan al fondo de una página larga; tras pulsar, `cancelable` pasa a `false` y el botón local (`pedido`) se pierde al recargar. | `Cancelar` |
| La nota «No mostramos razonamiento» convive con «Ver comentario del modelo»: mensaje contradictorio. | `Veredicto` |

## 2. Propuesta (una pantalla, tres zonas)
Referencias: NN/g (percent-done para esperas largas, mostrar ítems completados, estimado como rango, ofrecer cancelar); NN/g sobre contenido que se actualiza (no mover la posición del lector, ofrecer «ir a lo último»); WCAG 2.2 criterio 2.2.2 (la información que se actualiza sola debe poder pausarse o controlarse) y 4.1.3 (avisos de estado sin mover el foco); patrón *feed* de ARIA APG (`aria-busy`, posición en el conjunto); AWS Audit Manager (estado de revisión por control, evidencia por control y bitácora; un ejemplo verificado de patrón GRC; TeamMate+ y AuditBoard no se pudieron verificar).

**Zona A · Resumen fijo (sticky, ver 1–4 del SVG).** Una línea de fase («Paso 2 de 3 · Evaluando cada par»), barra **de pares** (no el % mezclado), contador, **un solo tiempo**, estimado, Cancelar y los filtros. Nada de lo que está aquí se repite abajo.
**Zona B · Lista única de pares (5–9).** Una fila por par, mismo componente en todos los estados. Orden: **en análisis arriba** (borde verde, máx. `LLM_CONCURRENCY`), luego **resueltos, el más reciente primero**. Los pares en espera no son filas: son el contador.
**Zona C · Pie:** una nota corta (ver §4).

**Fila colapsada (1 línea, ≥ 40 px):** [chip de estado con icono + palabra] · «Art. 12 · {norma} ↔ Sección 5.2 · {manual}» · «✓ Citas verificadas» o «⚠ Citas por revisar» · chevron. Sin similitud, sin confianza, sin origen.
**Fila expandida (Enter/Espacio o clic; varias a la vez):** dos columnas, **Cita de la norma | Cita del manual**, cada una con documento, sección, página y estado de verificación; «Qué falta» (si es parcial); «Confianza del modelo N %» y «Ver comentario del modelo» plegado (texto plano). En análisis, el detalle muestra «Texto que se está evaluando» (los previews actuales) y la similitud.
**Marcas:** por par solo se muestra la cobertura. Las marcas A/L/R/X/P son por artículo y se calculan al final; no se muestran provisionales por par. Rojo solo para «No lo cubre» (brecha, RF-18); «Sin veredicto» e «incompletas» van en ámbar con ⚠.

**Orden y lectura sin saltos (decisión de diseño).** Lo más reciente arriba, **sin auto-scroll**. Si la persona ha bajado más de una fila, tiene una fila abierta o el foco está dentro de la lista, los resultados nuevos **no se insertan**: aparece «N resultados nuevos · Mostrar» y los contadores siguen vivos. Así nada se mueve bajo el ojo y se cumple 2.2.2. Descartado: oldest-first con seguimiento al final (el par en curso quedaría lejos del resumen con cientos de filas).
**Cientos de pares:** se pintan 50 resueltos y «Mostrar 50 más (quedan N)» (botón, no scroll infinito: operable por teclado). Sin virtualización: 50–150 filas colapsadas de texto no la justifican. Los filtros acotan.
**Filtros = conteos:** chips «Todos · Cubre por completo · Cubre en parte · No lo cubre · Por revisar» con n entre paréntesis y `aria-pressed`; reemplazan la línea «Hasta ahora (por par, provisional)». Tooltip: «Conteo por par; las marcas A, L, R, X y P se calculan al final.»
**Lectores de pantalla:** una región `role="status"` oculta, **solo por hitos**: cambio de fase, cada 10 % de pares o cada 60 s (lo que ocurra último), espera del proveedor, fin o cancelación («12 de 40 pares resueltos; 3 por revisar»). Nada por par. Barra con `role="progressbar"`, `aria-valuenow`=resueltos, `aria-valuemax`=total, `aria-valuetext`=«12 de 40 pares». Lista = `ul`/`li` con botón de disclosure (`aria-expanded`/`aria-controls`); `aria-busy` no hace falta (no es feed). Los nuevos retenidos no se anuncian.

## 3. Cancelar
- **Siempre visible** en el resumen fijo, texto «Cancelar comparación», objetivo ≥ 40 px. (Dónde estaba — al fondo — es una causa probable de «no funciona»; el comportamiento del servidor lo investigas tú.)
- Sin pares resueltos: cancela sin preguntar. Con ≥ 1: confirmación **en línea** (no modal): «¿Cancelar la comparación? Ya resolvimos {N} pares. [Sí, cancelar] [Seguir comparando]».
- **Cancelando…** (botón deshabilitado, rótulo «Cancelando…», bajo él: «No se enviarán más pares.»). Dura ~1 s: la cancelación actúa de inmediato aunque haya llamadas al modelo en vuelo (se descartan sus resultados; [05](../05-ux.md), [11](../11-api.md)). Las filas en análisis pasan a «Terminando». **API:** `cancelando: bool` en `JobOut` (hoy `cancelable=false` oculta el botón y `pedido` se pierde al recargar). Si la petición falla: «No pudimos enviar la cancelación (ERR-JOB-…). Inténtalo de nuevo.» y el botón vuelve.
- **Cancelado.** Texto A (hoy, el parcial se descarta): «Comparación cancelada. Los {N} pares resueltos no se conservan.» (con N = 1: «El par resuelto no se conserva»; con N = 0, solo «Comparación cancelada.») Texto B (**decisión PO/usuario**, solo si el backend conserva lo resuelto): «Cancelada: se conservan los {N} pares ya resueltos y no se vuelven a evaluar si comparas de nuevo.» B exige que `juzgar_pares` reutilice pares ya juzgados por (artículo, sección, ajustes) en memoria; no se puede dar un papel de trabajo parcial (las marcas son por artículo). En ambos, la lista queda visible de solo lectura bajo «Volver».

## 4. Textos exactos
Título «Comparando». Fases: «Paso 1 de 3 · Buscando coincidencias» / «Paso 2 de 3 · Evaluando cada par» / «Paso 3 de 3 · Armando el papel de trabajo».
Contador «{h} de {t} pares resueltos» · «{e} en análisis · {w} en espera». Tiempo «Tiempo transcurrido: {d}». Estimado «Falta aproximadamente: entre {a} y {b}» desde 3 pares resueltos; antes «Todavía no podemos estimar el tiempo restante.» (La fase 1 y 3 no muestran estimado.)
Ayuda (una línea, sustituye «Sigue trabajando…», sin segundo reloj): «Cada par puede tardar varios minutos con el modelo local. Puedes dejar esta pestaña abierta o volver más tarde: el avance se conserva.»
Estados: «En análisis» · «Terminando» · «Cubre por completo» · «Cubre en parte» · «No lo cubre» · «Sin veredicto · revisar». Citas: «✓ Citas verificadas» / «⚠ Citas por revisar». Detalle: «Cita de la norma», «Cita del manual», «Verificada en el texto», «No pudimos confirmar esta cita; mostramos el fragmento más cercano del documento», «El modelo no encontró un fragmento del manual que lo cubra», «Qué falta».
Vacíos: «Todavía no hay pares resueltos. El primero aparecerá aquí.» · «Ningún par resuelto coincide con este filtro. [Ver todos]». Listas: «{n} resultados nuevos · Mostrar» · «Mostrar 50 más (quedan {n})».
Espera del proveedor (existente): «Esperando al servicio de IA (límite de uso del proveedor). Se reanuda en {s} s · intento {i} de {m}.»
Pie (sustituye la nota actual): «Mostramos solo el veredicto y las citas, verificadas contra el texto del documento; no el razonamiento del modelo. Los resultados por par son provisionales: las marcas A, L, R, X y P se calculan al final, por artículo.»

## 5. Datos por par: qué llega y qué falta
| Dato | Hoy | 
|---|---|
| fase, `pares_total`, `pares_hechos`, `conteo_cobertura`, `a_revision`, `espera_limite`, `inicio_ts`, `ahora_ts` | Sí (`JobOut`) |
| En análisis: id, documento, página, preview, score, origen, `desde_ts` (`ParEnCurso`) | Sí |
| Resuelto: `seq`, cobertura, naturaleza, confianza, `cita_*_ok`, `requiere_revision`, comentario (≤ 300) | Sí, pero solo los **últimos 20** y con identificadores sueltos |
| Resuelto: documento, página, texto de la cita de la norma y del manual (los reales, de `verificar_fragmento`), «qué falta» | **No** |
| Historial completo de pares resueltos (recarga, cientos) | **No** |
| Estado «cancelando» | **No** (se deduce de `etapa`, frágil) |

**Cambio de API mínimo:** (1) `GET /api/jobs/{id}?desde=N` agrega `pares_resueltos: list[ParResuelto]` (solo `seq > N`) y `seq_ultimo`; `ParResuelto` = `VeredictoVivo` + `articulo` y `seccion` como `FragmentoOut` + `cita_norma`, `cita_manual` (≤ 600 letras, texto del documento, regla 5) + `elementos_faltantes`. El servidor guarda la lista completa en el job (memoria, ≤ `MAX_PARES`; ~2 KB por par). Sin `desde` o con `desde=0` devuelve todo: así la recarga (reenganche) no pierde nada, y el sondeo de 1,5 s solo transporta lo nuevo. (2) `cancelando: bool`. (3) Solo para el texto B: reutilizar pares ya juzgados. `ultimos_veredictos` se retira cuando el frontend migre.

## 6. Criterios de aceptación
1. El resultado de cada par (cobertura y citas) aparece en su propia fila; no existe un bloque aparte «Últimos veredictos».
2. En pantalla hay un solo tiempo («Tiempo transcurrido»); no aparece «Última novedad hace».
3. La barra y el texto coinciden: con 0 de 2 pares resueltos la barra está en 0 % y no se muestra «25 %».
4. Con 100 filas cargadas, a 1280×720, el resumen (fase, contador, tiempo, Cancelar, filtros) sigue visible al desplazarse.
5. Filtrar por «No lo cubre» deja solo esas filas y el número del chip coincide con las filas mostradas.
6. El auditor expande una fila con teclado (Enter/Espacio) y ve la cita de la norma y la del manual, con documento, sección y página, sin salir de la lista; `aria-expanded` correcto.
7. Con una fila abierta o el foco en la lista, llegan 3 resultados: nada se mueve y aparece «3 resultados nuevos · Mostrar»; al pulsar se insertan y el foco no se pierde.
8. Con 300 resueltos se pintan 50 y «Mostrar 50 más (quedan 250)»; tras recargar la página reaparecen los 300 en ≤ 2 s.
9. Con lector de pantalla (NVDA/VoiceOver) hay como máximo un anuncio por minuto, solo por hitos; ninguno por par.
10. Cancelar: con 0 resueltos no pide confirmación; con ≥ 1 la pide mostrando N; tras confirmar muestra «Cancelando…» en ≤ 1,5 s y lo conserva si se recarga; si falla, muestra mensaje con código y permite reintentar.
11. Cada estado lleva icono y palabra (nunca solo color); contraste ≥ 4,5:1; objetivos ≥ 24 px (filas y botones ≥ 40 px); foco visible; con `prefers-reduced-motion` no hay animación.
12. Ningún texto sugiere razonamiento («pensando…») ni muestra trazas; las citas mostradas son texto del documento, no del modelo.

## 7. Qué NO hacer
- No mostrar marcas A/L/R/X/P por par ni «provisionales»: la marca es del artículo.
- No auto-scroll ni insertar filas bajo el ojo de quien lee; no scroll infinito.
- No una segunda lista «resoluciones» ni un panel lateral: un par, una fila.
- No spinners ni animaciones de «pensando»; ni estimado antes de 3 pares.
- No anunciar cada par a lectores de pantalla ni mover el foco al llegar resultados.
- No mostrar el razonamiento del modelo; el «comentario» va plegado y como texto plano (pendiente §8).
- No modal de confirmación para cancelar; no ocultar el botón durante «Cancelando…».

## 8. Esfuerzo y decisiones
| Bloque | Esfuerzo | API |
|---|---|---|
| A Resumen fijo (un tiempo, barra de pares, fase, ayuda, pie) | S | No |
| B Lista única y fila expandible con citas | M | Sí (1) |
| C Filtros-chips con conteos | S | No |
| D Nuevos retenidos + «Mostrar 50 más» | S–M | No |
| E Anuncios a lector de pantalla por hitos | S | No |
| F Cancelar (visible, confirmación, «Cancelando…», error) | S | Sí (2, trivial) |
| G `pares_resueltos` incremental + historial en el job | M | Backend |
| H Conservar lo resuelto al cancelar / reutilizar pares (texto B) | L | Backend; **después** salvo decisión |

Decisiones para el PO/usuario: (a) ¿se muestra «Ver comentario del modelo» o solo veredicto y citas, como dice la regla del proyecto? Propuesta: plegado dentro del detalle y la nota del pie ajustada; (b) texto A o B al cancelar (H); (c) ¿se acepta mostrar «Qué falta» (`elementos_faltantes`, salida del modelo en texto plano)?

Fuentes: https://www.nngroup.com/articles/progress-indicators/ · https://www.nngroup.com/articles/saving-scroll-position/ · https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html · https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html · https://www.w3.org/WAI/ARIA/apg/patterns/feed/ · https://docs.aws.amazon.com/audit-manager/latest/userguide/review-controls.html
