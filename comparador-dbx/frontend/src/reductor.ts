import { quitarDeArboles } from "./arbol.ts";
import type { Perdida } from "./sesion.ts";
import type { ArbolDocOut, ComparacionOut, DocumentoOut, JobOut, SesionOut, TrabajoActivo } from "./tipos.ts";

export type Paso = "carga" | "procesando" | "seleccion" | "comparando" | "resultados";

export interface InfoSesion { usuario?: string; retencion_horas?: number; max_documentos?: number; iniciada_ts?: number }
export interface AvisoPdf { ids: string[]; entrar: boolean }       // `entrar`: al cerrar se pasa a Selección

export interface Estado {
  paso: Paso;
  documentos: DocumentoOut[];
  job: JobOut | null;                 // procesamiento o comparación en curso
  normas: ArbolDocOut[] | null;
  manuales: ArbolDocOut[] | null;
  seleccion: Set<string>;             // ids de hojas marcadas (de normas y manuales)
  seleccionLista: boolean;
  comparacion: ComparacionOut | null;
  perdida: Perdida | null;            // se perdió la sesión (expiró o el servidor se reinició)
  renovar: boolean;                   // hay que pedir una sesión nueva al servidor
  aviso: string;                      // mensaje de negocio para mostrar arriba
  sesionInfo: InfoSesion | null;      // cuenta, retención y máximo que informa el servidor
  trabajoActivo: TrabajoActivo | null;
  reenganche: TrabajoActivo | null;   // se abrió la vista de avance de un trabajo que ya estaba en marcha
  avisoPdf: AvisoPdf | null;
  agregando: boolean;                 // se fue a Carga desde Selección/Resultados para agregar documentos
}

export const inicial: Estado = {
  paso: "carga", documentos: [], job: null, normas: null, manuales: null, seleccion: new Set(),
  seleccionLista: false, comparacion: null, perdida: null, renovar: false, aviso: "",
  sesionInfo: null, trabajoActivo: null, reenganche: null, avisoPdf: null, agregando: false,
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
  | { t: "sesion"; sesion: SesionOut; perdida?: Perdida | null }
  | { t: "quitar"; id: string; sesion: SesionOut }
  | { t: "sesionPerdida"; conProceso?: boolean }
  | { t: "renovada" }
  | { t: "descartarPerdida" }
  | { t: "reenganchar"; trabajo: TrabajoActivo }
  | { t: "entrarSeleccion"; aviso: string[] }
  | { t: "abrirAviso"; ids: string[]; entrar: boolean }
  | { t: "cerrarAviso" }
  | { t: "agregarDocs" }
  | { t: "agregandoFin" }
  | { t: "aviso"; aviso: string }
  | { t: "reiniciar" };

/** Documentos ya procesados: si cambian (se sube otro, se carga el ejemplo), la selección debe volver a pedirse al servidor. */
export const listos = (docs: DocumentoOut[]) => docs.filter((d) => d.estado === "listo").map((d) => d.id).sort().join(",");

const enCurso = (j: JobOut) => j.estado === "en_cola" || j.estado === "en_curso";

/** Aplica lo que dice GET /api/session: lista de documentos, cuenta, trabajo activo y comparación vigente. */
function aplicarSesion(e: Estado, s: SesionOut, perdida: Perdida | null | undefined): Estado {
  const base: Estado = perdida ? { ...inicial, perdida, sesionInfo: e.sesionInfo } : e;
  const docs = s.documentos;
  let n: Estado = {
    ...base, documentos: docs, renovar: false,
    seleccionLista: base.seleccionLista && listos(base.documentos) === listos(docs),
    perdida: docs.length > 0 ? null : base.perdida,
    sesionInfo: { usuario: s.usuario, retencion_horas: s.retencion_horas, max_documentos: s.max_documentos, iniciada_ts: s.iniciada_ts },
    trabajoActivo: "trabajo_activo" in s ? s.trabajo_activo ?? null : base.trabajoActivo,
  };
  if (!s.comparacion_id && n.comparacion) {                                  // la comparación ya no existe en el servidor
    n = { ...n, comparacion: null, paso: n.paso === "resultados" ? "seleccion" : n.paso };
  }
  if (!docs.some((x) => x.estado === "listo") && (n.paso === "seleccion" || n.paso === "resultados")) n = { ...n, paso: "carga" };
  return n;
}

export function reducir(e: Estado, a: Accion): Estado {
  switch (a.t) {
    case "paso": return { ...e, paso: a.paso, reenganche: a.paso === "procesando" || a.paso === "comparando" ? e.reenganche : null };
    case "documentos": return { ...e, documentos: a.documentos, seleccionLista: e.seleccionLista && listos(e.documentos) === listos(a.documentos) };
    case "agregar": return { ...e, documentos: [...e.documentos, ...a.documentos], perdida: null };
    case "doc": return { ...e, documentos: e.documentos.map((d) => (d.id === a.documento.id ? a.documento : d)) };
    case "job":
      return {
        ...e, job: a.job, reenganche: a.job ? e.reenganche : null,
        trabajoActivo: a.job && enCurso(a.job) ? { id: a.job.job_id, tipo: a.job.tipo } : null,
      };
    case "arboles": return { ...e, normas: a.normas, manuales: a.manuales, seleccion: a.seleccion, seleccionLista: true, agregando: false };
    case "seleccion": return { ...e, seleccion: a.seleccion };
    case "comparacion": return { ...e, comparacion: a.comparacion };
    case "sesion": return aplicarSesion(e, a.sesion, a.perdida);
    case "quitar": {
      // Se quita el documento de la lista, de los árboles y de las marcas; los demás se conservan.
      const arb = e.normas && e.manuales ? quitarDeArboles(e.normas, e.manuales, e.seleccion, a.id) : { normas: e.normas, manuales: e.manuales, seleccion: e.seleccion };
      return aplicarSesion({ ...e, ...arb, documentos: e.documentos.filter((d) => d.id !== a.id) }, a.sesion, undefined);
    }
    case "sesionPerdida": return { ...inicial, sesionInfo: e.sesionInfo, perdida: { motivo: "reinicio", conProceso: !!a.conProceso }, renovar: true };
    case "renovada": return { ...e, renovar: false };
    case "descartarPerdida": return { ...e, perdida: null };
    case "reenganchar":
      return { ...e, paso: a.trabajo.tipo === "procesamiento" ? "procesando" : "comparando", job: null, reenganche: a.trabajo, trabajoActivo: a.trabajo };
    case "entrarSeleccion":
      return a.aviso.length > 0 ? { ...e, avisoPdf: { ids: a.aviso, entrar: true } } : { ...e, paso: "seleccion", reenganche: null };
    case "abrirAviso": return { ...e, avisoPdf: { ids: a.ids, entrar: a.entrar } };
    case "cerrarAviso": return { ...e, avisoPdf: null, paso: e.avisoPdf?.entrar ? "seleccion" : e.paso, reenganche: e.avisoPdf?.entrar ? null : e.reenganche };
    case "agregarDocs": return { ...e, paso: "carga", agregando: true };
    case "agregandoFin": return { ...e, agregando: false };
    case "aviso": return { ...e, aviso: a.aviso };
    case "reiniciar": return { ...inicial, sesionInfo: e.sesionInfo };
  }
}
