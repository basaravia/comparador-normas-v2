---
name: qa-trazabilidad
description: Mantiene la matriz de trazabilidad del Comparador Normativo v2 entre requisitos (RF/RNF de docs/04), criterios de aceptación de los hitos (docs/13) y las pruebas que los verifican. Úsala al cerrar un hito o cuando el product-owner necesite saber qué está verificado.
---

# Matriz de trazabilidad

Archivo: `comparador-dbx/qa/trazabilidad.md`. Lo escribe el agente `qa-ia` y lo lee el `product-owner` para el tablero.

## Fuentes
- **Requisitos**: tablas RF-01 a RF-16 y RNF-01 a RNF-12 de `comparador-dbx/docs/04-requerimientos.md`.
- **Criterios**: el criterio de aceptación de cada hito en `comparador-dbx/docs/13-plan-hitos.md`.
- **Implementado**: `comparador-dbx/implementacion/README.md`.
- **No hay historias de usuario** (decisión del usuario): no las inventes.

## Formato
Dos tablas.

1. **Requisitos**
   - Columnas: `ID | Requisito (resumen) | Prioridad | Hito | Pruebas | Estado`.
   - Estado: `verificado` (hay prueba y pasa), `falla` (hay prueba y no pasa), `parcial` (cubre solo una parte; di cuál), `sin prueba` (hay código pero no se prueba), `pendiente` (su hito aún no llega).
   - Pruebas: `tests/test_x.py::test_y`, o el notebook y la celda si el criterio se verifica en un notebook.
2. **Criterios de aceptación por hito**
   - Columnas: `Hito | Criterio | Evidencia (prueba o notebook) | Estado`.

Al final:
- **resumen**: N de M RF/RNF verificados y N de M criterios;
- **coverage** de la última corrida;
- **fecha** y **commit**.

## Reglas
- Un requisito solo es `verificado` si una prueba lo comprueba y pasa en la última corrida. Que el código exista no basta.
- Los RNF que no se prueban con pytest se verifican con evidencia concreta: rendimiento (RNF-11) con las mediciones de un notebook, seguridad (RNF-12) con el reporte de `appsec`. Cita la fuente.
- No se borran filas: si un requisito deja de aplicar, lo decide el usuario y se anota.
