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
- Commits pequeños; cita el criterio de aceptación del hito en el mensaje.
- **Antes de cada commit con código** pasa el cambio por el agente `appsec` (seguridad) y el `product-owner` (plan). Un BLOQUEAR de `appsec` se corrige antes del commit; lo que marque como "Decisión del usuario: SÍ" se consulta con el usuario.
- **Documenta lo implementado** en `implementacion/README.md` (fuera de `docs/`, que es solo la spec) en el mismo commit: módulos, API pública, configuración, mediciones y diferencias con la spec. El agente `product-owner` revisa que ese doc y el código coincidan.
- Los valores marcados `[CALIBRAR]` van en configuración (`config/.env.example`), nunca hardcodeados.
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
# pruebas
pytest -q
```
