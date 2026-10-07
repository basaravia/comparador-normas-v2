# documentos/

Carpeta local de **entrada**: lo que pongas aquí **no se versiona** (`.gitignore`), pero los notebooks y las pruebas lo leen.

```
documentos/
└── normas/     ← PDF de las normas reales
```

## normas/
Copia aquí los PDF de las normas (por ejemplo los de `Normativa2026/` del repo v1). Los notebooks esperan estos nombres:

| Archivo | Lo usan |
|---|---|
| `L1-XVI-cap-III.pdf`, `L1-XVI-cap-IV.pdf`, `L1-XVI-cap-V.pdf` | notebooks 01, 02, 03 y 05 |
| `Proyecto-de-Ley-Organica-Organica-para-Reprimir-y-Prevenir-el-Lavado-de-Activos-y-la-Financiacion-del-Terrorismo.pdf` | notebooks 01, 02, 03 y pruebas de L2 y L3 |

Los manuales MOCK (ficticios) **sí** están versionados, en `samples/`.

## Otra ubicación
Define `NORMAS_DIR` en `config/.env` (ruta absoluta, o relativa a `comparador-dbx/`):

```
NORMAS_DIR=/ruta/completa/a/mis/normas
```

En Databricks, define `NORMAS_DIR` como variable de entorno apuntando a donde subas los PDF.
