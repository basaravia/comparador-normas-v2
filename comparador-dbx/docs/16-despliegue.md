# 16 · Despliegue en Databricks Apps

La app es un solo contenedor: FastAPI (`backend/main:app`, un worker) que sirve `frontend/dist`. Estado en memoria; el Excel descargado es la persistencia.

## Antes de desplegar
1. **Interfaz compilada:** `cd frontend && npm install && npm run build` (el `dist/` ya viene versionado; recompilar solo si cambia el código del frontend).
2. **Azure AI Foundry:** edita `app.yaml` y cambia los `REEMPLAZAR-…` por el endpoint, la versión de API y los nombres de los deployments del LLM y de embeddings. **No pegues el token en el archivo**: el repo es público.
3. **Token como secreto:** en la consola de Databricks crea un secreto (scope + clave) con el token de Foundry y agrégalo a la App como recurso con la clave `foundry-token` (el `valueFrom` de `app.yaml`).
4. **Umbral de similitud:** `SIM_THRESHOLD` vale 0,30 por defecto; con `text-embedding-3-large` hay que recalibrarlo (docs/14 #1). Se cambia con una variable de entorno en `app.yaml`.

## Desplegar (notebook `notebooks/07_desplegar.ipynb`)
El código está directo en el notebook; los parámetros son widgets: `app`, `secreto_scope`, `secreto_clave` y `ruta` (opcional). Se ejecuta de arriba abajo.

- Identifica solo al usuario que ejecuta (`current_user.me()`) y sube el código a **su** carpeta, `/Workspace/Users/<tu-correo>/<app>`, nunca a la raíz del workspace. Si indicas `ruta`, debe estar dentro de esa carpeta o el notebook se detiene.
- Sube el código sin `node_modules`, `output`, `documentos`, `notebooks`, `tests` ni archivos `.env*`, `.pem` o `.key`.
- `apps.get` valida si la app existe (la crea o actualiza sus recursos) y le da un recurso secreto `foundry-token` con permiso **READ** sobre `secreto_scope`/`secreto_clave` (reemplaza el paso 3 manual de arriba).
- Si la app está detenida (la Free las apaga y no admite despliegues), el notebook la inicia con `start_and_wait` antes de desplegar.
- `deploy_and_wait` (`SNAPSHOT`) despliega y el notebook imprime la URL.

La App instala `requirements.txt` sola. Docling descarga sus modelos la primera vez (necesita salida a internet del contenedor); si la extracción en vivo no es estable, usa **Cargar ejemplo** (no ejecuta Docling).

## Comprobaciones
- `GET <url>/api/health` → `{"estado":"ok","llm":true}` (hace un ping real al LLM y a embeddings; se cachea 60 s).
- "Cargar ejemplo" → Selección → Comparar 2–3 artículos → Resultados → Descargar `.xlsx`.
- Con un PDF propio: tarda lo que tarde Docling (máximo `MAX_PAGES`=250 páginas y `MAX_MB`=20 MB; `DOCLING_TIMEOUT_S`=3000 s por documento).

## Hallazgos de la prueba en Databricks Free (19 oct 2026)
- **Carpeta del service principal:** al desplegar en modo `SNAPSHOT`, Databricks crea `/Users/<id-del-service-principal>/src` (copia del código). No la crea el notebook; al borrar la app se borra la carpeta. El código fuente sigue en la carpeta del usuario que despliega.
- **Subida al workspace:** se usa `ImportFormat.RAW` y los archivos vacíos (`__init__.py`) llevan un salto de línea, porque el workspace rechaza archivos vacíos. `output`, `documentos`, `notebooks`, `tests` y `.git` se excluyen solo en la raíz (`backend/output/` es código).
- **Identidad:** la App recibe `x-forwarded-email`, `x-forwarded-user` y `x-forwarded-access-token`. Se comprobó con el token OAuth del CLI; falta repetirlo desde el navegador. Hoy la app no usa el correo: separa por la cookie `session_id`.
- **Escritura en el workspace:** la App, con su service principal, escribe en su propia carpeta `/Workspace/Users/<id-del-service-principal>/`. No se usa: la regla 8 de CLAUDE.md (sin persistencia en servidor) se mantiene por decisión del usuario. No hay volumen de Unity Catalog disponible por ahora.
- **Límite de la Free:** 3 apps por workspace.
