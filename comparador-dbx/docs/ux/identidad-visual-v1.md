# UX · Identidad visual «enterprise» y espacio para logos (v1)

Wireframe: `wireframes/identidad-cabecera-v1.svg` (baja fidelidad; el MCP de Penpot no estaba disponible, se usó SVG). Solo documentación: nada está implementado. Fecha: 24 nov 2026. Punto de partida: `frontend/src/estilos.css` (19.336 bytes). Paleta verde y blanco = decisión #12 de `14-puntos-abiertos.md`; se sustituye por el brand kit del banco cuando llegue.

Alcance (PO): solo tokens CSS en `:root` y reorganización visual. Sin dependencias, sin librerías de UI, sin fuentes ni iconos por CDN, sin cambios de comportamiento, API, textos ni roles ARIA. CSS final ≤ 32 KB (el doble de 16 KB). Esfuerzo total: M. Backend: no (salvo la opción B de logos, ver §4).

## 1. Principios enterprise aplicables
Patrones tomados de herramientas GRC/auditoría (AuditBoard, TeamMate+, Workiva, HighBond, ServiceNow IRM, Eramba, CISO Assistant). Aquí no se consultó su documentación en línea: son patrones de dominio generales, no citas verificadas. Lo único que se mide en este documento son los contrastes (calculados con la fórmula WCAG 2.2).

| Principio | Qué significa en esta app |
|---|---|
| Jerarquía | Un solo elemento dominante por pantalla (el botón primario verde). Títulos de 3 niveles de peso, no de color. El verde marca acción y estado activo; no decora. |
| Calma y densidad útil | Fondo gris muy claro, tarjetas blancas con borde fino y sombra casi nula; filas de lista de 40 px mínimo; cifras con `tabular-nums`. Más aire entre grupos (24 px) que dentro de ellos (8 px). |
| Estados siempre legibles | Cada estado = color + letra/palabra (A/L/R/X/P; «En análisis», «Cubre en parte»...). Nunca solo color. El rojo solo para brecha (RF-18) y error. |
| Propuesta rotulada | Lo automático lleva su rótulo («Propuesta generada automáticamente») en tono neutro, no en tono de alerta. Sin cambio de texto. |
| Evidencia primero | Citas en bloque con filo izquierdo verde y fuente en negrita (ya existe); se conserva. |
| Consistencia | Una escala de espaciado (4/8/12/16/24/32), un radio por tamaño de componente, una sombra. Ninguna pantalla define valores propios. |

## 2. Tokens (valores ACTUALES y contraste medido)
Contraste = razón WCAG 2.2. Umbral: texto ≥ 4,5:1; componentes e iconos ≥ 3:1 (1.4.11). «Falla» = incumple hoy. «Propuesta» = valor sugerido para corregirlo; el resto se queda igual.

### 2.1 Color base, superficie, borde y texto
| Token | Actual | Par medido | Razón | Resultado | Propuesta |
|---|---|---|---|---|---|
| `--verde` | #1e7b4f | blanco sobre verde (botón primario, paso activo) | 5,25 | Cumple | igual |
| `--verde-osc` | #165c3b | blanco sobre él (hover) / sobre blanco | 7,99 | Cumple | igual |
| `--verde-claro` | #e7f3ec | verde sobre él (secundario hover) | 4,61 | Cumple | igual |
| `--blanco` | #ffffff | superficie de tarjetas | – | – | token `--superficie` = blanco (alias) |
| `--fondo` | #f6f8f7 | fondo de página | – | – | igual |
| `--texto` | #1f2a24 | sobre blanco / sobre fondo | 14,84 / 13,91 | Cumple | igual |
| `--gris` (texto secundario) | #6b7770 | sobre blanco | 4,67 | Cumple | **#5b6760** |
| | | sobre fondo #f6f8f7 (ayudas, `small`) | 4,38 | **Falla** | 5,54 |
| | | sobre verde-claro (franja PDF, tablas) | 4,10 | **Falla** | 5,19 |
| | | sobre #e3e9e6 (etapas inactivas) | 3,79 | **Falla** | 4,80 |
| | | sobre #eceff0 (`.estado`, `.par`) | 4,04 | **Falla** | (usar `--texto` en chips: 12,84) |
| `--borde` (decorativo) | #d6ded9 | sobre blanco / fondo | 1,37 / 1,29 | Solo válido como separador, no como límite de control | igual |
| `--borde-control` (nuevo) | – | límite de input, select, textarea, chip de filtro, casilla | – | Hoy esos controles usan `--borde`: **falla 1.4.11** | **#7f8b85** (3,54 sobre blanco; 3,32 sobre fondo) |
| `--foco` | #2f6fb0 | anillo sobre blanco / fondo | 5,22 / 4,90 | Cumple (3 px, offset 2 px, queda fuera del botón verde) | igual |
| Borde dropzone | #1e7b4f | sobre fondo | 4,92 | Cumple | igual |

