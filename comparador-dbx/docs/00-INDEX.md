# Índice de la especificación

| # | Documento | Contenido |
|---|---|---|
| 01 | [Contexto y alcance](01-contexto-alcance.md) | Problema, objetivo del MVP, doble vía, MVP vs V2 |
| 02 | [Restricciones](02-restricciones.md) | Restricciones duras del entorno Databricks |
| 03 | [Arquitectura](03-arquitectura.md) | C4 nivel 1 y 2, flujo, componentes y stack |
| 04 | [Requerimientos](04-requerimientos.md) | Funcionales (RF) y no funcionales (RNF) |
| 05 | [Experiencia de usuario](05-ux.md) | Pantallas, comportamiento y mensajes de error |
| 06 | [Ingesta y metadatos](06-ingesta-metadatos.md) | Validación, escaneo, metadatos nativos y LLM |
| 07 | [Extracción y seccionado](07-extraccion-seccionado.md) | Docling, cascada de seccionado, esquema de sección |
| 08 | [Indexación semántica](08-indexacion.md) | Sub-chunks, embeddings, FAISS |
| 09 | [Motor de doble vía](09-motor-doble-via.md) | Candidatos, deduplicación, juez, citas, marcas |
| 10 | [Papel de trabajo](10-papel-de-trabajo.md) | Formato Excel del banco: hoja 1 y hoja 2 |
| 11 | [API](11-api.md) | Endpoints REST y sesión |
| 12 | [Estructura y configuración](12-estructura-config.md) | Árbol del repo, dependencias, variables |
| 13 | [Plan de hitos](13-plan-hitos.md) | H0–H6 con criterios de aceptación y pruebas |
| 14 | [Puntos abiertos](14-puntos-abiertos.md) | Decisiones a calibrar |
| 15 | [Hoja de ruta V2](15-roadmap-v2.md) | Fuera del MVP |

Prompts: [`backend/prompts/`](../backend/prompts/). Configuración: [`config/.env.example`](../config/.env.example).

Esta carpeta es la **especificación** (qué construir). Lo **implementado** (qué existe, cómo se usa y mediciones) vive aparte, en [`implementacion/`](../implementacion/README.md).
