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
Los manuales MOCK (`MOCK-DEMO-01/02/03.pdf`) son ficticios y **sí** están versionados. Un manual real del banco no se sube a git: guárdalo fuera de esta carpeta (por ejemplo en `NORMAS_DIR` o en otra ruta local).

## Otra ubicación
Define `NORMAS_DIR` en `config/.env` (ruta absoluta, o relativa a `comparador-dbx/`):

```
NORMAS_DIR=/ruta/completa/a/mis/normas
```

En Databricks, define `NORMAS_DIR` como variable de entorno apuntando a donde subas los PDF.