### 2.2 Estados de marca A/L/R/X/P (letra + palabra, además del color)
| Marca | Palabra visible | Fondo actual | Letra blanca | Resultado | Propuesta |
|---|---|---|---|---|---|
| A | Sí cumple | #1e7b4f | 5,25 | Cumple | igual |
| L | Cumple parcialmente | #c98a00 | 2,95 | **Falla** | misma ámbar #c98a00 con **letra `--texto`** (5,03) |
| R | No cumple | #c23b32 | 5,30 | Cumple | igual |
| X | No aplica | #6b7770 | 4,67 | Cumple | igual |
| P | Información obtenida de la normativa | #2f6fb0 | 5,22 | Cumple | igual |

Texto de estado sobre fondos tintados (chips y notas):
| Uso | Par | Razón | Resultado |
|---|---|---|---|
| `.chip-total`, `.estado-listo` | verde-osc sobre verde-claro | 7,01 | Cumple |
| `.chip-parcial` | #6b4700 sobre #fff1cf | 7,42 | Cumple |
| `.chip-nula`, `.estado-error` | #9c2a22 sobre #fdeceb | 6,64 | Cumple (`.estado-error` usa `--R` #c23b32: 4,63, cumple justo) |
| `.estado-extrayendo` | #2f6fb0 sobre #e4eefa | 4,45 | **Falla** → #2a64a3 (5,19) |
| `.lento`, `.cob-parcial`, `.incierto` (texto ámbar) | #c98a00 sobre fondo/blanco | 2,77 / 2,95 | **Falla** → #8a5d00 (5,76 sobre blanco; 5,34 sobre #fff6dd) |
| `.nota-aviso` | texto sobre #fff6dd | 13,77 | Cumple |
| `.ajuste-aviso` | #8a5d00 sobre blanco | 5,76 | Cumple |
| Barra de progreso | verde sobre #e3e9e6 | 4,26 | Cumple (componente ≥ 3) |

Reglas de forma para no depender del color: cada marca conserva su letra; en lista, el chip lleva la palabra. Un icono por estado es opcional y queda en «después» (necesita SVG propio; sin CDN).

