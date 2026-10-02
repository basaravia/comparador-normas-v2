# Implementación (documento vivo)

Qué está construido **de verdad**, hito por hito. La especificación en [`docs/`](../docs/00-INDEX.md) dice qué hay que construir; esta carpeta dice qué existe, cómo se usa y qué se aprendió al medirlo. Se actualiza **en el mismo commit** que cierra o cambia un hito.

Si algo de aquí contradice a la especificación, manda la especificación y la diferencia se anota en "Diferencias con la spec" del hito correspondiente.

## Estado

| Hito | Estado | Rama · commit | Notebook |
|---|---|---|---|
| L0 · Base | ✅ Cumplido | `feat/fase-l-local` · `feat(L0): …` | `notebooks/00_modelos.ipynb` |
| L1 · Ingesta | Pendiente | — | — |
| L2 · Seccionado | Pendiente | — | — |
| L3 · Recuperación | Pendiente | — | — |
| L4 · Juez | Pendiente | — | — |
| L5 · Papel | Pendiente | — | — |
| L6 · Extremo a extremo | Pendiente | — | — |

## Cómo correrlo en local

```bash
conda activate comparador_v2                  # Python 3.11, igual que Databricks
pip install -r comparador-dbx/requirements-dev.txt
# config/.env (ignorado por git): solo el stage y los secretos, p. ej.
#   STAGE=sandbox            # dev (MacBook, DMR) | sandbox (Raspberry) | mvp (Databricks)
#   GROQ_API_KEY=gsk_...     # solo sandbox
ollama pull bge-m3                            # sandbox: embeddings locales
# dev: los modelos de config/stages/dev.env deben estar en Docker Desktop → Models

# ejecutar un notebook de punta a punta desde la terminal
cd comparador-dbx/notebooks
jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.kernel_name=comparador_v2 00_modelos.ipynb
```

## Stages

| `STAGE` | Máquina | LLM | Embeddings | Archivo |
|---|---|---|---|---|
| `dev` | MacBook con Docker Desktop | DMR `ai/qwen3.5:9B-UD-Q4_K_XL` | DMR `ai/granite-embedding-multilingual` | `config/stages/dev.env` |
| `sandbox` | Raspberry Pi | Groq `openai/gpt-oss-120b` | Ollama `bge-m3` | `config/stages/sandbox.env` |
| `mvp` | Cluster Databricks | Foundry (GPT-5.6) | Foundry (`text-embedding-3-large`) | `config/stages/mvp.env` |

Los archivos de stage solo tienen proveedores y modelos, **nunca secretos**: se versionan. Cada modelo de embeddings tiene su dimensión y su escala de similitud, así que `SIM_THRESHOLD` se calibra por stage y los índices FAISS no se mezclan entre stages.

## Configuración

Precedencia: **variable de entorno** (en Databricks, `app.yaml` o la celda del notebook) > **`config/.env`** (local: `STAGE` y secretos, ignorado por git) > **`config/stages/<STAGE>.env`** > **`config/.env.example`** (valores iniciales, versionado).

El código **no tiene valores por defecto**: todo valor `[CALIBRAR]` vive solo en `config/.env.example`. Para cambiar un umbral se edita ese archivo o se sobrescribe en `config/.env`.

Variables que añadió la implementación a las de la spec (docs/12): `LLM_PROVIDER`, `EMB_PROVIDER`, `GROQ_*`, `OLLAMA_BASE_URL`, `OLLAMA_EMB_MODEL`, `OLLAMA_LLM_MODEL`, `STAGE`, `FOUNDRY_AI_*`, `FOUNDRY_OMIT_TEMPERATURE`, `DMR_BASE_URL`, `DMR_LLM_MODEL`, `DMR_EMB_MODEL`, `LLM_TEMPERATURE`, `LLM_TIMEOUT_S`, `CITATION_SHOW_MIN`, `COLOR_PRIMARIO` y `COLOR_FONDO`.

### Credenciales en Databricks

Solo los `*_KEY` y `*_TOKEN` son secretos. El resto (endpoint, versión de la API, deployments) son parámetros normales.

