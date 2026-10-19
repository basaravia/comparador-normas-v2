import { createContext, useContext, useReducer, type Dispatch, type ReactNode } from "react";
import type { ArbolDocOut, ComparacionOut, DocumentoOut, JobOut } from "./tipos";

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

function reducir(e: Estado, a: Accion): Estado {
  switch (a.t) {
    case "paso": return { ...e, paso: a.paso };
    case "documentos": return { ...e, documentos: a.documentos };
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

const Ctx = createContext<{ e: Estado; d: Dispatch<Accion> } | null>(null);

export function Proveedor({ children }: { children: ReactNode }) {
  const [e, d] = useReducer(reducir, inicial);
  return <Ctx.Provider value={{ e, d }}>{children}</Ctx.Provider>;
}

export function useStore() {
  const c = useContext(Ctx);
  if (!c) throw new Error("Falta el proveedor de estado");
  return c;
}
