// Lógica pura de «Comparando»: orden, filtros, retención, paginación, anuncios, estimado y cancelación.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  accionCancelar, anuncioInicial, chipDe, citasVerificadas, contarNuevos, contarPorFiltro, corteVisible, debeRetener, estadoCita, etiquetaPar,
  filtrar, ordenarFilas, paginar, paresPorPagina, estimadoDesdePares, resueltosDe, siguienteAnuncio, textoCancelada, textoConfirmacion,
  textoContador, textoEstimado, textoFase, trabajoTerminado, unirResueltos, type DatosAnuncio,
} from "../src/progresoComparacion.ts";
import type { JobOut, ParEnCurso, ParResuelto } from "../src/tipos.ts";

const par = (seq: number, cobertura: ParResuelto["cobertura"] = "total", extra: Partial<ParResuelto> = {}): ParResuelto => ({
  seq, par_id: `p${seq}`, articulo: `A${seq}`, seccion: `S${seq}`, cobertura, naturaleza: "", confianza: 0.9,
  cita_norma_ok: true, cita_manual_ok: true, requiere_revision: false, comentario: "", ...extra,
});
const curso = (id: string) => ({ par_id: id } as ParEnCurso);

test("ordenar: en análisis arriba y resueltos del más reciente al más antiguo", () => {
  const f = ordenarFilas([curso("x"), curso("y")], [par(1), par(3), par(2)]);
  assert.deepEqual(f.map((x) => x.clave), ["c-x", "c-y", "r-3", "r-2", "r-1"]);
});

test("unir: sin repetir seq y con el más reciente primero; sirve con un backend sin pares_resueltos", () => {
  const u = unirResueltos([par(2), par(1)], [par(3), par(2)]);
  assert.deepEqual(u.map((p) => p.seq), [3, 2, 1]);
  const viejo = { ultimos_veredictos: [par(5)] } as unknown as JobOut;
  assert.deepEqual(resueltosDe(viejo).map((p) => p.seq), [5]);
  assert.deepEqual(resueltosDe({ pares_resueltos: [par(7)], ultimos_veredictos: [par(5)] } as unknown as JobOut).map((p) => p.seq), [7]);
});

test("contar y filtrar: el número de cada chip coincide con las filas que deja", () => {
  const rs = [par(1, "total"), par(2, "parcial"), par(3, "nula"), par(4, "nula"), par(5, "sin_veredicto"), par(6, "total", { requiere_revision: true })];
  const c = contarPorFiltro(rs);
  assert.deepEqual(c, { todos: 6, total: 2, parcial: 1, nula: 2, revisar: 2 });
  for (const f of ["todos", "total", "parcial", "nula", "revisar"] as const) assert.equal(filtrar(rs, f).length, c[f]);
});

test("paginar: 50 por página y cuántos quedan", () => {
  const rs = Array.from({ length: 300 }, (_, i) => par(i + 1));
  const p1 = paginar(rs, 1, 50);
  assert.equal(p1.visibles.length, 50); assert.equal(p1.quedan, 250);
  assert.equal(paginar(rs, 6, 50).quedan, 0);
  assert.equal(paginar(rs, 7, 50).visibles.length, 300);
  assert.equal(paresPorPagina({} as JobOut), 50); assert.equal(paresPorPagina({ pares_por_pagina: 20 } as JobOut), 20);
  assert.equal(estimadoDesdePares({} as JobOut), 3); assert.equal(estimadoDesdePares({ estimado_desde_pares: 5 } as JobOut), 5);
});

test("retención: fila abierta, foco o más de una fila bajada retienen; si no, se muestra todo", () => {
  assert.equal(debeRetener({ filasAbiertas: 0, focoEnLista: false, filasBajadas: 1 }), false);
  assert.equal(debeRetener({ filasAbiertas: 1, focoEnLista: false, filasBajadas: 0 }), true);
  assert.equal(debeRetener({ filasAbiertas: 0, focoEnLista: true, filasBajadas: 0 }), true);
  assert.equal(debeRetener({ filasAbiertas: 0, focoEnLista: false, filasBajadas: 2 }), true);
  const rs = [par(1), par(2), par(3), par(4), par(5)];
  assert.equal(corteVisible(2, 5, true), 2);
  assert.equal(contarNuevos(rs, corteVisible(2, 5, true)), 3);      // «3 resultados nuevos · Mostrar»
  assert.equal(corteVisible(2, 5, false), 5);
  assert.equal(contarNuevos(rs, 5), 0);
});

const dat = (x: Partial<DatosAnuncio> = {}): DatosAnuncio =>
  ({ fase: "juzgando", etapa: "", estado: "en_curso", cancelando: false, espera: false, hechos: 0, total: 40, porRevisar: 0, ...x });

test("anuncios: solo hitos; nunca uno por par", () => {
  let e = anuncioInicial;
  let r = siguienteAnuncio(e, dat(), 0);                       // cambio de fase
  assert.equal(r.texto, "Paso 2 de 3 · Evaluando cada par"); e = r.estado;
  for (let h = 1; h <= 3; h++) { r = siguienteAnuncio(e, dat({ hechos: h }), h); assert.equal(r.texto, null); e = r.estado; }   // 7,5 % y menos; y <60 s
  r = siguienteAnuncio(e, dat({ hechos: 8 }), 30); assert.equal(r.texto, null);                // 20 % pero solo pasaron 30 s
  r = siguienteAnuncio(e, dat({ hechos: 12, porRevisar: 3 }), 61); assert.equal(r.texto, "12 de 40 pares resueltos; 3 por revisar."); e = r.estado;
  r = siguienteAnuncio(e, dat({ hechos: 17 }), 62); assert.equal(r.texto, null);               // otro 10 %, pero antes de 60 s
  r = siguienteAnuncio(e, dat({ hechos: 17 }), 122); assert.equal(r.texto, "17 de 40 pares resueltos; 0 por revisar."); e = r.estado;
});

