// Lo que el navegador recuerda (localStorage / sessionStorage). Todo en try/catch: sin almacenamiento la app funciona igual.
import { idsParaAviso, unirAvisados, type Avisados, type Recuerdo } from "./sesion.ts";
import type { DocumentoOut } from "./tipos.ts";

const K_RECUERDO = "cn_recuerdo", K_AVISADOS = "cn_avisados", K_OCULTO = "cn_aviso_oculto";

function leer<T>(almacen: Storage, clave: string): T | null {
  try { const t = almacen.getItem(clave); return t ? (JSON.parse(t) as T) : null; } catch { return null; }
}
function escribir(almacen: Storage, clave: string, valor: unknown) { try { almacen.setItem(clave, JSON.stringify(valor)); } catch { /* sin almacenamiento */ } }

export const leerRecuerdo = () => { try { return leer<Recuerdo>(localStorage, K_RECUERDO); } catch { return null; } };
export const guardarRecuerdo = (r: Recuerdo) => { try { escribir(localStorage, K_RECUERDO, r); } catch { /* nada */ } };

export function marcarAvisados(ids: string[], iniciada_ts: number | undefined) {
  try { escribir(localStorage, K_AVISADOS, unirAvisados(leer<Avisados>(localStorage, K_AVISADOS), iniciada_ts ?? 0, ids)); } catch { /* nada */ }
}

export function ocultarAvisoEnSesion() { try { sessionStorage.setItem(K_OCULTO, "1"); } catch { /* nada */ } }
const avisoOculto = () => { try { return sessionStorage.getItem(K_OCULTO) === "1"; } catch { return false; } };

/** Ids que deben mostrarse en el aviso ahora. Si la persona pidió no verlo, se dan por avisados y no se muestra. */
export function avisoParaMostrar(docs: DocumentoOut[], iniciada_ts: number | undefined): string[] {
  let previo: Avisados | null = null;
  try { previo = leer<Avisados>(localStorage, K_AVISADOS); } catch { /* nada */ }
  const ids = idsParaAviso(docs, previo, iniciada_ts ?? 0);
  if (ids.length > 0 && avisoOculto()) { marcarAvisados(ids, iniciada_ts); return []; }
  return ids;
}

/** "Borrar todo": se olvidan la preferencia del aviso y lo recordado. */
export function olvidarTodo() {
  try { sessionStorage.removeItem(K_OCULTO); localStorage.removeItem(K_AVISADOS); localStorage.removeItem(K_RECUERDO); } catch { /* nada */ }
}
