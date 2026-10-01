# 03 · Arquitectura

## C4 nivel 1 — Contexto del sistema

Un único actor humano (auditor) usa la App desde el navegador con autenticación de Databricks. En runtime hay una sola dependencia externa: el **AI Gateway de Databricks**, que enruta a **Azure AI Foundry**. El repo de GitHub solo interviene en tiempo de construcción.

```mermaid
flowchart LR
    auditor(["👤 Auditor<br/><i>Usuario de negocio, no técnico.<br/>Sube PDFs, selecciona secciones,<br/>revisa y descarga el papel</i>"])
    app["<b>Comparador Normativo</b><br/>[Databricks App]<br/>Ingesta, seccionado, recuperación semántica,<br/>juez de doble vía y papel de trabajo"]
    gw["<b>AI Gateway</b><br/>[Servicio Databricks]<br/>Serving endpoints registrados"]
    az["<b>Azure AI Foundry</b><br/>[Sistema externo]<br/>GPT-5.6 · text-embedding-3-large"]
    repo["<b>Repositorio GitHub</b><br/>[Código existente]<br/>Docling, chunking, vectorización,<br/>cliente del gateway"]
    xlsx[/"<b>Papel de trabajo .xlsx</b><br/>Única persistencia del MVP"/]

    auditor -- "Usa vía navegador (HTTPS, SSO)" --> app
    app -- "Prompts y textos (HTTPS, SDK)" --> gw
    gw -- "Enruta" --> az
    repo -. "Módulos reutilizados (build time)" .-> app
    app -- "Genera" --> xlsx
    xlsx -- "Descarga" --> auditor
```

## C4 nivel 2 — Contenedores y componentes

Todo corre en **un contenedor** de Databricks Apps. Dos contenedores lógicos (SPA y API) y seis componentes de backend con responsabilidades separadas: en V2, extracción e indexación se mueven a Jobs sin reescribir el resto.

```mermaid
flowchart TB
    auditor(["👤 Auditor"])
    subgraph APP["Databricks App · 1 contenedor (Medium ~6 GB) · 1 proceso uvicorn"]
        spa["<b>Frontend SPA</b><br/>[React 18 + Vite + TS]<br/>Carga, progreso, árbol dual,<br/>resultados, conclusión"]
        api["<b>API Backend</b><br/>[FastAPI, Python 3.11]<br/>REST /api/*, sirve frontend/dist"]
        ing["<b>Ingesta y metadatos</b><br/>[PyMuPDF + LLM]<br/>Validación, escaneo,<br/>metadatos nativos + JSON"]
        ext["<b>Extracción y seccionado</b><br/>[Docling (repo) + cascada]<br/>Cola de 1 worker"]
        idx["<b>Indexación semántica</b><br/>[Chunker (repo) + FAISS]<br/>IndexFlatIP por tipo de doc"]
        eng["<b>Motor de doble vía</b><br/>[asyncio]<br/>Candidatos, dedup, juez,<br/>citas, agregación"]
        out["<b>Generador del papel</b><br/>[pandas + openpyxl]<br/>Hoja 1 + Hoja 2 · 0 tokens"]
        ses[("<b>Estado de sesión</b><br/>dict en memoria + /tmp<br/>Efímero")]
        smp[("<b>Ejemplos precargados</b><br/>samples/: secciones .json<br/>+ embeddings .npy")]
    end
    gw["<b>AI Gateway</b><br/>[Databricks]"]
    az["<b>Azure AI Foundry</b><br/>GPT-5.6 · text-embedding-3-large"]

    auditor -- HTTPS --> spa
    spa -- "JSON / polling 1.5 s" --> api
    api --> ing --> ext --> idx --> eng --> out
    ing & ext & idx & eng & out <--> ses
    smp -. "Cargar ejemplo" .-> ses
    ing -- "clasificación + metadatos" --> gw
    idx -- "embeddings" --> gw
    eng -- "juicios + conclusión" --> gw
    gw --> az
```

### Componentes

| Componente | Responsabilidad | Tecnología |
|---|---|---|
| Frontend SPA | Carga múltiple, tabla de metadatos, progreso por etapa, árbol dual, resultados, edición de conclusión, descarga | React 18 + Vite + TypeScript, CSS propio, sin librerías de UI pesadas |
| API Backend | Endpoints REST, validaciones, orquestación de jobs, estáticos | FastAPI + uvicorn (1 worker), Pydantic v2 |
| Ingesta y metadatos | Tamaño/páginas, detección de escaneo, metadatos nativos, clasificación + metadatos vía LLM | PyMuPDF, cliente del gateway |
| Extracción y seccionado | Docling y árbol de secciones con texto literal y página | Docling (repo), regex, heurísticas tipográficas |
| Indexación semántica | Sub-chunking, embeddings por lotes, índices FAISS separados | Chunker (repo), faiss-cpu, NumPy |
| Motor de doble vía | Candidatos bidireccionales, pares únicos, juez concurrente, verificación de citas, agregación | asyncio + semáforo, difflib |
| Generador del papel | Hoja 1 y Hoja 2, sin tokens | pandas, openpyxl |
| Estado de sesión | Documentos, secciones, índices, jobs, resultados por sesión | dict en memoria + `/tmp` |

## Flujo extremo a extremo

```mermaid
flowchart LR
    A["1 · Carga<br/>arrastre múltiple"] --> B["2 · Metadatos<br/>nativos + JSON LLM"]
    B --> C["3 · Extracción<br/>Docling en cola + seccionado"]
    C --> D["4 · Indexación<br/>sub-chunks → FAISS"]
    D --> E["5 · Selección<br/>árbol dual"]
    E --> F["6 · Doble vía<br/>pares únicos → juez"]
    F --> G["7 · Papel<br/>Excel 2 hojas + conclusión"]
    classDef user fill:#2A9D8F,color:#fff,stroke:#2A9D8F
    class A,E,G user
```
Pasos 1, 5 y 7: interacción del auditor. Pasos 2, 3, 4 y 6: procesamiento con progreso visible.

## Stack

| Capa | Elección | Notas |
|---|---|---|
| Runtime | Python 3.11 | Compatible con Databricks Apps y el repo |
| API | fastapi, uvicorn, python-multipart, pydantic v2 | Un worker |
| PDF | PyMuPDF (fitz) | Páginas, escaneo, metadatos nativos, texto de primeras páginas |
| Extracción | Docling (versión fijada del repo) | `do_ocr=False`; artefactos pre-cacheados |
| Vectores | faiss-cpu, numpy | IndexFlatIP sobre vectores L2-normalizados = coseno |
| Modelos | Cliente existente del AI Gateway | GPT-5.6; text-embedding-3-large |
| Excel | pandas, openpyxl | Estilos, celdas combinadas, paneles congelados |
| Frontend | React 18, Vite, TypeScript | Se despliega solo `dist` |
| Pruebas | pytest, httpx | Fixtures de seccionado, agregación, citas, Excel |
