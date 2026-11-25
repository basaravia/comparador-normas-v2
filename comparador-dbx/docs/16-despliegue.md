# 16 · Despliegue en Databricks Apps

La app es un solo contenedor: FastAPI (`backend/main:app`, un worker) que sirve `frontend/dist`. Estado en memoria; el Excel descargado es la persistencia.

## Antes de desplegar
Elige variante: **Foundry** (`app.yaml`, pasos 2 y 3) o **Databricks Free** (`app.free.yaml`, sección «Despliegue en Databricks Free»).

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

## Despliegue en Databricks Free (modelos del workspace)
Free no incluye Foundry y el plan gratuito de Groq (200 000 tokens por día) no alcanza para una comparación completa. Esta variante usa los modelos que sirve el propio workspace, sin gasto, con `LLM_PROVIDER=databricks` y `EMB_PROVIDER=databricks`: LLM `databricks-gpt-oss-120b` y embeddings `databricks-qwen3-embedding-0-6b` (`DATABRICKS_LLM_ENDPOINT` y `DATABRICKS_EMB_ENDPOINT` en `config/defaults.env`).
- **`app.free.yaml`** no lleva secretos: la plataforma inyecta `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID` y `DATABRICKS_CLIENT_SECRET` (el service principal de la App pide su token OAuth y lo renueva solo). Databricks Apps solo despliega un archivo llamado `app.yaml` en la raíz del código: al subir, `app.free.yaml` se copia como `app.yaml`. Deja `TRUST_PROXY_IDENTITY=false` hasta la comprobación de S-21.
- **Recursos de la App:** dos `serving_endpoint` con permiso `CAN_QUERY` (los dos modelos de arriba); no lleva el recurso `foundry-token`. Ejemplo para crearla: `databricks apps create --json '{"name":"comparador-normativo","resources":[{"name":"llm","serving_endpoint":{"name":"databricks-gpt-oss-120b","permission":"CAN_QUERY"}},{"name":"embeddings","serving_endpoint":{"name":"databricks-qwen3-embedding-0-6b","permission":"CAN_QUERY"}}]}'`; luego `databricks workspace import-dir` del código (con `app.free.yaml` renombrado) y `databricks apps deploy --source-code-path`. La app debe estar con el cómputo activo antes de desplegar.
- **En local** con esos mismos modelos: `LLM_PROVIDER=databricks`, `EMB_PROVIDER=databricks`, `DATABRICKS_HOST` y `DATABRICKS_TOKEN` (token personal u OAuth del CLI, solo en `config/.env` o en el entorno; nunca en el repo).
- **Respaldo del LLM:** `LLM_FALLBACK=databricks,ollama` (en `config/stages/sandbox.env`) hace que, si Groq cae o llega a su límite diario, la misma llamada pase a Databricks Free y, de último, a Ollama local. Cada respaldo sin configurar se omite con un aviso. **Ollama:** crear una vez el modelo derivado con `ollama create comparador-qwen3-4b -f config/ollama/Modelfile.comparador` (contexto 8 192, salida 1 500; sin eso Ollama usa 4 096 y recorta el prompt). OpenRouter queda fuera de la cadena: se agrega a mano en `config/.env` (`LLM_FALLBACK=databricks,ollama,openrouter` y `OPENROUTER_API_KEY`) si el usuario lo decide.
- **Pruebas del despliegue (D-66):** `scripts/prueba_humo.py <URL> --perfil-databricks DEFAULT` hace un extremo a extremo con un **ejemplo reducido** (3 artículos × 3 secciones = 9 pares; salud con el LLM real, ejemplo, comparación y Excel; con `--pdf`, Docling) y `scripts/prueba_navegador.mjs <URL> --perfil-databricks DEFAULT --navegador /usr/bin/brave-browser` comprueba la interfaz con un navegador real (Brave por Playwright, perfil limpio; `playwright-core` no es dependencia del proyecto: `NODE_PATH` apunta al de la máquina).
- **Lotes de embeddings:** el endpoint de embeddings del workspace Free rechaza lotes grandes con 429 (REQUEST_LIMIT_EXCEEDED, por consultas por segundo): con 32 textos o más no responde y con 16 va sin rechazos (≈ 2 llamadas por segundo). `app.free.yaml` fija `EMB_BATCH=16` (el valor por defecto es 64). El cliente además espera y reintenta ante un 429 (`EMB_REINTENTOS_LIMITE`, `EMB_ESPERA_LIMITE_S`).
- **Particularidad:** este servicio exige la palabra «json» en el último mensaje del usuario cuando se pide formato JSON; el cliente la añade solo.
- **Medido con modelos reales (25 nov 2026):** comparación del ejemplo de punta a punta, 80 pares en 415 s, 0 errores, 0 respuestas 429; Excel generado. `SIM_THRESHOLD` se calibró para `qwen3-embedding` (P-03, golden set ARLAFT de 75 pares, la ley completa contra `MANUAL-ARLAFT-V14`): recall@candidatos **65,3 % a 0,50**, **72,0 % a 0,40** y 73,3 % a 0,30 (con `bge-m3` a 0,50: 74,7 %); a 0,40 hay 1 167 pares a juzgar (654 a 0,50; 1 338 a 0,30). `app.free.yaml` fija **0,40** (docs/14 #1).

## Comprobaciones
- `GET <url>/api/health` → `{"estado":"ok","llm":true}` (hace un ping real al LLM y a embeddings; se cachea 60 s).
- "Cargar ejemplo" → Selección → Comparar 2–3 artículos → Resultados → Descargar `.xlsx`.
- Con un PDF propio: tarda lo que tarde Docling (máximo `MAX_PAGES`=250 páginas y `MAX_MB`=20 MB; `DOCLING_TIMEOUT_S`=3000 s por documento).

## Hallazgos de la prueba en Databricks Free (19 oct 2026)
- **Carpeta del service principal:** al desplegar en modo `SNAPSHOT`, Databricks crea `/Users/<id-del-service-principal>/src` (copia del código). No la crea el notebook; al borrar la app se borra la carpeta. El código fuente sigue en la carpeta del usuario que despliega.
- **Subida al workspace:** se usa `ImportFormat.RAW` y los archivos vacíos (`__init__.py`) llevan un salto de línea, porque el workspace rechaza archivos vacíos. `output`, `documentos`, `notebooks`, `tests` y `.git` se excluyen solo en la raíz (`backend/output/` es código).
- **Identidad:** la App recibe `x-forwarded-email`, `x-forwarded-user` y `x-forwarded-access-token`. Se comprobó con el token OAuth del CLI; falta repetirlo desde el navegador. Con `TRUST_PROXY_IDENTITY=true` (apagada en `app.yaml` hasta la comprobación de abajo) la app separa las sesiones por `x-forwarded-email`; con la bandera apagada sigue con la cookie `session_id`.
- **Condición de despliegue pendiente (la bandera no se enciende sin esto):** comprobar desde el navegador, en Databricks, que una cabecera `x-forwarded-email` falsificada por el cliente llega **sobrescrita** por el proxy, y que la app **no responde fuera del proxy** (el puerto del contenedor no es alcanzable directamente). Si cualquiera falla, `TRUST_PROXY_IDENTITY` queda en `false`. La app no arranca con la bandera encendida si falta `DATABRICKS_APP_NAME` en el entorno.
- **Cachés globales:** la extracción de Docling (por hash del PDF) y los vectores del índice (por hash del texto) son del proceso, no de la sesión: sobreviven a «Quitar» y «Borrar todo» hasta que el proceso se reinicia. No contienen el PDF; sí texto de documentos procesados, en memoria.
- **Escritura en el workspace:** la App, con su service principal, escribe en su propia carpeta `/Workspace/Users/<id-del-service-principal>/`. No se usa: la regla 8 de CLAUDE.md (sin persistencia en servidor) se mantiene por decisión del usuario. No hay volumen de Unity Catalog disponible por ahora.
- **Límite de la Free:** 3 apps por workspace.
