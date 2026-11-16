// Lógica pura de sesión: cupo, lotes de archivos, aviso de PDF y pérdida de sesión. Sin React ni navegador (se prueba con `npm test`).
import type { DocumentoOut } from "./tipos.ts";

// ---- Cupo y lotes (P-4, P-5) ----

/** Documentos que cuentan para el máximo: los fallidos no cuentan. */
export const usados = (docs: DocumentoOut[]) => docs.filter((d) => d.estado !== "error").length;

/** Cuántos documentos más caben; `null` si el servidor no informó el máximo. */
export const cupoLibre = (docs: DocumentoOut[], max?: number): number | null =>
  max === undefined ? null : Math.max(0, max - usados(docs));

/** Decide qué archivos se envían: solo PDF y, si el lote excede el cupo, ninguno (se avisa cuántos caben). */
export function evaluarLote<T extends { name: string }>(archivos: T[], libres: number | null, max?: number): { enviar: T[]; avisos: string[] } {
  const pdfs = archivos.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
  const omitidos = archivos.filter((f) => !f.name.toLowerCase().endsWith(".pdf")).map((f) => f.name);
  const avisos: string[] = [];
  if (omitidos.length) avisos.push(`Solo se aceptan archivos PDF. No se agregó: ${omitidos.join(", ")}.`);
  if (libres !== null && pdfs.length > libres) {
    const caben = libres === 1 ? "Solo cabe 1 documento más" : `Solo caben ${libres} documentos más`;
    avisos.push(`${caben} (máximo ${max}). No se agregó ninguno; elige hasta ${libres} o quita alguno de la lista.`);
    return { enviar: [], avisos };
  }
  return { enviar: pdfs, avisos };
}

// ---- Aviso "PDF no guardado" (decisión 2, I-7) ----

/** Lo que el navegador recuerda de los documentos ya avisados, ligado a la sesión del servidor en que se avisó. */
export interface Avisados { iniciada_ts: number; ids: string[] }

/** Documentos indexados que aún no se han avisado en este navegador (para esta sesión del servidor). */
export function idsParaAviso(docs: DocumentoOut[], avisados: Avisados | null, iniciada_ts: number): string[] {
  const ya = new Set(avisados && avisados.iniciada_ts === iniciada_ts ? avisados.ids : []);
  return docs.filter((d) => d.estado === "listo" && !ya.has(d.id)).map((d) => d.id);
}

export function unirAvisados(previo: Avisados | null, iniciada_ts: number, ids: string[]): Avisados {
  const base = previo && previo.iniciada_ts === iniciada_ts ? previo.ids : [];
  return { iniciada_ts, ids: [...new Set([...base, ...ids])] };
}

// ---- Pérdida de sesión (I-2): expirada vs reinicio ----

/** Lo que el navegador recuerda de la última vez que habló con el servidor. */
export interface Recuerdo { usuario: string; docs: number; iniciada_ts: number; ultima_ms: number; trabajo: boolean }
export type MotivoPerdida = "expirada" | "reinicio";
export interface Perdida { motivo: MotivoPerdida; conProceso: boolean }

export interface EntradaPerdida {
  recuerdo: Recuerdo | null;
  usuario?: string;
  sesion_nueva: boolean;
  iniciada_ts?: number;
  docs: number;                 // documentos que devuelve el servidor ahora
  perdidaConocida: boolean;     // el servidor ya respondió "sesión perdida" a una llamada
  ahoraMs: number;
  retencionHoras?: number;
}

/** `null` si no se perdió nada; "expirada" si pasó más que la retención desde la última actividad; "reinicio" en otro caso. */
export function motivoPerdida(p: EntradaPerdida): MotivoPerdida | null {
  const rec = p.recuerdo && (!p.usuario || p.recuerdo.usuario === p.usuario) ? p.recuerdo : null;
  const cambio = !!rec && rec.docs > 0 && p.docs === 0 && p.iniciada_ts !== undefined && p.iniciada_ts !== rec.iniciada_ts;
  const nuevaConAlgoPerdido = p.sesion_nueva && !(rec && rec.docs === 0);   // quien no tenía nada cargado no perdió nada
  if (!(p.perdidaConocida || nuevaConAlgoPerdido || cambio)) return null;
  const expirada = !!rec && p.retencionHoras !== undefined && p.ahoraMs - rec.ultima_ms > p.retencionHoras * 3600 * 1000;
  return expirada ? "expirada" : "reinicio";
}
