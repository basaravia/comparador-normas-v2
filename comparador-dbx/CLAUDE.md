# CLAUDE.md — Comparador Normativo de Doble Vía (MVP)

Lee este archivo completo al inicio de cada sesión. La especificación vive en `docs/`; empieza por `docs/00-INDEX.md`.

## Qué estamos construyendo
Una Databricks App que compara normativas regulatorias (Superintendencia de Bancos, protección de datos, etc.) contra manuales de control interno de un banco, en **doble vía**, y genera un **papel de trabajo de auditoría en Excel** con el formato del banco. La opera un **auditor no técnico**. Demo del MVP: **viernes 2 de octubre de 2026**.

## Reglas no negociables
1. **Reutilizar antes que crear.** El repo de referencia (`../../comparador-normativas-ec-v1`, rama `feature/v6-react-fastapi`, solo su `backend/`) ya tiene módulos probados de: extracción con Docling, chunking, vectorización y cliente de modelos (Groq / Foundry). Localízalos y adáptalos. Registra en `README.md` qué archivo de origen se reutilizó en cada módulo nuevo.
2. **No añadir dependencias** fuera de `docs/12-estructura-config.md` sin una línea de justificación en el commit.
3. **El modelo produce campos, el código produce formato.** El LLM solo devuelve JSON validado con Pydantic. Umbrales, preselecciones, agregación de marcas y armado del Excel son Python determinista.
4. **Modelos reales, nunca simulados.** El LLM, los embeddings (según el stage: DMR en dev, Groq + Ollama `bge-m3` en sandbox, Foundry en mvp) y el índice FAISS se usan reales en notebooks y pruebas de integración. Nada de dobles ni respuestas falsas para el LLM o la recuperación.
5. **Texto literal siempre.** El texto de normas y manuales nunca se parafrasea ni se genera. Toda cita del juez se verifica en Python contra el texto fuente (`docs/09-motor-doble-via.md` §4).
6. **Un solo proceso uvicorn (`--workers 1`).** El estado vive en memoria; varios workers rompen la sesión.
7. **Extracción con Docling en cola de un solo worker**, nunca en paralelo. `do_ocr=False`. El cómputo es Medium (~6 GB RAM) y Docling ya saturó la CPU en pruebas.
8. **Sin persistencia de infraestructura:** no hay volúmenes de Unity Catalog ni SQL Warehouse. Estado en memoria + `/tmp`. El Excel descargado es la persistencia.
9. **Cada par (artículo, sección de manual) se juzga exactamente una vez** (`docs/09-motor-doble-via.md` §2).
10. **El Excel se arma con pandas + openpyxl, cero tokens.**
11. **Mensajes al usuario en lenguaje de negocio.** Nunca trazas técnicas en pantalla.

## Cómo trabajar
- Implementa por hitos en el orden de `docs/13-plan-hitos.md`. No avances de hito sin cumplir su criterio de aceptación.
- **Backend primero, en local:** fase L con notebooks en los stages locales (dev: MacBook con DMR; sandbox: Raspberry con Groq + Ollama), luego despliegue en Databricks Free y la UI al final. Paso a paso.
- **Ramas cortas desde `main`** (GitHub flow; decisión del usuario, 6 oct 2026):
  - `main` es el tronco estable. Cada tarea va en una rama corta con prefijo de Conventional Commits: `feat/l2-seccionado`, `fix/...`, `test/...`, `docs/...`, `chore/...`.
  - Cada rama tiene **su propio worktree** junto al repo: `git worktree add -b <rama> ../wt-<rama-con-guiones> main`. Ningún agente trabaja en el worktree de otro.
  - Cada rama se integra en `main` cuando pasa `appsec`, `product-owner` y, si cierra un hito, `qa-ia`. Después se borran la rama (local y remota) y su worktree.
  - El trabajo de `qa-ia` va en su propia rama `test/...` y en su worktree; nunca se mezcla con la rama de la funcionalidad.
- **Versionado: Conventional Commits + SemVer 0.x por hito.**
  - Al integrar en `main` el cierre de un hito, se pone un tag anotado con notas de versión: `v0.1.0` = L0, `v0.2.0` = L1, … `v0.7.0` = L6.
  - Las correcciones posteriores van como parche `v0.x.y`. **`v1.0.0` = demo del MVP.**
