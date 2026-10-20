import type { ArbolDocOut, NodoOut } from "./tipos.ts";

/** Hojas (artículos o secciones comparables) de un nodo. */
export function hojas(n: NodoOut): NodoOut[] {
  return n.hoja || n.hijos.length === 0 ? [n] : n.hijos.flatMap(hojas);
}

const todasLasHojas = (arboles: ArbolDocOut[]) => arboles.flatMap((a) => a.nodos.flatMap(hojas));

/** Selección inicial: las hojas que el servidor propone (seleccionadas y no excluidas). */
export const seleccionInicial = (arboles: ArbolDocOut[]) =>
  new Set(todasLasHojas(arboles).filter((h) => h.seleccionada && !h.excluida).map((h) => h.id));

/** Al recargar el árbol se conserva lo que el auditor ya había marcado (si sigue existiendo); solo los documentos nuevos entran con su preselección. */
export function seleccionTrasRecarga(previa: Set<string>, vistos: ArbolDocOut[], normas: ArbolDocOut[], manuales: ArbolDocOut[]): Set<string> {
  const docsVistos = new Set(vistos.map((a) => a.doc_id));
  const nuevos = [...normas, ...manuales].filter((a) => !docsVistos.has(a.doc_id));
  const ids = new Set(todasLasHojas([...normas, ...manuales]).map((h) => h.id));
  return new Set([...[...previa].filter((i) => ids.has(i)), ...seleccionInicial(nuevos)]);
}
