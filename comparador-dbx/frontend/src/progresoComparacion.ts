// Lógica pura de la pantalla «Comparando» (docs/ux/comparacion-en-curso-v1.md): orden, filtros, retención,
// paginación, anuncios por hitos, estimado y cancelación. Sin React, para poder probarla con node --test.
import type { FragmentoOut, JobOut, ParEnCurso, ParResuelto } from "./tipos.ts";

// Respaldos solo para un servidor antiguo que no manda estos campos. El valor vigente viene del servidor
// (`pares_por_pagina` y `estimado_desde_pares`, de la configuración del backend); para cambiarlo se edita allí, no aquí.
export const PARES_POR_PAGINA = 50;
export const ESTIMADO_DESDE_PARES = 3;

export function duracion(seg: number): string {
  const s = Math.max(0, Math.round(seg));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m} min ${s % 60} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`;

// ---- Fase y estimado ----

export function textoFase(fase: string, etapa = ""): { paso: number | null; texto: string } {
  const f: Record<string, [number, string]> = {
    recuperando: [1, "Buscando coincidencias"], juzgando: [2, "Evaluando cada par"], armando: [3, "Armando el papel de trabajo"],
  };
  const x = f[fase];
  return x ? { paso: x[0], texto: `Paso ${x[0]} de 3 · ${x[1]}` } : { paso: null, texto: etapa || "En cola" };
}

/** Tiempo restante con rango (±35 %) a partir de los pares resueltos; null si todavía no hay base. */
export function estimarRango(hechos: number, total: number, transcurrido: number): { desde: number; hasta: number } | null {
  if (hechos <= 0 || total <= hechos || transcurrido < 3) return null;
  const resto = ((total - hechos) * transcurrido) / hechos;
  return { desde: resto * 0.65, hasta: resto * 1.35 };
}

/** Texto del estimado de la comparación; solo en la fase 2. Antes de `minimo` pares resueltos: aviso de que aún no se puede. */
export function textoEstimado(fase: string, hechos: number, total: number, transcurrido: number, minimo = ESTIMADO_DESDE_PARES): string | null {
  if (fase !== "juzgando" || total <= 0 || hechos >= total) return null;
  const r = hechos >= minimo ? estimarRango(hechos, total, transcurrido) : null;
  return r ? `Falta aproximadamente: entre ${duracion(r.desde)} y ${duracion(r.hasta)}` : "Todavía no podemos estimar el tiempo restante.";
}

// ---- Resueltos: unir, ordenar, filtrar, paginar ----

export const maxSeq = (rs: { seq: number }[]) => rs.reduce((m, r) => Math.max(m, r.seq), 0);

/** Une lo acumulado con lo recién llegado sin repetir `seq`; devuelve el más reciente primero. */
export function unirResueltos(acum: ParResuelto[], nuevos: ParResuelto[]): ParResuelto[] {
  const por = new Map<number, ParResuelto>();
  for (const r of acum) por.set(r.seq, r);
  for (const r of nuevos) por.set(r.seq, r);
  return [...por.values()].sort((a, b) => b.seq - a.seq);
}

/** Resueltos de un sondeo: `pares_resueltos` si el servidor lo manda; si no, los `ultimos_veredictos` de siempre. */
export const resueltosDe = (j: JobOut): ParResuelto[] => j.pares_resueltos ?? j.ultimos_veredictos ?? [];

export type FilaPar =
  | { tipo: "curso"; clave: string; par: ParEnCurso }
  | { tipo: "resuelto"; clave: string; par: ParResuelto };

/** En análisis arriba (en el orden del servidor), luego los resueltos, el más reciente primero. */
export function ordenarFilas(enCurso: ParEnCurso[], resueltos: ParResuelto[]): FilaPar[] {
  const rec = [...resueltos].sort((a, b) => b.seq - a.seq);
  return [
    ...enCurso.map((par): FilaPar => ({ tipo: "curso", clave: `c-${par.par_id}`, par })),
    ...rec.map((par): FilaPar => ({ tipo: "resuelto", clave: `r-${par.seq}`, par })),
  ];
}

export type Filtro = "todos" | "total" | "parcial" | "nula" | "revisar";
export const FILTROS: { id: Filtro; etiqueta: string }[] = [
  { id: "todos", etiqueta: "Todos" }, { id: "total", etiqueta: "Cubre por completo" }, { id: "parcial", etiqueta: "Cubre en parte" },
  { id: "nula", etiqueta: "No lo cubre" }, { id: "revisar", etiqueta: "Por revisar" },
];

export const porRevisar = (p: ParResuelto) => p.requiere_revision || p.cobertura === "sin_veredicto";

export function coincide(p: ParResuelto, f: Filtro): boolean {
  if (f === "todos") return true;
  if (f === "revisar") return porRevisar(p);
  return p.cobertura === f;
}

export function contarPorFiltro(rs: ParResuelto[]): Record<Filtro, number> {
  const c: Record<Filtro, number> = { todos: 0, total: 0, parcial: 0, nula: 0, revisar: 0 };
  for (const r of rs) for (const f of FILTROS) if (coincide(r, f.id)) c[f.id]++;
  return c;
}

export const filtrar = (rs: ParResuelto[], f: Filtro) => rs.filter((r) => coincide(r, f));

export function paginar<T>(items: T[], paginas: number, porPagina: number): { visibles: T[]; quedan: number } {
  const n = Math.max(1, paginas) * Math.max(1, porPagina);
  return { visibles: items.slice(0, n), quedan: Math.max(0, items.length - n) };
}

export const paresPorPagina = (j: JobOut) => (j.pares_por_pagina && j.pares_por_pagina > 0 ? j.pares_por_pagina : PARES_POR_PAGINA);
export const estimadoDesdePares = (j: JobOut) => (j.estimado_desde_pares && j.estimado_desde_pares > 0 ? j.estimado_desde_pares : ESTIMADO_DESDE_PARES);

// ---- Retención de resultados nuevos (sin saltos bajo el ojo) ----

export const FILAS_DE_MARGEN = 1;   // se retiene si la persona bajó más de una fila

export function debeRetener(a: { filasAbiertas: number; focoEnLista: boolean; filasBajadas: number }): boolean {
  return a.filasAbiertas > 0 || a.focoEnLista || a.filasBajadas > FILAS_DE_MARGEN;
}

/** Hasta qué `seq` se muestra: si hay que retener, el corte actual; si no, todo lo recibido. */
export const corteVisible = (corte: number, ultimo: number, retener: boolean) => (retener ? Math.min(corte, ultimo) : ultimo);

export const visiblesHasta = (rs: ParResuelto[], corte: number) => rs.filter((r) => r.seq <= corte);
export const contarNuevos = (rs: ParResuelto[], corte: number) => rs.filter((r) => r.seq > corte).length;

// ---- Anuncios para lectores de pantalla: solo hitos, nunca por par ----

export const PAUSA_ANUNCIO_S = 60;
export interface EstadoAnuncio { fase: string; decil: number; t: number; espera: boolean; cancelando: boolean; final: string }
export const anuncioInicial: EstadoAnuncio = { fase: "", decil: 0, t: -Infinity, espera: false, cancelando: false, final: "" };
export interface DatosAnuncio {
  fase: string; etapa: string; estado: string; cancelando: boolean; espera: boolean; hechos: number; total: number; porRevisar: number;
}

/** Devuelve el estado nuevo y, si hubo un hito, el texto a anunciar. El avance por pares solo se anuncia al pasar un 10 % Y pasados 60 s del último aviso. */
export function siguienteAnuncio(prev: EstadoAnuncio, d: DatosAnuncio, ahora: number): { estado: EstadoAnuncio; texto: string | null } {
  const resumen = `${d.hechos} de ${d.total} pares resueltos; ${d.porRevisar} por revisar`;
  const decil = d.total > 0 ? Math.floor((10 * d.hechos) / d.total) : 0;
  const finalizado = ["listo", "cancelado", "error"].includes(d.estado) ? d.estado : "";
  const sig: EstadoAnuncio = { ...prev, fase: d.fase, espera: d.espera, cancelando: d.cancelando, final: finalizado };
  let texto: string | null = null;
  if (finalizado && prev.final !== finalizado) {
    texto = finalizado === "listo" ? `Comparación terminada: ${resumen}.` : finalizado === "cancelado" ? "Comparación cancelada." : "La comparación no se pudo completar.";
  } else if (!finalizado && d.cancelando && !prev.cancelando) texto = "Cancelando la comparación.";
  else if (!finalizado && d.fase && d.fase !== prev.fase) texto = textoFase(d.fase, d.etapa).texto;
  else if (!finalizado && d.espera && !prev.espera) texto = "Esperando al servicio de IA por el límite de uso del proveedor.";
  else if (!finalizado && d.fase === "juzgando" && decil > prev.decil && ahora - prev.t >= PAUSA_ANUNCIO_S) {
    texto = `${resumen}.`;
    sig.decil = decil;
  }
  if (texto) sig.t = ahora;
  return { estado: sig, texto };
}

// ---- Cancelar ----

export const accionCancelar = (resueltos: number): "directo" | "confirmar" => (resueltos >= 1 ? "confirmar" : "directo");
export const textoConfirmacion = (n: number) => `¿Cancelar la comparación? Ya resolvimos ${plural(n, "par", "pares")}.`;
export const textoCancelada = (n: number) =>
  n <= 0 ? "Comparación cancelada."
    : n === 1 ? "Comparación cancelada. El par resuelto no se conserva." : `Comparación cancelada. Los ${n} pares resueltos no se conservan.`;

/** Contador de la cabecera: «en análisis / en espera» solo mientras hay trabajo en curso (no tras cancelar ni en error). */
export const textoContador = (hechos: number, total: number, enAnalisis: number, activo: boolean) =>
  `${hechos} de ${total} pares resueltos` + (activo ? ` · ${enAnalisis} en análisis · ${Math.max(0, total - hechos - enAnalisis)} en espera` : "");

/** El aviso de «proceso que sigue en marcha» solo vale mientras el trabajo no terminó. */
export const trabajoTerminado = (estado: string) => ["listo", "cancelado", "error"].includes(estado);
export const ERROR_CANCELAR = "No pudimos enviar la cancelación. Inténtalo de nuevo. (ERR-JOB-003)";

// ---- Texto de cada fila ----

const idDe = (f: FragmentoOut | string) => (typeof f === "string" ? f : f.identificador);
const docDe = (f: FragmentoOut | string) => (typeof f === "string" ? "" : f.documento);
const conPrefijo = (pref: string, id: string) => (/^(art|sec)/i.test(id) ? id : `${pref} ${id}`);

/** «Art. 12 · {norma} ↔ Sección 5.2 · {manual}» (sin el documento si el servidor aún no lo manda). */
export function etiquetaPar(art: FragmentoOut | string, sec: FragmentoOut | string): string {
  const a = conPrefijo("Art.", idDe(art)), s = conPrefijo("Sección", idDe(sec));
  return `${docDe(art) ? `${a} · ${docDe(art)}` : a} ↔ ${docDe(sec) ? `${s} · ${docDe(sec)}` : s}`;
}

/** La fila se lee en dos líneas: lo que distingue al par («Art. 12 ↔ Sección 5.2», no se corta) y debajo los documentos (se acortan). */
export function partesPar(art: FragmentoOut | string, sec: FragmentoOut | string): { ids: string; docs: string } {
  return {
    ids: `${conPrefijo("Art.", idDe(art))} ↔ ${conPrefijo("Sección", idDe(sec))}`,
    docs: docDe(art) && docDe(sec) ? `${docDe(art)} ↔ ${docDe(sec)}` : "",
  };
}

/** Citas verificadas: ambas ok; si el modelo no halló fragmento del manual (no lo cubre), solo cuenta la de la norma. */
export function citasVerificadas(p: ParResuelto): boolean {
  const manualOk = p.cita_manual_ok || (p.cobertura === "nula" && !p.cita_manual);
  return p.cita_norma_ok && manualOk;
}

export function estadoCita(lado: "norma" | "manual", p: ParResuelto): string {
  if (lado === "manual" && p.cobertura === "nula" && !p.cita_manual) return "El modelo no encontró un fragmento del manual que lo cubra";
  return (lado === "norma" ? p.cita_norma_ok : p.cita_manual_ok)
    ? "Verificada en el texto"
    : "No pudimos confirmar esta cita; mostramos el fragmento más cercano del documento";
}

export interface ChipEstado { icono: string; texto: string; clase: string }
export function chipDe(f: FilaPar, cancelando: boolean): ChipEstado {
  if (f.tipo === "curso") return cancelando ? { icono: "cargando", texto: "Terminando", clase: "curso" } : { icono: "cargando", texto: "En análisis", clase: "curso" };
  switch (f.par.cobertura) {
    case "total": return { icono: "check", texto: "Cubre por completo", clase: "total" };
    case "parcial": return { icono: "mitad", texto: "Cubre en parte", clase: "parcial" };
    case "nula": return { icono: "equis", texto: "No lo cubre", clase: "nula" };
    default: return { icono: "aviso", texto: "Sin veredicto · revisar", clase: "revisar" };
  }
}
