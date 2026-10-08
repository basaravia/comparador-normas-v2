# documentos/

Carpeta local de **entrada**: lo que pongas aquí **no se versiona** (`.gitignore`), pero los notebooks y las pruebas lo leen.

```
documentos/
├── normas/      ← PDF de las normas reales (NO se versiona)
└── manuales/    ← manuales de control: los 3 MOCK ficticios (SÍ se versionan)
```

## normas/
Copia aquí los PDF de las normas (por ejemplo los de `Normativa2026/` del repo v1). Los notebooks esperan estos nombres:

| Archivo | Lo usan |
|---|---|
| `L1-XVI-cap-III.pdf`, `L1-XVI-cap-IV.pdf`, `L1-XVI-cap-V.pdf` | notebooks 01, 02, 03 y 05 |
| `Proyecto-de-Ley-Organica-Organica-para-Reprimir-y-Prevenir-el-Lavado-de-Activos-y-la-Financiacion-del-Terrorismo.pdf` | notebooks 01, 02, 03 y pruebas de L2 y L3 |

## manuales/
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