### 2.3 Radio, espaciado, sombra, tipografía
| Token | Actual | Propuesta |
|---|---|---|
| `--radio` | 8px (más 6, 10, 12, 14, 16, 20 sueltos) | `--r-s:6px` controles, `--r-m:8px` tarjetas, `--r-l:12px` diálogo/dropzone, `--r-pill:999px` chips y pasos |
| Espaciado | valores sueltos (3, 6, 8, 10, 12, 14, 16, 18, 24, 36, 40) | `--e1:4px --e2:8px --e3:12px --e4:16px --e5:24px --e6:32px`; usarlos al reordenar |
| Sombra | ninguna (solo `box-shadow` en filtro activo) | `--sombra:0 1px 2px rgba(31,42,36,.08)` en tarjetas y pie fijo; sin sombras grandes |
| Tipografía | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`; 1,45 de interlineado | igual (fuentes del sistema, sin descargas). Escala: 12/13/14 (base 16)/18/20 px; títulos 600; `tabular-nums` en cifras |
| Objetivo táctil | filtros y filas 40 px; otros botones ~36–40 px; `.plegar` 24 px | mínimo 24 px en todo control; 40 px en filas y chips |
| Movimiento | `latido`, transición de barra; ya hay `prefers-reduced-motion` | mantener; sumar cualquier transición nueva a ese bloque |

## 3. Pantallas, en orden de entrega
Cada paso es independiente y reversible. Criterios medibles (se verifican con captura + herramienta de contraste + teclado).

**P1 · Tokens + cabecera + Ajustes (esfuerzo M).** Cabecera blanca de 56 px con borde inferior de 1 px `--borde` y filete verde de 3 px (como hoy), zona de marca a la izquierda (§4), pasos en el centro, Ajustes y «Servicio disponible» a la derecha. Ajustes: tarjetas `.ajuste` con la nueva sombra y espaciado 12/24.
- Todos los pares de §2 cumplen 4,5:1 (texto) o 3:1 (componente) medidos con la fórmula WCAG.
- La cabecera no cambia de altura entre pasos y no hace más de 2 líneas a 320 px de ancho.
- Foco visible en Carga, Selección, Resultados, Ajustes y Servicio: anillo ≥ 2 px, visible sobre el paso activo verde.
- Con `prefers-reduced-motion` no hay animaciones.
- Sin logos configurados la cabecera se ve igual que hoy (§4).

**P2 · Carga.** Dropzone con borde punteado verde, `--r-l`, más aire vertical; la tabla de documentos con encabezado `--verde-claro` y filas de 40 px; estados `.estado` con texto `--texto`.
- El botón primario es el único elemento verde sólido en la pantalla.
- Un nombre de archivo de 120 caracteres no produce scroll horizontal.
- Todos los controles de fila miden ≥ 24 px; tabulación llega a «Quitar» sin trampas.

**P3 · Selección (estructura aprobada intacta).** Solo: bordes de controles a `--borde-control`, paneles con sombra, pie fijo con sombra superior en lugar de filete de 2 px.
- La posición de árbol, vista, barra y pie no cambia respecto de `seleccion-indice-v1.svg`.
- Casillas, buscador y «solo marcados» tienen límite visible ≥ 3:1.
- El pie fijo no tapa la última fila al desplazarse (margen inferior ≥ altura del pie).

**P4 · Comparando (estructura de `comparacion-en-curso-v1.md` intacta).** Solo: filas `.fila-par` con sombra y filete izquierdo verde en curso; chips con texto `--texto`; resumen fijo con fondo `--fondo`.
- Los bloques A–F siguen en el mismo orden y con los mismos textos.
- Ninguna fila cambia de alto al pasar de «En análisis» a resuelta (sin saltos de lista).
- «Cancelar comparación» sigue visible sin desplazarse en 1366×768.
- Filtros ≥ 40 px de alto, estado activo distinguible sin color (negrita + borde 2 px).

**P5 · Resultados.** Tarjetas de resumen A/L/R/X/P con la letra sobre el nuevo ámbar; tabla con encabezado fijo; detalle con citas lado a lado.
- Las 5 marcas se distinguen en escala de grises por letra y palabra.
- La letra L cumple 4,5:1 (5,03).
- El rojo aparece solo en R y en errores; ningún otro uso decorativo.
- Se puede filtrar por R y abrir el detalle con teclado (Enter/Espacio) sin perder la lista.
- La «Conclusión» conserva su rótulo de propuesta automática, en texto `--gris` ≥ 4,5:1.

## 4. Hueco de logos
Wireframe: `wireframes/identidad-cabecera-v1.svg`. Los logos los aporta el banco en el servicio de destino; **no se guardan en el repo público**.

| Elemento | Posición | Tamaño | Zona de respeto | Alt text |
|---|---|---|---|---|
| Logo de la organización | cabecera, extremo izquierdo | caja máx. **200×40 px** (proporción libre; se escala con `object-fit: contain`, nunca se deforma ni recorta) | 8 px por lado; 16 px de separación con el nombre del producto | «Logo de {nombre de la organización}» |
| Logo del producto (opcional) | a la derecha del anterior, antes del nombre | caja máx. **32×32 px** (cuadrado) o 120×32 (apaisado) | 8 px por lado | vacío (`alt=""`), porque el nombre «Comparador Normativo» está al lado como texto |
| Logo pie / «Acerca de» (opcional) | pie de Ajustes, sección «Acerca de» | caja máx. 160×32 px, en gris o monocromo si el logo lo permite | 16 px | «Logo de {organización}» |
| Excel | no aplica | – | – | – |

Reglas:
- Formato SVG o PNG (recomendado SVG con `viewBox`; PNG a 2×: 400×80). Peso ≤ 100 KB. Fondo transparente; sobre cabecera blanca.
- **Sin logo:** el texto «Comparador Normativo» (con ⚖ como hoy) ocupa el lugar. Es el fallback y no cambia de tamaño ni de posición. Si la imagen falla al cargar, se oculta y se muestra el fallback (sin icono de imagen rota).
- **Con logo:** el texto «Comparador Normativo» sigue visible (nombra el producto y mantiene el nombre accesible de la cabecera); el logo se suma, no lo reemplaza.
- A 320 px de ancho el logo de la organización se reduce a 120×28 px y el logo de producto se oculta; el texto no se corta.
- Contraste: un logo es contenido de marca, exento de 1.4.3; igualmente el fondo de cabecera queda blanco para no obligar al banco a versiones en negativo.

Cómo se configura (sin dependencias ni logos en el repo):
- **Vigente: opción B de §6 (variables en `config/defaults.env`).** La opción A queda descartada por el requisito de configuración paramétrica:
- **Opción A (descartada, backend: no):** el servicio de destino coloca los archivos en `frontend/dist/marca/` (o `frontend/public/marca/` antes del build): `logo-org.svg`, `logo-producto.svg`, `logo-pie.svg`, más `marca.json` con `{"organizacion": "Banco X"}` para el alt. La carpeta `marca/` va en `.gitignore`; el repo solo trae `marca/LEEME.md` con estas medidas. Sin archivos → fallback. La interfaz los pide con `<img>` y `onError`; para el nombre lee `marca.json` con un `fetch` simple.
- **Opción B (backend: sí, esfuerzo S):** variables `LOGO_ORG_ARCHIVO`, `LOGO_PRODUCTO_ARCHIVO`, `LOGO_ORG_ALT` en `config/defaults.env` (junto a `COLOR_PRIMARIO`), carpeta fuera del repo (por ejemplo `/tmp` o la que defina el servicio) y una ruta de solo lectura que sirva el archivo. Más coherente con el resto de la configuración, pero toca API.
- Alternativa descartada: incrustar logos como base64 en el CSS o en el código (sube el repo y expone la marca en el repositorio público).
- Los colores del brand kit se cambian en `:root` (`--verde`, `--verde-osc`, `--verde-claro`); `COLOR_PRIMARIO` ya existe en `config/defaults.env`. Quien cambie el verde debe volver a medir los pares de §2 (blanco sobre `--verde` ≥ 4,5).

## 5. Qué NO cambia
- Estructura y orden de Comparando (bloques A–G) y de Selección (árbol, vista previa, pie).
- Textos, etiquetas, mensajes y códigos de error; roles y atributos ARIA; orden de tabulación.
- Comportamiento, API, esquemas, flujo de 3 pasos, atajos.
- Marcas A/L/R/X/P: letras, palabras y significado; el rojo sigue reservado a brecha y error.
- Excel (formato, encabezado verde `COLOR_PRIMARIO`).
- Dependencias, fuentes (del sistema) e iconos (caracteres existentes).

## 6. Cómo sustituir la identidad (requisito del usuario: todo paramétrico)
Esta sección **sustituye** la opción A de §4: los logos se configuran por variables (opción B, requiere backend S). Hoy `estilos.css` tiene colores literales fuera de `:root` (#fff6dd, #fdeceb, #eceff0, #e3e9e6, #e4eefa, #fff1cf, #8a5d00, #6b4700, #9c2a22, #9fcdb4, #f1f4f2, #fafcfb, `rgba(46,125,50,…)`, `#2e7d32`); en la implementación pasan a tokens.