| Dónde corre | De dónde sale el token de Foundry |
|---|---|
| Local (dev y sandbox) | `config/.env` (ignorado por git): `GROQ_API_KEY` en sandbox; dev con DMR no necesita clave |
| **Notebook en el entorno de la demo** | `dbutils.secrets.get(scope=..., key="foundry_ai_token")`, en una **línea comentada** de cada notebook que se descomenta allí junto con los parámetros de Foundry |
| **Databricks Apps** (fase D) | Recurso Secret de la app, inyectado con `valueFrom: foundry_ai_token` en `app.yaml`, igual que en la v6 |

El código no lee secretos por su cuenta: todo llega como variable de entorno, que gana a `config/.env`. En Databricks no hay Ollama, así que allí `EMB_PROVIDER=foundry` (docs/14 #14).

---

## L0 · Base

**Criterio (docs/13):** una llamada al LLM devuelve JSON válido y un lote de embeddings sale normalizado L2, con Groq + `bge-m3`. **Cumplido.**

### Módulos

| Archivo | Responsabilidad | Uso |
|---|---|---|
| `backend/config.py` | Lee la configuración (`settings`), carga prompts y oculta secretos | `from backend.config import settings, cargar_prompt, redact` |
| `backend/core/errors.py` | Errores del dominio, cada uno con código `ERR-*` y mensaje de negocio | `err.para_usuario()` → `{"codigo", "mensaje"}` para la pantalla |
| `backend/llm/client.py` | Cliente único de modelos (SDK `openai`) para Groq, Ollama, Docker Model Runner y Foundry | `ModelClient().chat_json(...)`, `.embed(...)`, `.ping()` |

### API pública

- **`settings`**: objeto inmutable con todas las variables de `config/.env.example`, salvo `OMP_NUM_THREADS`, que lee directamente el runtime (torch/Docling). `settings.publico()` devuelve la configuración con los secretos como `***`.
- **`cargar_prompt(nombre) -> (sistema, usuario)`**: lee `backend/prompts/<nombre>.md` y lo separa por `# SISTEMA` / `# USUARIO`.
- **`redact(texto)`**: reemplaza los secretos configurados y las claves con formato conocido (`sk-`, `gsk_`, `dapi`) por `***`. Se usa antes de escribir en los logs.
- **`ModelClient.chat_json(sistema, usuario, esquema)`**: pide JSON (`response_format=json_object`) y lo valida con el modelo Pydantic `esquema`. Si no valida, reintenta **una vez** adjuntando los errores. Si vuelve a fallar, lanza `LLMOutputError`.
- **`ModelClient.embed(textos) -> np.ndarray`**: matriz `float32` `(n, dim)`, en lotes de `EMB_BATCH` y con cada fila de norma 1.
- **`ModelClient.ping() -> dict`**: una llamada mínima real a cada modelo, con `ok` y `ms`. Base para `/api/health` (D0).

### Errores

| Clase | Código | Efecto | Cuándo |
|---|---|---|---|
| `LLMUnavailableError` | ERR-LLM-001 | Aborta la corrida | Conexión, timeout, 5xx o límite de tasa con los reintentos agotados, o error desconocido |
| `ProviderConfigError` | ERR-CFG-001 | Aborta antes de gastar | Falta una variable, la clave es inválida o el modelo no existe |
| `LLMOutputError` | ERR-LLM-010 | Degrada la fila (`requiere_revision`) | JSON inválido tras el reintento |

Los reintentos ante 429/5xx los hace el SDK `openai` (`max_retries=LLM_RETRIES`, backoff exponencial).

### Proveedores

| Variable | dev | sandbox | mvp |
|---|---|---|---|
| `LLM_PROVIDER` | `dmr` → `DMR_LLM_MODEL` | `groq` → `openai/gpt-oss-120b` | `foundry` → `FOUNDRY_AI_DEPLOYMENT` (`AzureOpenAI`, solo el host del endpoint; sin `temperature` si `FOUNDRY_OMIT_TEMPERATURE=true`) |
| `EMB_PROVIDER` | `dmr` → `DMR_EMB_MODEL` | `ollama` → `bge-m3` (dim 1024) | `foundry` → `FOUNDRY_AI_EMBED_DEPLOYMENT` |

También admite `LLM_PROVIDER=ollama` (`OLLAMA_LLM_MODEL`), sin usar en ningún stage por ahora.

**Docker Model Runner (`dmr`)**: alternativa local a Ollama para el LLM o los embeddings (`DMR_BASE_URL`, `DMR_LLM_MODEL`, `DMR_EMB_MODEL`). Comparte el código de Ollama: la API es compatible con OpenAI y no pide clave. **Sin probar**: se valida en la MacBook (stage `dev`); DMR no está instalado en la Raspberry. Si se usa para embeddings con un modelo distinto de `bge-m3`, cambia la dimensión: los índices FAISS de proveedores distintos no se mezclan y hay que reindexar.

La ruta de Foundry está implementada pero **sin probar**: se valida corriendo `00_modelos.ipynb` en el entorno de la demo, descomentando la celda de Foundry.

### Mediciones (Raspberry, 1 oct 2026)

Stage sandbox. Salidas de la última ejecución de `notebooks/00_modelos.ipynb`:

| Medida | Valor |
|---|---|
| Latencia de Groq `gpt-oss-120b` | Última corrida: 0,6–0,7 s (media 0,6 s); el primer ping, ~5,7 s. Varía con la carga del plan gratuito (en una corrida anterior, media de 3,1 s) |
| Embeddings `bge-m3` en la Raspberry | Última corrida: 8,5 textos/s (67 textos en 7,9 s, 2 lotes); entre 6,7 y 8,5 en corridas anteriores |
| Similitud con `bge-m3` | relacionado 0,753 · **no relacionado 0,499** |

Observación fuera del notebook: con Ollama en frío, la primera llamada de embeddings tarda ~15 s porque carga el modelo en memoria.

### Diferencias con la spec y decisiones técnicas

- **`SIM_THRESHOLD=0.30` no sirve con `bge-m3`**: un par sin relación ya supera 0,30. Se calibra en L3 (docs/14 #1).
- Se descartó el secret scope de la v6 (`databricks-sdk`): en Databricks Apps el token llega como variable de entorno (`valueFrom`).
- Docs/12 nombra `jupyter` para desarrollo; se instalan solo sus componentes `ipykernel` y `nbconvert` (`requirements-dev.txt`).

### Seguridad (auditoría inicial del agente `appsec`)

Veredicto: **OBSERVACIONES**, sin bloqueos. `bandit` y `pip-audit` sin hallazgos; sin secretos en archivos ni en el historial.

Corregido en L0:
- Prompts `juez.md` y `clasificador.md`: el texto de los documentos va entre marcas (`<texto_articulo>`, `<texto_seccion>`, `<texto_documento>`) y el SISTEMA indica que es dato, no instrucción (prompt injection, OWASP LLM01).
- `chat_json` no envía ni registra fragmentos de la respuesta del modelo (`include_input=False`); `LLMOutputError` solo informa la longitud.
- `ping()` ya no devuelve el detalle técnico: va solo al log (docs/05).
- Foundry exige `https://` en el endpoint.

Pendiente, por fase:
- **L1/L4:** al rellenar los prompts, sustituir las variables en una sola pasada y quitar del texto las marcas `<texto_*>` (que un documento no pueda cerrar el delimitador). Validar `%PDF`, `MAX_MB` y `MAX_PAGES` antes de Docling y sanear el nombre del archivo en `/tmp`.
- **L4:** chequeo de frases dirigidas al evaluador → `requiere_revision` (decisión del usuario, docs/14 #18).
- **L5:** neutralizar formula injection en todas las celdas de texto del Excel (CWE-1236).
- **D0:** `/api/health` sin detalle técnico y con caché corta (el ping gasta tokens); `cargar_prompt` nunca con entrada del usuario.
- **V2:** fijar las dependencias transitivas (lock).

### Origen (repo de referencia v6)

Ver la tabla de módulos reutilizados en [`README.md`](../README.md).
