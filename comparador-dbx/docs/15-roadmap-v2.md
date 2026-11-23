# 15 · Hoja de ruta — versión 2

No implementar en el MVP. Diseñar sin bloquear estas evoluciones.

- **Arquitectura 2B:** la App orquesta; extracción e indexación corren en Jobs de Databricks sobre clusters; resultados en Delta / Unity Catalog.
- **Persistencia:** volúmenes para PDFs; tablas para secciones, embeddings, pares y veredictos; historial de revisiones.
  - **Persistencia que sobreviva a apagados (tablero V-15):** hoy un reinicio o apagado de la app borra todo (el PDF ni siquiera se guarda tras procesar). Para persistir de verdad haría falta un almacén fuera del contenedor: un volumen de Unity Catalog para los archivos y tablas Delta (o un SQL Warehouse) para secciones, marcas y resultados, indexados por el hash del correo; más un trabajo de limpieza por retención y reabrir los índices desde ahí. Requiere decidir qué se retiene y por cuánto con seguridad, y revisar la regla 8 de CLAUDE.md. Fuera del MVP.
- **Canonicalización:** antes de embeber, el LLM extrae de cada sección la obligación o el control en forma canónica neutral (ej. "monitoreo mensual de transacciones inusuales"). Reduce la asimetría entre lenguaje deóntico de la norma y lenguaje operativo del manual; sube el recall.
- **OCR** para escaneados y PDF planos.
- **Cascada de cómputo:** hash → embeddings + léxico → cross-encoder → juez, con umbrales de tres bandas calibrados contra golden set etiquetado.
- **Edición del seccionado** en UI (fusionar y dividir) y evaluación conjunta de coberturas parciales.
- **Comparación de versiones** de una normativa (modificados, derogados, añadidos, renumerados).
- **H · Conservar o reutilizar pares ya juzgados (pendiente de decisión del usuario; no descartada; esfuerzo L).** Hoy, al cancelar una comparación, el resultado parcial se descarta y volver a comparar rejuzga todo ([14](14-puntos-abiertos.md) #39). H haría que `juzgar_pares` reutilice en memoria los pares ya juzgados por (artículo, sección, ajustes), de modo que un cancelado o una nueva corrida no los repita (compatible con la regla 9). El aviso al cancelar pasaría a «Cancelada: se conservan los {N} pares ya resueltos y no se vuelven a evaluar si comparas de nuevo.» No habría papel de trabajo parcial: las marcas A/L/R/X/P son por artículo y se calculan al final.
