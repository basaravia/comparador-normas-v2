# 16 · Despliegue en Databricks Apps

La app es un solo contenedor: FastAPI (`backend/main:app`, un worker) que sirve `frontend/dist`. Estado en memoria; el Excel descargado es la persistencia.

## Antes de desplegar
1. **Interfaz compilada:** `cd frontend && npm install && npm run build` (el `dist/` ya viene versionado; recompilar solo si cambia el código del frontend).
2. **Azure AI Foundry:** edita `app.yaml` y cambia los `REEMPLAZAR-…` por el endpoint, la versión de API y los nombres de los deployments del LLM y de embeddings. **No pegues el token en el archivo**: el repo es público.
3. **Token como secreto:** en la consola de Databricks crea un secreto (scope + clave) con el token de Foundry y agrégalo a la App como recurso con la clave `foundry-token` (el `valueFrom` de `app.yaml`).
4. **Umbral de similitud:** `SIM_THRESHOLD` vale 0,30 por defecto; con `text-embedding-3-large` hay que recalibrarlo (docs/14 #1). Se cambia con una variable de entorno en `app.yaml`.

## Desplegar (desde `comparador-dbx/`)
```bash
databricks auth login --host https://<workspace>.cloud.databricks.com   # solo si el perfil venció
databricks apps create comparador-normativo                              # una sola vez
databricks sync . /Workspace/Users/<tu-correo>/comparador-normativo --exclude node_modules --exclude output --exclude documentos --exclude notebooks
databricks apps deploy comparador-normativo --source-code-path /Workspace/Users/<tu-correo>/comparador-normativo
databricks apps get comparador-normativo        # URL y estado
```
La App instala `requirements.txt` sola. Docling descarga sus modelos la primera vez (necesita salida a internet del contenedor); si la extracción en vivo no es estable, usa **Cargar ejemplo** (no ejecuta Docling).

## Comprobaciones
- `GET <url>/api/health` → `{"estado":"ok","llm":true}` (hace un ping real al LLM y a embeddings; se cachea 60 s).
- "Cargar ejemplo" → Selección → Comparar 2–3 artículos → Resultados → Descargar `.xlsx`.
- Con un PDF propio: tarda lo que tarde Docling (máximo `MAX_PAGES` páginas y `MAX_MB` MB).
