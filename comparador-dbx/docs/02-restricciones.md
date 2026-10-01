# 02 · Restricciones del entorno

Restricciones **duras**. Condicionan toda la arquitectura del MVP.

| Restricción | Implicación de diseño |
|---|---|
| Despliegue como **Databricks App**; backend Python, frontend React | FastAPI sirve la API y el build estático de React desde un único contenedor |
| Todo el flujo end-to-end vive en Databricks | Docling corre dentro del contenedor; modelos en Foundry |
| **Sin volúmenes** de Unity Catalog ni **SQL Warehouse** | Sin persistencia: memoria + filesystem efímero (`/tmp` / directorio de la app). Un reinicio pierde la sesión |
| Cómputo **Medium (~6 GB RAM)**; Docling llevó la CPU casi al tope en la prueba previa | Extracción en cola de **1 worker**, OCR desactivado, hilos acotados, cada PDF se extrae una vez por sesión (caché SHA-256) |
| Paquete de la app de **10 MB** como máximo | Solo código, `frontend/dist` y `samples/` livianos; nada de PDFs grandes ni modelos |
| Documentos de hasta **~100 páginas** | Límite duro: 100 páginas y 20 MB por archivo; FAISS plano en memoria basta |
| Opera un **auditor**, no el arquitecto | UI mínima, progreso visible, errores en lenguaje de negocio, ejemplos precargados |
| Modelos en **Azure AI Foundry**, llamados directo como en la v1 | GPT-5.6 (juez, metadatos, conclusión) y text-embedding-3-large en la demo; Groq + Ollama en desarrollo. Proveedor por configuración ([14](14-puntos-abiertos.md) punto 14) |

> **Importante — artefactos de Docling.** Docling descarga sus modelos (~1,5 GB, desde `huggingface.co`) en la primera ejecución. **No caben en el paquete de la app** (límite de 10 MB, ver [14](14-puntos-abiertos.md) punto 16), así que el contenedor necesita salida a internet. `DOCLING_ARTIFACTS` queda como opción para entornos donde sí haya un directorio local. Verificar en D1.

> **Importante — frontend.** Compilar React localmente (`npm run build`) y desplegar `frontend/dist`. El contenedor no debe depender de npm al arrancar.