**(a) Un solo bloque de tokens.** Todo valor visual vive en `:root` al inicio de `estilos.css` (o en `tokens.css` importado por él, mismo peso). Ninguna otra regla usa colores, fuentes, radios ni sombras literales: solo `var(--…)`. Cada token marcado `[CALIBRAR]` es un valor del brand kit.

| Grupo | Tokens (`[CALIBRAR]`) |
|---|---|
| Marca | `--verde`, `--verde-osc`, `--verde-claro`, `--sobre-marca` (texto sobre `--verde`, hoy blanco) |
| Superficie y texto | `--fondo`, `--superficie`, `--texto`, `--texto-suave` (hoy `--gris`), `--borde`, `--borde-control`, `--foco` |
| Estados | `--A`, `--L`, `--R`, `--X`, `--P` y sus letras `--sobre-A`…`--sobre-P` |
| Avisos tintados | `--aviso-fondo`/`--aviso-texto`, `--error-fondo`/`--error-texto`, `--info-fondo`/`--info-texto`, `--neutro-fondo` (reemplazan los literales listados arriba) |
| Forma | `--r-s`, `--r-m`, `--r-l`, `--r-pill`, `--sombra`, `--e1`…`--e6`, `--alto-cabecera` |
| Tipografía | `--fuente` (pila del sistema por defecto; el banco puede nombrar la suya **si ya está instalada**, sin descargas), `--tam-base`, `--peso-titulo` |
| Logos | `--logo-org-max-w:200px`, `--logo-org-max-h:40px`, `--logo-prod-max:32px`, `--logo-pie-max-w:160px` |

