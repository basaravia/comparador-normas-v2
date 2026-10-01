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
cp comparador-dbx/config/.env.example comparador-dbx/config/.env   # y rellenar GROQ_API_KEY
ollama pull bge-m3                            # embeddings locales

# ejecutar un notebook de punta a punta desde la terminal
cd comparador-dbx/notebooks
jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.kernel_name=comparador_v2 00_modelos.ipynb
```

## Configuración

Precedencia: **variable de entorno** (en Databricks, `app.yaml`) > **`config/.env`** (local, con secretos, ignorado por git) > **`config/.env.example`** (valores iniciales, versionado).

El código **no tiene valores por defecto**: todo valor `[CALIBRAR]` vive solo en `config/.env.example`. Para cambiar un umbral se edita ese archivo o se sobrescribe en `config/.env`.

Variables que añadió la implementación a las de la spec (docs/12): `LLM_PROVIDER`, `EMB_PROVIDER`, `GROQ_*`, `OLLAMA_BASE_URL`, `OLLAMA_EMB_MODEL`, `OLLAMA_LLM_MODEL`, `FOUNDRY_AI_*`, `LLM_TEMPERATURE`, `LLM_TIMEOUT_S`, `CITATION_SHOW_MIN`, `COLOR_PRIMARIO` y `COLOR_FONDO`.

---

## L0 · Base

**Criterio (docs/13):** una llamada al LLM devuelve JSON válido y un lote de embeddings sale normalizado L2, con Groq + `bge-m3`. **Cumplido.**

### Módulos

| Archivo | Responsabilidad | Uso |
|---|---|---|
| `backend/config.py` | Lee la configuración (`settings`), carga prompts y oculta secretos | `from backend.config import settings, cargar_prompt, redact` |
| `backend/core/errors.py` | Errores del dominio, cada uno con código `ERR-*` y mensaje de negocio | `err.para_usuario()` → `{"codigo", "mensaje"}` para la pantalla |
| `backend/llm/client.py` | Cliente único de modelos (SDK `openai`) para Groq, Ollama y Foundry | `ModelClient().chat_json(...)`, `.embed(...)`, `.ping()` |

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

| Variable | Desarrollo | Demo |
|---|---|---|
| `LLM_PROVIDER` | `groq` → `openai/gpt-oss-120b` (también admite `ollama` → `OLLAMA_LLM_MODEL`, sin usar por ahora) | `foundry` → `FOUNDRY_AI_DEPLOYMENT` (`AzureOpenAI`) |
| `EMB_PROVIDER` | `ollama` → `bge-m3` (dim 1024) | `foundry` → `FOUNDRY_AI_EMBED_DEPLOYMENT` |

La ruta de Foundry está implementada pero **sin probar**: se valida en la fase Demo, cuando haya credenciales.

### Mediciones (Raspberry, 1 oct 2026)

Salidas de la última ejecución de `notebooks/00_modelos.ipynb`:

| Medida | Valor |
|---|---|
| Latencia de Groq `gpt-oss-120b` | 0,4–0,8 s por llamada corta (media 0,6 s); la primera, el ping, ~5,7 s |
| Embeddings `bge-m3` en la Raspberry | 6,7 textos/s (67 textos en 10,0 s, 2 lotes) |
| Similitud con `bge-m3` | relacionado 0,753 · **no relacionado 0,499** |

Observación fuera del notebook: con Ollama en frío, la primera llamada de embeddings tarda ~15 s porque carga el modelo en memoria.

### Diferencias con la spec y decisiones técnicas

- **`SIM_THRESHOLD=0.30` no sirve con `bge-m3`**: un par sin relación ya supera 0,30. Se calibra en L3 (docs/14 #1).
- Se descartó el secret scope de la v6 (`databricks-sdk`): en Databricks Apps el token llega como variable de entorno (`valueFrom`).
- Docs/12 nombra `jupyter` para desarrollo; se instalan solo sus componentes `ipykernel` y `nbconvert` (`requirements-dev.txt`).

### Origen (repo de referencia v6)

Ver la tabla de módulos reutilizados en [`README.md`](../README.md).
