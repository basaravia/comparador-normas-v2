---
name: qa-eval-ia
description: Evalúa los componentes de IA del Comparador Normativo v2 con RAGAS: recuperación de candidatos (L3) y juez auditor (L4) contra el golden set de los MOCK, con el LLM real del stage como evaluador. Úsala al cerrar L3, L4 o L6, o cuando cambie un prompt, un modelo o un umbral.
---

# Evaluación de IA (RAGAS)

## Privacidad (obligatorio)
- `RAGAS_DO_NOT_TRACK=true` siempre (ya en `tests/conftest.py`).
- **Entorno propio**: `conda create -n comparador_eval python=3.11` + `pip install -r requirements-eval.txt` (RAGAS exige `openai<2`; la app usa `openai` 3.x). Las pruebas de evaluación van en `tests/eval/` con `@pytest.mark.eval` y se corren desde ese entorno; el cliente `ModelClient` funciona con ambas versiones de `openai`.
- **Nunca** Langfuse, ni callbacks o envíos a servicios externos: se procesan documentos de un banco. Los resultados se quedan en local (`comparador-dbx/qa/`).
- Modelo evaluador: el LLM real del stage, a través de `backend.llm.client.ModelClient` (RAGAS acepta un LLM propio con `llm_factory` o un wrapper personalizado) (Groq en sandbox, Foundry en mvp). Nada de claves de OpenAI directas.

## Golden set
- `tests/golden_pairs.csv` (docs/13), construido desde la matriz de `LEEME-MANUALES-MOCK.md` de la v1: norma LA/FT, artículos 31–48, contra MOCK-DEMO-01/02/03, con la cobertura esperada. Perfil de cada manual: MOCK-03 cumple, MOCK-01 parcial, MOCK-02 omite.

## Qué medir
- **L3 · Recuperación** (no necesita LLM evaluador):
  - `recall@candidatos = pares_golden_en_candidatos / total_golden`. **Umbral: ≥ 90 %** (docs/13);
  - además, precision@k y la lista de fallos con sus scores, para calibrar `SIM_THRESHOLD` y `K_SUBCHUNKS` por stage.
- **L4 · Juez**:
  - **acuerdo de marcas** con el golden set (MOCK-03 → A, MOCK-01 → L, MOCK-02 → R);
  - **citas verificadas** (toda cita es subcadena del texto fuente o queda marcada);
  - RAGAS `Faithfulness` y una métrica de rúbrica propia (`AspectCritic`/`RubricsScore`) para auditoría: ¿el comentario se sustenta en las citas? ¿los `elementos_faltantes` son reales?
  - casos adversariales de prompt injection (docs/14 #18).
- **L6 · Extremo a extremo**: las mismas métricas sobre la corrida completa, más tiempo y RAM.

## Cómo
- Pruebas con `@pytest.mark.eval` en `tests/eval/test_*.py`, usando las métricas de RAGAS.
- Resultados resumidos en `comparador-dbx/qa/eval-<hito>.md`: fecha, stage, modelo, métricas, umbral y fallos.
- Las métricas con LLM evaluador varían entre corridas: reporta el valor y el umbral, y repite si queda a menos de 5 puntos del umbral.
- Si una métrica de RAGAS exige algo que el proyecto no tiene (p. ej. contexto recuperado como lista), adapta los datos en la prueba; no cambies el backend.
