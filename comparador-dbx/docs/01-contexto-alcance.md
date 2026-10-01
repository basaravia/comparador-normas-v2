# 01 · Contexto y alcance

## Problema
En el entorno bancario, auditoría verifica manualmente si los manuales internos de control implementan las obligaciones emitidas por los entes reguladores (Superintendencia de Bancos, Superintendencia de Compañías, autoridad de protección de datos, entre otros). Normas y manuales rara vez se citan directamente: el manual **parafrasea u operacionaliza** la obligación. El núcleo del problema es la **correspondencia semántica**, no la búsqueda de referencias textuales.

Ejemplo: un artículo de la Ley Orgánica de Protección de Datos consagra el derecho del cliente a no ser expuesto en su imagen; el manual implementa una capa automatizada y validada que despersonaliza la imagen para que nunca se persista ni se filtre. Lenguaje distinto, misma obligación.

## Objetivo del MVP
Entregar el **viernes 2 de octubre de 2026** una Databricks App funcional donde un auditor, sin asistencia técnica:
1. carga normativas y manuales,
2. elige qué secciones comparar contra cuáles,
3. ejecuta un análisis de doble vía,
4. descarga un papel de trabajo en Excel con el formato del banco y evidencia trazable de cada veredicto.

## Doble vía
| Vía | Pregunta | Resultado |
|---|---|---|
| Vía 1 · Normativa → Manual | ¿Qué obligaciones de la norma cubre el manual y en qué grado? | Marca por artículo (A, L, R, X, P) con cita y razonamiento. Identifica incumplimientos y riesgos. |
| Vía 2 · Manual → Normativa | ¿A qué obligación responde cada control del manual? | Relación control–obligación y controles sin base normativa identificada. |

Varias normas contra varios manuales.

## Alcance: MVP vs V2
| Capacidad | MVP | V2 |
|---|---|---|
| Tipos de PDF | Solo PDF con texto nativo; escaneados rechazados con mensaje claro | OCR para escaneados y PDF planos |
| Cómputo | Todo en el contenedor de la App | Extracción pesada en Jobs; la App orquesta |
| Persistencia | Ninguna; el Excel es la persistencia | Delta / Unity Catalog, volúmenes, historial |
| Representación | Embeddings del texto de sub-chunks | Canonicalización de obligaciones y controles |
| Ranking | Embeddings → juez LLM | Cascada con cross-encoder y umbrales calibrados |
| Seccionado | Automático con bandera de "seccionado incierto" | Corrección manual (fusionar/dividir) |