El valor por defecto de `--verde` sigue viniendo de `COLOR_PRIMARIO` (`config/defaults.env`); si el backend lo entrega en la configuración pública, la interfaz lo asigna a `--verde` al arrancar (misma ruta que los logos). Los demás tokens se editan en el bloque.

**(b) Logos y nombre por configuración pública (no sensible).** Variables nuevas en `config/defaults.env`, todas opcionales (vacías = fallback):

| Variable | Qué es | Vacía |
|---|---|---|
| `NOMBRE_PRODUCTO` | Texto de la cabecera | «Comparador Normativo» |
| `LOGO_ORG_URL` | Logo de la organización (cabecera) | no se muestra |
| `LOGO_PRODUCTO_URL` | Logo del producto (opcional) | se usa ⚖ como hoy |
| `LOGO_PIE_URL` | Logo de «Acerca de» | la sección no se muestra |
| `TEXTO_ALTERNATIVO` | Nombre de la organización para el alt («Logo de …») | alt = «Logo» |

- El backend expone estos valores de solo lectura en la configuración pública que ya consulta la interfaz (nueva ruta o campos aditivos; **requiere backend, esfuerzo S**). Solo URLs relativas de la propia app o rutas del servicio; nunca claves ni datos de usuario. Validar que sea una ruta o `https://` del dominio del servicio (revisión de `appsec`).
- Los archivos de logo se **copian en el servicio de destino** (carpeta servida por el backend, por ejemplo la que defina `LOGO_DIR`), **nunca al repo**; `.gitignore` los excluye y el repo solo trae `marca/LEEME.md` con las medidas de §4.
- Con la variable vacía o el archivo ausente, la interfaz muestra el texto de `NOMBRE_PRODUCTO` (fallback de §4). Sin cambios de textos fijos: el nombre es el mismo por defecto.

**(c) Lista de verificación: sustituir paleta y logos (5 pasos).**
1. Pon los colores del brand kit en el bloque `:root` (marca, superficie, texto, estados, avisos) y, si aplica, `COLOR_PRIMARIO`.
2. Copia los logos al servicio de destino y completa `LOGO_ORG_URL`, `LOGO_PRODUCTO_URL`, `LOGO_PIE_URL`, `NOMBRE_PRODUCTO` y `TEXTO_ALTERNATIVO` en `config/defaults.env`; reinicia.
3. Revisa a simple vista las 5 pantallas (Carga, Selección, Comparando, Resultados, Ajustes) con y sin logo; nada se corta a 320 px.
4. Mide el contraste de los pares siguientes (herramienta WCAG o la fórmula usada aquí) y corrige el token si falla:
   - Texto 4,5:1: `--texto` / `--superficie` y `--fondo`; `--texto-suave` / `--superficie`, `--fondo`, `--verde-claro` y fondo de etapas; `--sobre-marca` / `--verde` y `--verde-osc`; `--verde` y `--verde-osc` / `--verde-claro`; `--sobre-A…P` / cada estado; `--aviso-texto` / `--aviso-fondo`; `--error-texto` / `--error-fondo`; `--info-texto` / `--info-fondo`.
   - Componente 3:1: `--borde-control` / `--superficie` y `--fondo`; `--foco` / `--superficie`, `--fondo` (el anillo queda fuera del botón verde); `--verde` / `--fondo` (borde de la zona de carga); `--verde` / fondo de barra de progreso.
5. Comprueba por teclado que el foco se ve en cada control y que A, L, R, X y P se distinguen en escala de grises (letra y palabra).
Aceptación: ningún par de la lista baja del umbral; cambiar toda la identidad no exige tocar ninguna regla de componente (verificable con `grep -nE '#[0-9a-fA-F]{3,8}|rgba?\(' estilos.css` fuera de `:root`: 0 coincidencias).

## 7. Decisiones pendientes para el usuario / PO
1. (Resuelto por el usuario: logos por variables; ver §6.) Ajustar §4 «Opción A» como descartada.
2. Aprobar el ajuste de color de L (letra oscura) y del gris secundario (#5b6760): cambian ligeramente el aspecto, pero corrigen 7 pares que hoy fallan 4,5:1.
3. Si el banco exige que el logo aparezca también en el pie de Resultados (hoy se propone solo en cabecera y «Acerca de»).
