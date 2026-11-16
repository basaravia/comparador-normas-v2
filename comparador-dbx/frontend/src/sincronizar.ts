// Pegamento entre el servidor y el estado: pedir GET /api/session y reconciliar.
import type { Dispatch } from "react";
import { api } from "./api";
import { leerRecuerdo } from "./recuerdo.ts";
import type { Accion } from "./reductor.ts";
import { motivoPerdida } from "./sesion.ts";
import type { SesionOut } from "./tipos.ts";

interface Opciones { perdidaConocida?: boolean; conProceso?: boolean; sinPerdida?: boolean }

/** Pide la sesión, decide si se perdió algo (expiró o el servidor se reinició) y lo vuelca al estado. */
export async function traerSesion(d: Dispatch<Accion>, o: Opciones = {}): Promise<SesionOut> {
  const s = await api.sesion();
  const rec = leerRecuerdo();
  const motivo = o.sinPerdida ? null : motivoPerdida({
    recuerdo: rec, usuario: s.usuario, sesion_nueva: !!s.sesion_nueva, iniciada_ts: s.iniciada_ts, docs: s.documentos.length,
    perdidaConocida: !!o.perdidaConocida, ahoraMs: Date.now(), retencionHoras: s.retencion_horas,
  });
  d({ t: "sesion", sesion: s, perdida: motivo ? { motivo, conProceso: !!o.conProceso || !!rec?.trabajo } : null });
  return s;
}

/** Abre la vista de avance del trabajo que el servidor dice que está activo. Devuelve false si ya no hay ninguno. */
export async function verAvance(d: Dispatch<Accion>): Promise<boolean> {
  const s = await traerSesion(d);
  if (!s.trabajo_activo) return false;
  d({ t: "reenganchar", trabajo: s.trabajo_activo });
  return true;
}
