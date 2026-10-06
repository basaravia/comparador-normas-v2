// Datos del tablero. Lo actualiza el agente product-owner antes de cada push.
// index.html solo los pinta: no hace falta tocarlo para mover tarjetas.
//
// estado: "por_hacer" | "en_curso" | "revision" | "hecho" | "bloqueado"
// tipo:   "hito" | "seguridad" | "pendiente" | "decision"
window.TABLERO = {
  actualizado: "2026-10-06",
  rama: "feat/fase-l-local",
  ultimo_commit: "0b4f926 feat(L1): ingesta de PDFs (validación + clasificación) con LLM real",
  demo: "Demo MVP en workspace Azure de pago (stage mvp, Foundry)",

  fases: [
    { id: "L", nombre: "Fase L · Backend en local (notebooks)" },
    { id: "D", nombre: "Fase D · Despliegue en Databricks Free" },
    { id: "U", nombre: "Fase U · Interfaz" },
    { id: "Demo", nombre: "Demo · Azure + Foundry" },
  ],

  tarjetas: [
    // ── Hitos (docs/13) ──
    { id: "L0", fase: "L", tipo: "hito", estado: "hecho", titulo: "Base: config, errores y cliente de modelos",
      nota: "7/7 chequeos en 00_modelos.ipynb con Groq + bge-m3 reales en sandbox (criterio cumplido en f227b59). Después: Foundry listo para probar, correcciones appsec, stages dev/sandbox/mvp y proveedor DMR.", commit: "7c802a1" },
    { id: "L1", fase: "L", tipo: "hito", estado: "hecho", titulo: "Ingesta: validación + clasificación",
      nota: "6/6 chequeos en 01_ingesta.ipynb (Groq real). MOCK → manual_control, LA/FT → normativa (0,85). Rechazos con ERR-ING-001..003 y mensaje de negocio.", commit: "0b4f926" },
    { id: "L2", fase: "L", tipo: "hito", estado: "por_hacer", titulo: "Seccionado: Docling + cascada de patrones",
      nota: "Siguiente. Criterio: ≥ 95 % de artículos de una norma real. Medir RAM/CPU de Docling en la Pi." },
    { id: "L3", fase: "L", tipo: "hito", estado: "por_hacer", titulo: "Recuperación: sub-chunks, embeddings, FAISS, pares",
      nota: "Recall ≥ 90 % sobre el golden set de los MOCK." },
    { id: "L4", fase: "L", tipo: "hito", estado: "por_hacer", titulo: "Juez: veredictos, citas verificadas, marcas A/L/R/X/P",
      nota: "MOCK-03 → A, MOCK-01 → L, MOCK-02 → R." },
    { id: "L5", fase: "L", tipo: "hito", estado: "por_hacer", titulo: "Papel de trabajo: Excel Hoja 1 + Hoja 2",
      nota: "Cero tokens al generar. Conteos Hoja 1 = Hoja 2." },
    { id: "L6", fase: "L", tipo: "hito", estado: "por_hacer", titulo: "Extremo a extremo: PDFs → Excel",
      nota: "Tiempos y RAM medidos en la Raspberry." },
    { id: "D0", fase: "D", tipo: "hito", estado: "por_hacer", titulo: "API FastAPI + sesión en memoria" },
    { id: "D1", fase: "D", tipo: "hito", estado: "por_hacer", titulo: "App en Databricks Free (app.yaml, < 10 MB)" },
    { id: "D2", fase: "D", tipo: "hito", estado: "por_hacer", titulo: "Ejemplos precargados (samples/)" },
    { id: "U0", fase: "U", tipo: "hito", estado: "por_hacer", titulo: "UI mínima en verde y blanco" },
    { id: "DEMO", fase: "Demo", tipo: "hito", estado: "por_hacer", titulo: "Ensayo con Foundry y documentos reales" },

    // ── Pendientes y verificaciones ──
    { id: "P-01", fase: "L", tipo: "pendiente", estado: "por_hacer", titulo: "Probar stage dev (MacBook, DMR)",
      nota: "Opcional, no bloquea (docs/13). Lo prueba el usuario." },
    { id: "P-02", fase: "Demo", tipo: "pendiente", estado: "por_hacer", titulo: "Probar stage mvp (Foundry en Databricks)",
      nota: "Celda comentada en 00_modelos.ipynb; token por dbutils." },
    { id: "P-03", fase: "L", tipo: "pendiente", estado: "por_hacer", titulo: "Calibrar SIM_THRESHOLD por stage",
      nota: "Con bge-m3 un par sin relación ya da ~0,50. Se calibra en L3 (docs/14 #1)." },
    { id: "P-04", fase: "L", tipo: "pendiente", estado: "por_hacer", titulo: "Calibrar LLM_CONCURRENCY con Groq gratuito",
      nota: "Ya se vieron 429 en L1. Se calibra en L4 (docs/14 #9)." },
    { id: "P-05", fase: "D", tipo: "pendiente", estado: "por_hacer", titulo: "D0: los metadatos editados por el auditor ganan a los del modelo",
      nota: "Anotado en implementacion/README.md, L1." },

    // ── Seguridad (agente appsec) ──
    { id: "S-01", fase: "L", tipo: "seguridad", estado: "por_hacer", titulo: "L4: chequeo de frases al evaluador → requiere_revision",
      nota: "Decisión del usuario (docs/14 #18)." },
    { id: "S-02", fase: "L", tipo: "seguridad", estado: "por_hacer", titulo: "L5: neutralizar fórmulas en el Excel (CWE-1236)",
      nota: "Todas las celdas de texto, incluidos metadatos y textos del modelo: prefijos =, +, -, @." },
    { id: "S-03", fase: "D", tipo: "seguridad", estado: "por_hacer", titulo: "D0: subidas con nombre generado, tope en streaming y timeout",
      nota: "MuPDF parsea entrada hostil." },
    { id: "S-04", fase: "D", tipo: "seguridad", estado: "por_hacer", titulo: "D0: /api/health sin detalle técnico y con caché",
      nota: "El ping gasta tokens. Además: cargar_prompt nunca con entrada del usuario." },
    { id: "S-05", fase: "L", tipo: "seguridad", estado: "por_hacer", titulo: "L4: rellenar el prompt del juez con rellenar_prompt",
      nota: "Ya existe desde L1 (clasificador). Auditoría appsec de L0." },
    { id: "S-06", fase: "L", tipo: "seguridad", estado: "hecho", titulo: "L1: validar %PDF, MAX_MB, MAX_PAGES y sanear el nombre",
      nota: "Hecho en validation.py; verificado en 01_ingesta.ipynb.", commit: "0b4f926" },
  ],

  // Historial breve: una línea por push (lo más reciente arriba).
  historial: [
    { fecha: "2026-10-06", texto: "Creación del tablero de avance; el product-owner lo actualiza antes de cada push." },
    { fecha: "2026-10-06", texto: "L1 cerrado: ingesta con validación y clasificador (Groq real)." },
    { fecha: "2026-10-02", texto: "Stages dev/sandbox/mvp, proveedor DMR y auditoría appsec de L0." },
    { fecha: "2026-10-01", texto: "L0 cerrado: base del backend con Groq + bge-m3 reales. Repo público." },
  ],
};
