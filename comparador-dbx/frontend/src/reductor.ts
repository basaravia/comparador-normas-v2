import type { ArbolDocOut, ComparacionOut, DocumentoOut, JobOut } from "./tipos.ts";

export type Paso = "carga" | "procesando" | "seleccion" | "comparando" | "resultados";

export interface Estado {
  paso: Paso;
  documentos: DocumentoOut[];
  job: JobOut | null;                 // procesamiento o comparación en curso
  normas: ArbolDocOut[] | null;
  manuales: ArbolDocOut[] | null;
  seleccion: Set<string>;             // ids de hojas marcadas (de normas y manuales)
  seleccionLista: boolean;
  comparacion: ComparacionOut | null;
  sesionPerdida: boolean;
  aviso: string;                      // mensaje de negocio para mostrar arriba
}

export const inicial: Estado = {
  paso: "carga", documentos: [], job: null, normas: null, manuales: null, seleccion: new Set(),
  seleccionLista: false, comparacion: null, sesionPerdida: false, aviso: "",
};

export type Accion =
  | { t: "paso"; paso: Paso }
  | { t: "documentos"; documentos: DocumentoOut[] }
  | { t: "agregar"; documentos: DocumentoOut[] }
  | { t: "doc"; documento: DocumentoOut }
  | { t: "job"; job: JobOut | null }
  | { t: "arboles"; normas: ArbolDocOut[]; manuales: ArbolDocOut[]; seleccion: Set<string> }
  | { t: "seleccion"; seleccion: Set<string> }
  | { t: "comparacion"; comparacion: ComparacionOut | null }
  | { t: "sesionPerdida" }
  | { t: "aviso"; aviso: string }
  | { t: "reiniciar" };

/** Documentos ya procesados: si cambian (se sube otro, se carga el ejemplo), la selección debe volver a pedirse al servidor. */
export const listos = (docs: DocumentoOut[]) => docs.filter((d) => d.estado === "listo").map((d) => d.id).sort().join(",");

export function reducir(e: Estado, a: Accion): Estado {
  switch (a.t) {
    case "paso": return { ...e, paso: a.paso };
    case "documentos": return { ...e, documentos: a.documentos, seleccionLista: e.seleccionLista && listos(e.documentos) === listos(a.documentos) };
    case "agregar": return { ...e, documentos: [...e.documentos, ...a.documentos], sesionPerdida: false };
    case "doc": return { ...e, documentos: e.documentos.map((d) => (d.id === a.documento.id ? a.documento : d)) };
    case "job": return { ...e, job: a.job };
    case "arboles": return { ...e, normas: a.normas, manuales: a.manuales, seleccion: a.seleccion, seleccionLista: true };
    case "seleccion": return { ...e, seleccion: a.seleccion };
    case "comparacion": return { ...e, comparacion: a.comparacion };
    case "sesionPerdida": return { ...inicial, sesionPerdida: true };
    case "aviso": return { ...e, aviso: a.aviso };
    case "reiniciar": return { ...inicial };
  }
}
