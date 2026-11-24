# Logos de la marca

Esta carpeta está vacía a propósito: **los logos no se versionan** (el repositorio es público). El servicio de destino copia aquí los archivos del banco.

## Cómo se configuran
1. Copia los archivos aquí (`LOGO_DIR`, por defecto esta carpeta): solo `.svg` o `.png`, nombre con letras, números, `.`, `_` o `-`, **≤ 512 KB** cada uno.
2. En el archivo de configuración por defecto (`config/defaults.env`) o en las variables del servicio, pon la ruta de cada uno:

| Variable | Qué es | Caja máxima | Si está vacía |
|---|---|---|---|
| `LOGO_ORG_URL` | Logo de la organización (cabecera, extremo izquierdo) | 200 × 40 px | no se muestra |
| `LOGO_PRODUCTO_URL` | Logo del producto (opcional, antes del nombre) | 32 px de alto (hasta 120 px de ancho) | se usa ⚖ |
| `LOGO_PIE_URL` | Logo de «Ajustes → Acerca de» | 160 × 32 px | no aparece |
| `NOMBRE_PRODUCTO` | Texto de la cabecera (siempre visible) | 80 caracteres | «Comparador Normativo» |
| `TEXTO_ALTERNATIVO` | Nombre de la organización para el texto alternativo («Logo de …») | 120 caracteres | «Logo» |

Ejemplo: `LOGO_ORG_URL=/marca/logo-org.svg`. Solo se aceptan rutas `/marca/<archivo>.svg|png`; cualquier otra cosa (https externo, `data:`, `..`) se ignora y la cabecera queda con el texto. Reinicia la app después de cambiar las variables.

## Recomendaciones
- SVG con `viewBox`, o PNG a 2× (400 × 80 px), fondo transparente: la cabecera es blanca.
- La imagen se escala sin deformarse ni recortarse. A 320 px de ancho el logo de la organización baja a 120 × 28 px y el del producto se oculta.
- Colores y demás valores visuales: bloque `:root` al inicio de `frontend/src/estilos.css` (docs/ux/identidad-visual-v1.md §6).
