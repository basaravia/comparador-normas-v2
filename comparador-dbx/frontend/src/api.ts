import type {
  AjustesIn, AjustesOut, ArbolDocOut, ComparacionIn, ComparacionOut, DocumentoOut, DocumentoPatch, ErrorNegocio, HealthOut,
  JobOut, SeccionOut, SesionOut, Tipo,
} from "./tipos";

export class ApiError extends Error {
  constructor(public status: number, public codigo: string, mensaje: string) {
    super(mensaje);
  }
  get sesionPerdida() { return this.status === 410; }
}

async function pedir<T>(ruta: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch("/api" + ruta, { credentials: "same-origin", ...init });
  } catch {
    throw new ApiError(0, "ERR-LLM-001", "No pudimos conectarnos al servicio. Intenta de nuevo en un momento.");
  }
  if (!r.ok) {
    let cuerpo: Partial<ErrorNegocio> = {};
    try { cuerpo = await r.json(); } catch { /* sin cuerpo */ }
    const mensaje = r.status === 410
      ? "La sesión se reinició y los documentos ya no están disponibles. Vuelve a cargarlos o usa el ejemplo."
      : cuerpo.mensaje || "Ocurrió un problema inesperado. Intenta de nuevo o consulta con soporte.";
    throw new ApiError(r.status, cuerpo.codigo || "ERR-GEN-001", mensaje);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

const json = (metodo: string, cuerpo: unknown): RequestInit => ({
  method: metodo, headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo),
});

export const api = {
  sesion: () => pedir<SesionOut>("/session"),
  reiniciar: () => pedir<void>("/session", { method: "DELETE" }),
  salud: () => pedir<HealthOut>("/health"),
  subir: (archivos: File[]) => {
    const f = new FormData();
    archivos.forEach((a) => f.append("archivos", a));
    return pedir<DocumentoOut[]>("/documents", { method: "POST", body: f });
  },
  editarDoc: (id: string, p: DocumentoPatch) => pedir<DocumentoOut>(`/documents/${id}`, json("PATCH", p)),
  procesar: (doc_ids: string[]) => pedir<JobOut>("/documents/process", json("POST", { doc_ids })),
  job: (id: string) => pedir<JobOut>(`/jobs/${id}`),
  arbol: (tipo: Tipo) => pedir<ArbolDocOut[]>(`/sections/tree?tipo=${tipo}`),
  seccion: (id: string) => pedir<SeccionOut>(`/sections/${encodeURIComponent(id)}`),
  comparar: (p: ComparacionIn) => pedir<JobOut>("/comparisons", json("POST", p)),
  comparacion: (id: string) => pedir<ComparacionOut>(`/comparisons/${id}`),
  guardarConclusion: (id: string, texto: string) => pedir<ComparacionOut>(`/comparisons/${id}/conclusion`, json("PUT", { texto })),
  urlExcel: (id: string) => `/api/comparisons/${id}/excel`,
  ajustes: () => pedir<AjustesOut>("/settings"),
  guardarAjustes: (p: AjustesIn) => pedir<AjustesOut>("/settings", json("PUT", p)),
  restablecerAjustes: () => pedir<AjustesOut>("/settings", { method: "DELETE" }),
  ejemplo: () => pedir<DocumentoOut[]>("/samples/load", { method: "POST" }),
};
