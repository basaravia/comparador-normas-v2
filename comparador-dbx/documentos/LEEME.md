# documentos/

Carpeta local de **entrada**, dividida en dos **zonas** (decisión del usuario, 12 oct 2026). Los notebooks, scripts y pruebas la leen con `carpeta_normas(zona)`, `carpeta_manuales(zona)` y `carpeta_comparaciones(zona)` de `backend/config.py`; la zona por defecto es `DOCS_ZONA` (`test`).

```
documentos/
├── test/                ← MOCK ficticios y normas públicas: lo reproducible
│   ├── normas/          ← PDF de normas públicas (no se versionan por tamaño)
│   ├── manuales/        ← los 3 MOCK-DEMO-* (SÍ se versionan)
│   └── comparaciones/   ← comparaciones a mano de prueba (no se versionan)
└── val/                 ← documentos REALES de validación: NUNCA se versionan (todo `val` está ignorado)
    ├── normas/
    ├── manuales/
    └── comparaciones/   ← tu comparación hecha a mano (CSV/XLSX)
```
Los resultados siguen la misma regla: `output/test/` se puede versionar (salvo la caché `bloques/`, que lleva texto íntegro) y `output/val/` nunca. En `val` los notebooks no muestran texto de los documentos (solo identificadores, títulos, rutas, páginas y scores).

**Migrar lo que tenías:** mueve `documentos/normas/*` a `documentos/test/normas/` (públicas) o a `documentos/val/normas/` (reales), y lo mismo con los manuales (los MOCK ya están en `test/manuales/`). La caché antigua `output/bloques/` puedes moverla a `output/test/bloques/` o `output/val/bloques/` (la caché es por hash de archivo: si no la mueves, se vuelve a extraer).

## test/normas/ y val/normas/
Copia aquí los PDF de las normas (por ejemplo los de `Normativa2026/` del repo v1). Los notebooks esperan estos nombres:

| Archivo | Lo usan |
|---|---|
| `L1-XVI-cap-III.pdf`, `L1-XVI-cap-IV.pdf`, `L1-XVI-cap-V.pdf` | notebooks 01, 02, 03 y 05 |
| `Proyecto-de-Ley-Organica-Organica-para-Reprimir-y-Prevenir-el-Lavado-de-Activos-y-la-Financiacion-del-Terrorismo.pdf` | notebooks 01, 02, 03 y pruebas de L2 y L3 |

## test/manuales/ y val/manuales/
Los manuales MOCK (`MOCK-DEMO-01/02/03.pdf`) son ficticios y **sí** están versionados. `MANUAL-ARLAFT-V14.pdf` (y su `.docx`) es un manual sintético muy parecido a uno real: 57 páginas, 120 encabezados de hasta 5 niveles, 14 tablas y numeración repetida. **No está en git**: cada quien lo tiene en local en esta carpeta (`.gitignore` solo deja pasar los `MOCK-DEMO-*`). La ingesta acepta el `.pdf`; el `.docx` se rechaza (ERR-ING-003).

Un manual real del banco no se sube a git: guárdalo fuera de esta carpeta (por ejemplo en `NORMAS_DIR` o en otra ruta local).

## Otra ubicación
Define `NORMAS_DIR` en `config/.env` (ruta absoluta, o relativa a `comparador-dbx/`):

```
NORMAS_DIR=/ruta/completa/a/mis/normas
```

En Databricks, define `NORMAS_DIR` como variable de entorno apuntando a donde subas los PDF.

## Modelos de Docling sin acceso a Hugging Face (red bloqueada)
Docling descarga ~0,5 GB de modelos de `huggingface.co` la primera vez. Si tu red lo bloquea verás `ERR-EXT-004` (en el log: `SSLError ... huggingface.co`).
Dos salidas:

1. **Variables de red:** el extractor pasa a Docling `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`, `SSL_CERT_FILE` y `REQUESTS_CA_BUNDLE`. Si tu empresa usa proxy o certificado propio, defínelas en el entorno antes de abrir el notebook.
2. **Modelos locales (sin red):** copia la caché de modelos y trabaja sin conexión.
   ```
   # 1) Descomprime en la caché de Hugging Face (crea los enlaces models--docling-project--* -> models--ds4sd--*)
   mkdir -p ~/.cache/huggingface/hub
   tar xzf docling-modelos.tar.gz -C ~/.cache/huggingface/hub
   # 2) En config/.env
   HF_HUB_OFFLINE=1
   ```
   `docling-modelos.tar.gz` (~470 MB) sale de una máquina donde Docling ya descargó los modelos: `~/.cache/huggingface/hub/models--ds4sd--docling-layout-heron` y `models--ds4sd--docling-models`, más dos enlaces con el nombre nuevo `docling-project--...` que apuntan a esas carpetas.
   Con `HF_HUB_OFFLINE=1` Docling no intenta conectarse; si falta un modelo falla con `ERR-EXT-004`.

## Caché de bloques (`output/<zona>/bloques/`, o `BLOQUES_DIR`)
Si defines `BLOQUES_DIR`, los notebooks guardan el **texto íntegro** que Docling extrae de cada PDF (un `.json` por documento) para no repetir los 6-10 minutos de extracción. Con un manual real, eso es información del banco **en claro en tu disco**:
- Se crea con permisos privados (carpeta 700, archivos 600). Elige una carpeta tuya, fuera de cualquier carpeta que se sincronice o se suba, y bórrala al terminar (`/tmp` sirve).
- Nunca la subas a git. La app **no** la usa: no persiste nada (CLAUDE.md, regla 8).
- Antes de usar la caché se valida el PDF (tipo, tamaño y páginas); una caché dañada o manipulada se ignora y se vuelve a extraer.

## validacion_privada/
Comparaciones hechas a mano (CSV o XLSX) para validar la recuperación con un manual real. **No se versiona** y no debe salir de la máquina donde está. Las lee la sección 9c de `notebooks/03_recuperacion.ipynb` con `backend/retrieval/validacion.py`; solo se usan identificadores (artículo, sección), nunca texto.
