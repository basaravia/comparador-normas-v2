import type { ArbolDocOut, NodoOut } from "./tipos.ts";

/** Hojas (artículos o secciones comparables) de un nodo. */
export function hojas(n: NodoOut): NodoOut[] {
  return n.hoja ? [n] : n.hijos.flatMap(hojas);     // un título sin artículos detectados no es hoja: no se puede comparar
}

const todasLasHojas = (arboles: ArbolDocOut[]) => arboles.flatMap((a) => a.nodos.flatMap(hojas));

/** Selección inicial: las hojas que el servidor propone (seleccionadas y no excluidas). */
export const seleccionInicial = (arboles: ArbolDocOut[]) =>
  new Set(todasLasHojas(arboles).filter((h) => h.seleccionada && !h.excluida).map((h) => h.id));

/** Al recargar el árbol se conserva lo que el auditor ya había marcado (si sigue existiendo); los documentos nuevos entran con su preselección.
 *  Solo se usa un manual a la vez: un manual nuevo llega sin marcas si ya hay otro con marcas; si todos son nuevos, solo el primero se preselecciona. */
export function seleccionTrasRecarga(previa: Set<string>, vistos: ArbolDocOut[], normas: ArbolDocOut[], manuales: ArbolDocOut[]): Set<string> {
  const docsVistos = new Set(vistos.map((a) => a.doc_id));
  const esNuevo = (a: ArbolDocOut) => !docsVistos.has(a.doc_id);
  const ids = new Set(todasLasHojas([...normas, ...manuales]).map((h) => h.id));
  const conservada = new Set([...previa].filter((i) => ids.has(i)));
  const manualYaMarcado = manuales.some((a) => !esNuevo(a) && a.nodos.flatMap(hojas).some((h) => conservada.has(h.id)));
  const manualesNuevos = manualYaMarcado ? [] : manuales.filter(esNuevo).slice(0, 1);
  return new Set([...conservada, ...seleccionInicial([...normas.filter(esNuevo), ...manualesNuevos])]);
}

/** Marcas por documento (para detectar más de un manual con marcas). */
export const marcasPorDoc = (arboles: ArbolDocOut[], sel: Set<string>) =>
  arboles.map((a) => ({ doc_id: a.doc_id, nombre: a.nombre, n: a.nodos.flatMap(hojas).filter((h) => sel.has(h.id)).length }));

/** Manuales con marcas; si hay más de uno, la comparación sería rechazada (ERR-CMP-003): la interfaz lo impide. */
export const manualesConMarcas = (manuales: ArbolDocOut[], sel: Set<string>) => marcasPorDoc(manuales, sel).filter((m) => m.n > 0);
export const hayConflictoDeManuales = (manuales: ArbolDocOut[], sel: Set<string>) => manualesConMarcas(manuales, sel).length > 1;

export function quitarMarcasDeDoc(a: ArbolDocOut, sel: Set<string>): Set<string> {
  const ids = new Set(a.nodos.flatMap(hojas).map((h) => h.id));
  return new Set([...sel].filter((i) => !ids.has(i)));
}

/** Quita el árbol de un documento y sus marcas; los demás documentos y sus marcas no cambian. */
export function quitarDeArboles(normas: ArbolDocOut[], manuales: ArbolDocOut[], sel: Set<string>, docId: string) {
  const quitado = [...normas, ...manuales].find((a) => a.doc_id === docId);
  return {
    normas: normas.filter((a) => a.doc_id !== docId),
    manuales: manuales.filter((a) => a.doc_id !== docId),
    seleccion: quitado ? quitarMarcasDeDoc(quitado, sel) : sel,
  };
}