test("anuncios: espera del proveedor, cancelación y fin se anuncian una sola vez", () => {
  let r = siguienteAnuncio({ ...anuncioInicial, fase: "juzgando" }, dat({ espera: true }), 1);
  assert.match(r.texto ?? "", /Esperando al servicio de IA/);
  assert.equal(siguienteAnuncio(r.estado, dat({ espera: true }), 2).texto, null);
  r = siguienteAnuncio(r.estado, dat({ cancelando: true }), 3); assert.equal(r.texto, "Cancelando la comparación.");
  r = siguienteAnuncio(r.estado, dat({ cancelando: true, estado: "cancelado" }), 4); assert.equal(r.texto, "Comparación cancelada.");
  assert.equal(siguienteAnuncio(r.estado, dat({ estado: "cancelado" }), 5).texto, null);
  const f = siguienteAnuncio({ ...anuncioInicial, fase: "armando" }, dat({ fase: "armando", estado: "listo", hechos: 40, porRevisar: 2 }), 6);
  assert.equal(f.texto, "Comparación terminada: 40 de 40 pares resueltos; 2 por revisar.");
});

test("texto de fase", () => {
  assert.equal(textoFase("recuperando").texto, "Paso 1 de 3 · Buscando coincidencias");
  assert.equal(textoFase("juzgando").texto, "Paso 2 de 3 · Evaluando cada par");
  assert.equal(textoFase("armando").texto, "Paso 3 de 3 · Armando el papel de trabajo");
  assert.deepEqual(textoFase("otra", "En cola"), { paso: null, texto: "En cola" });
});

test("estimado: rango desde el umbral; antes, aviso; fuera de la fase 2, nada", () => {
  assert.equal(textoEstimado("juzgando", 2, 40, 360), "Todavía no podemos estimar el tiempo restante.");
  assert.equal(textoEstimado("juzgando", 0, 40, 10), "Todavía no podemos estimar el tiempo restante.");
  // 3 pares en 300 s → faltan 37 × 100 s = 3700 s; ±35 %
  assert.equal(textoEstimado("juzgando", 3, 40, 300), "Falta aproximadamente: entre 40 min 5 s y 1 h 23 min");
  assert.equal(textoEstimado("juzgando", 3, 40, 300, 5), "Todavía no podemos estimar el tiempo restante.");   // umbral del servidor = 5
  assert.equal(textoEstimado("recuperando", 3, 40, 300), null);
  assert.equal(textoEstimado("armando", 40, 40, 300), null);
});

test("cancelar: sin pares directo; con pares confirma y muestra N; textos", () => {
  assert.equal(accionCancelar(0), "directo");
  assert.equal(accionCancelar(1), "confirmar");
  assert.equal(textoConfirmacion(12), "¿Cancelar la comparación? Ya resolvimos 12 pares.");
  assert.equal(textoConfirmacion(1), "¿Cancelar la comparación? Ya resolvimos 1 par.");
  assert.equal(textoCancelada(12), "Comparación cancelada. Los 12 pares resueltos no se conservan.");
  assert.equal(textoCancelada(1), "Comparación cancelada. El par resuelto no se conserva.");
  assert.equal(textoCancelada(0), "Comparación cancelada.");
});

test("contador: «en análisis / en espera» solo con trabajo en curso; el aviso de reenganche cae al terminar", () => {
  assert.equal(textoContador(3, 10, 2, true), "3 de 10 pares resueltos · 2 en análisis · 5 en espera");
  assert.equal(textoContador(3, 10, 2, false), "3 de 10 pares resueltos");
  assert.equal(textoContador(0, 10, 0, false), "0 de 10 pares resueltos");
  assert.deepEqual(["en_curso", "en_cola", "listo", "cancelado", "error"].map(trabajoTerminado), [false, false, true, true, true]);
});

test("filas: etiqueta, citas y chips", () => {
  const frag = (identificador: string, documento: string) => ({ identificador, documento, pagina: 1, preview: "" });
  assert.equal(etiquetaPar(frag("12", "Norma X"), frag("5.2", "Manual Y")), "Art. 12 · Norma X ↔ Sección 5.2 · Manual Y");
  assert.equal(etiquetaPar("Art. 12", "5.2"), "Art. 12 ↔ Sección 5.2");
  assert.equal(citasVerificadas(par(1)), true);
  assert.equal(citasVerificadas(par(1, "total", { cita_manual_ok: false })), false);
  assert.equal(citasVerificadas(par(1, "nula", { cita_manual_ok: false, cita_manual: "" })), true);
  assert.equal(estadoCita("manual", par(1, "nula", { cita_manual_ok: false, cita_manual: "" })), "El modelo no encontró un fragmento del manual que lo cubra");
  assert.equal(estadoCita("norma", par(1)), "Verificada en el texto");
  assert.match(estadoCita("norma", par(1, "total", { cita_norma_ok: false })), /No pudimos confirmar/);
  assert.equal(chipDe({ tipo: "curso", clave: "c", par: curso("x") }, false).texto, "En análisis");
  assert.equal(chipDe({ tipo: "curso", clave: "c", par: curso("x") }, true).texto, "Terminando");
  assert.equal(chipDe({ tipo: "resuelto", clave: "r", par: par(1, "nula") }, false).clase, "nula");
  assert.equal(chipDe({ tipo: "resuelto", clave: "r", par: par(1, "sin_veredicto") }, false).texto, "Sin veredicto · revisar");
});
