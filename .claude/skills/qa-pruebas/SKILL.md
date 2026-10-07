---
name: qa-pruebas
description: Escribe y ejecuta las pruebas del Comparador Normativo v2 (pytest) y mide el coverage de la lógica determinista (umbral 80 %). Úsala al cerrar un hito, cuando cambie código ya probado o cuando el usuario pida correr las pruebas.
---

# Pruebas y coverage

Desde `comparador-dbx/`, con el entorno del proyecto:
```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate comparador_v2
```

## 1. Estructura (crear si no existe)
- **Configuración**: `pytest.ini` con
  - `testpaths = tests`
  - `markers = integracion: usa los modelos reales del stage (gasta tokens)`
  - `addopts = -q`
- **`tests/conftest.py`**:
  - pone `RAGAS_DO_NOT_TRACK=true` antes de cualquier import;
  - añade `comparador-dbx/` al `sys.path`;
  - define una fixture `cliente` (el `ModelClient` real) **solo** para las pruebas de integración.
- **Archivos**: un `test_<módulo>.py` por módulo del backend (`test_validation.py`, `test_config.py`, …). Los datos de prueba pequeños van en `tests/datos/`. Los PDFs de prueba se generan en `tmp_path` con pymupdf, como en `notebooks/01_ingesta.ipynb`. Los MOCK están en `samples/`.

## 2. Qué probar (pirámide)
- **Unitarias, sin modelo** (la mayoría):
  - toda la lógica determinista;
  - valores límite (p. ej. `MAX_PAGES` y `MAX_PAGES + 1`, `SCAN_TEXT_RATIO` justo por encima y por debajo);
  - particiones de equivalencia y tablas de decisión (agregación de marcas, docs/09 §5);
  - casos hostiles: nombres con `..`, PDFs corruptos, marcas `<texto_*>`.
- **Las pruebas mínimas de docs/13**: `test_sectioner`, `test_aggregate`, `test_citations` y `test_excel`, cuando exista cada módulo.
- **Integración, `@pytest.mark.integracion`, con modelos reales**: el flujo del hito con el LLM y los embeddings del stage. Pocas y con aserciones robustas: el tipo de documento o la marca, no el texto exacto del modelo.
- **Nunca** simular el LLM, los embeddings ni FAISS (`CLAUDE.md`, regla 4).

## 3. Ejecutar
```bash
pytest -m "not integracion" --cov=backend --cov-report=term-missing   # unitarias + coverage
pytest -m integracion                                                # modelos reales (stage de config/.env)
```
- **Coverage**: el umbral es **80 %** sobre la lógica determinista. Si `backend/llm/client.py` solo se puede ejercitar con modelos reales, se excluye del porcentaje con `--cov-config` o `omit`, y la exclusión se anota en el reporte. No se excluye nada más sin justificarlo.
- **Una integración que falla por `429` de Groq** o por caída del servicio no es un defecto del código: se reintenta una vez y, si persiste, se reporta como bloqueo de entorno.

## 4. Reportar
Usa el formato del agente `qa-ia`. Copia las cifras **literalmente** de la salida de pytest: el product-owner y `implementacion/README.md` las citan.