- Commits pequeños; cita el criterio de aceptación del hito en el mensaje.
- **Antes de cada push**, el agente `product-owner` actualiza el tablero de avance (`tablero/datos.js`, se ve en `tablero/index.html`) y el cambio va en el push. El tablero refleja **todas** las actividades, también las canceladas o desestimadas: como el PO no ve el chat, el agente principal le pasa en el prompt lo discutido con el usuario desde la última actualización (aceptado, descartado o pospuesto, con motivo). **Solo el usuario desestima, modifica o cancela tareas**: ni el agente principal ni los subagentes lo hacen por su cuenta; se le propone y él decide.
  Después de cada actualización, el agente principal comprueba con `git status --porcelain` y `git diff --name-only` que **solo** cambió `comparador-dbx/tablero/datos.js` y que el diff de ese archivo solo toca literales dentro de `window.TABLERO = {...}`. Si cambió otro archivo, lo revierte y avisa al usuario (el permiso de edición del PO no tiene control técnico de ruta; decisión del usuario, 6 oct 2026).
- **Equipo:** el agente principal implementa los hitos de uno en uno, con el notebook como puerta de aprobación del usuario; `appsec`, `product-owner` y `qa-ia` revisan. El pool de tres desarrolladores de IA se retiró el 7 oct 2026 (rama `legacy/equipo-ia`).
- **Antes de cada commit con código** pasa el cambio por el agente `appsec` (seguridad) y el `product-owner` (plan).
- **Al cerrar cada hito** (y cuando cambie código ya probado), el agente `qa-ia` escribe y corre las pruebas: coverage **≥ 80 %** de la lógica determinista (`pytest -m "not integracion" --cov`), integración con modelos reales (`-m integracion`), RAGAS desde L3 (entorno propio `comparador_eval`), y actualiza `qa/trazabilidad.md`. Sin **APROBADO** de `qa-ia` el hito no se cierra. Después, el agente principal comprueba con git que `qa-ia` solo escribió en `tests/`, `qa/` y `pytest.ini`; si tocó otra cosa, lo revierte y avisa.
- **RAGAS** (evaluación de IA, `requirements-eval.txt`, entorno propio `comparador_eval` porque exige `openai<2`) siempre con `RAGAS_DO_NOT_TRACK=true`: ningún dato sale a servicios externos. No se usa Langfuse: necesita un servidor y no pueden salir documentos del banco. Un BLOQUEAR de `appsec` se corrige antes del commit; lo que marque como "Decisión del usuario: SÍ" se consulta con el usuario.
- **Documenta lo implementado** en `implementacion/README.md` (fuera de `docs/`, que es solo la spec) en el mismo commit: módulos, API pública, configuración, mediciones y diferencias con la spec. El agente `product-owner` revisa que ese doc y el código coincidan.
- **Documentos de entrada** (decisión del usuario, 7 oct 2026): las normas se leen de `documentos/normas/` (`NORMAS_DIR`, **no se versiona**) y los manuales de `documentos/manuales/` (`MANUALES_DIR`; los MOCK ficticios **sí** van en git). Notebooks, pruebas, scripts y la app obtienen la ruta con `carpeta_normas()` y `carpeta_manuales()` de `backend/config.py`; nunca con una ruta escrita en el código. Todo hito nuevo (L4, L6, D*, U*) mantiene esta regla. Ver `documentos/LEEME.md`.
- **Progreso y logs** (decisión del usuario, 8 oct 2026): todo proceso **largo o iterativo** (que pueda pasar de ~5 s o repetirse muchas veces: extracción, embeddings, lotes de llamadas al LLM, barridos) muestra una **barra de progreso** y un **log sencillo** que diga qué hace y cuánto tardó. Se usa `backend/core/progreso.py`: `configurar_logs()` al inicio del notebook y `with progreso("Docling · LA/FT", "pág") as cb:` para las funciones que aceptan `progreso(hechos, total)`; para un bucle simple, `tqdm(...)`. Toda función larga del backend recibe un `progreso` opcional y registra con `log.info` el inicio y el final. Aplica a cada hito nuevo (L4, L6, D*, U*) y a sus notebooks.
- Los valores marcados `[CALIBRAR]` van en configuración (`config/defaults.env`), nunca hardcodeados.
- Los prompts viven en `backend/prompts/*.md` y se cargan desde archivo. No los incrustes en el código.
- Si una decisión no está en `docs/`, pregunta antes de inventarla. Las decisiones abiertas están en `docs/14-puntos-abiertos.md`.

## Convenciones
- **DEBE**: obligatorio del MVP. **DEBERÍA**: recomendado, posponible avisando. **[CALIBRAR]**: valor inicial ajustable. **[V2]**: fuera del MVP, no bloquear.
- Python 3.11, tipado, Pydantic v2. Frontend React 18 + Vite + TypeScript.
- Idioma de la UI y de los mensajes: español.

## Comandos (ajustar cuando exista el repo)
```bash
# backend local
uvicorn backend.main:app --reload --port 8000
# frontend
cd frontend && npm install && npm run dev      # desarrollo
cd frontend && npm run build                   # genera frontend/dist para desplegar
# pruebas (desde comparador-dbx/)
pytest -m "not integracion" --cov=backend   # unitarias + coverage (umbral 80 %)
pytest -m integracion                        # modelos reales del stage
```
