# 15 · Hoja de ruta — versión 2

No implementar en el MVP. Diseñar sin bloquear estas evoluciones.

- **Arquitectura 2B:** la App orquesta; extracción e indexación corren en Jobs de Databricks sobre clusters; resultados en Delta / Unity Catalog.
- **Persistencia:** volúmenes para PDFs; tablas para secciones, embeddings, pares y veredictos; historial de revisiones.
- **Canonicalización:** antes de embeber, el LLM extrae de cada sección la obligación o el control en forma canónica neutral (ej. "monitoreo mensual de transacciones inusuales"). Reduce la asimetría entre lenguaje deóntico de la norma y lenguaje operativo del manual; sube el recall.
- **OCR** para escaneados y PDF planos.
- **Cascada de cómputo:** hash → embeddings + léxico → cross-encoder → juez, con umbrales de tres bandas calibrados contra golden set etiquetado.
- **Edición del seccionado** en UI (fusionar y dividir) y evaluación conjunta de coberturas parciales.
- **Comparación de versiones** de una normativa (modificados, derogados, añadidos, renumerados).
