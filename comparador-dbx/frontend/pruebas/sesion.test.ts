// Lógica pura de sesión múltiple: quitar documentos, marcas, un solo manual, cupo, aviso y pérdida de sesión.
import assert from "node:assert/strict";
import { test } from "node:test";
import { hayConflictoDeManuales, manualesConMarcas, quitarDeArboles, seleccionTrasRecarga } from "../src/arbol.ts";
import { inicial, reducir } from "../src/reductor.ts";
import { cupoLibre, evaluarLote, idsParaAviso, motivoPerdida, unirAvisados, type Recuerdo } from "../src/sesion.ts";
import type { ArbolDocOut, ComparacionOut, DocumentoOut, NodoOut, SesionOut } from "../src/tipos.ts";

const nodo = (id: string): NodoOut => ({ id, identificador: id, titulo: "", preview: "", hoja: true, incierto: false, excluida: false, motivo: "", seleccionada: true, pagina_inicio: 1, hijos: [] });
const arbol = (doc_id: string, ids: string[]): ArbolDocOut => ({ doc_id, nombre: doc_id, nodos: ids.map(nodo), avisos: [] });
const doc = (id: string, estado: DocumentoOut["estado"] = "listo") => ({ id, nombre: id, estado } as DocumentoOut);
const ses = (docs: DocumentoOut[], extra: Partial<SesionOut> = {}): SesionOut => ({ documentos: docs, comparacion_id: null, ...extra });

test("quitar un documento conserva lista, árboles y marcas de los demás", () => {
  const e = { ...inicial, paso: "carga" as const, seleccionLista: true, documentos: [doc("N1"), doc("M1"), doc("M2")],
    normas: [arbol("N1", ["A1"])], manuales: [arbol("M1", ["S1"]), arbol("M2", ["T1"])], seleccion: new Set(["A1", "S1", "T1"]) };
  const r = reducir(e, { t: "quitar", id: "M2", sesion: ses([doc("N1"), doc("M1")], { comparacion_id: null }) });
  assert.deepEqual(r.documentos.map((d) => d.id), ["N1", "M1"]);
  assert.deepEqual(r.manuales?.map((a) => a.doc_id), ["M1"]);
  assert.deepEqual([...r.seleccion].sort(), ["A1", "S1"]);
  assert.equal(r.seleccionLista, true);
});

test("quitar un procesado descarta la comparación y deshabilita Resultados; si el servidor la conserva, sigue", () => {
  const c = { id: "C1" } as ComparacionOut;
  const e = { ...inicial, paso: "carga" as const, comparacion: c, documentos: [doc("N1"), doc("M1")] };
  assert.equal(reducir(e, { t: "quitar", id: "M1", sesion: ses([doc("N1")]) }).comparacion, null);
  assert.equal(reducir(e, { t: "quitar", id: "M1", sesion: ses([doc("N1")], { comparacion_id: "C1" }) }).comparacion, c);
});

test("quitarDeArboles ignora un documento sin árbol", () => {
  const r = quitarDeArboles([arbol("N1", ["A1"])], [], new Set(["A1"]), "X");
  assert.deepEqual([...r.seleccion], ["A1"]);
});

test("al agregar documentos se conservan las marcas; el manual nuevo llega sin marcas si ya hay otro con marcas", () => {
  const n1 = arbol("N1", ["A1", "A2"]), m1 = arbol("M1", ["S1", "S2"]), m2 = arbol("M2", ["T1"]), n2 = arbol("N2", ["B1"]);
  const s = seleccionTrasRecarga(new Set(["A2", "S1"]), [n1, m1], [n1, n2], [m1, m2]);
  assert.deepEqual([...s].sort(), ["A2", "B1", "S1"]);                 // T1 (manual nuevo) no entra
});

test("si ningún manual visto tiene marcas, solo el primer manual nuevo se preselecciona", () => {
  const m1 = arbol("M1", ["S1"]), m2 = arbol("M2", ["T1"]);
  assert.deepEqual([...seleccionTrasRecarga(new Set(), [], [], [m1, m2])], ["S1"]);
  assert.deepEqual([...seleccionTrasRecarga(new Set(), [m1], [], [m1, m2])], ["T1"]);   // M1 ya visto y sin marcas
});

test("conflicto: marcas en más de un manual", () => {
  const m1 = arbol("M1", ["S1"]), m2 = arbol("M2", ["T1"]);
  assert.equal(hayConflictoDeManuales([m1, m2], new Set(["S1"])), false);
  assert.equal(hayConflictoDeManuales([m1, m2], new Set(["S1", "T1"])), true);
  assert.deepEqual(manualesConMarcas([m1, m2], new Set(["T1"])).map((m) => m.doc_id), ["M2"]);
});

test("cupo: los fallidos no cuentan y el lote que excede no se envía", () => {
  const docs = [doc("A"), doc("B"), doc("C", "error")];
  assert.equal(cupoLibre(docs, 3), 1);
  assert.equal(cupoLibre(docs, undefined), null);
  const f = (name: string) => ({ name });
  const r = evaluarLote([f("a.pdf"), f("b.PDF")], 1, 3);
  assert.deepEqual(r.enviar, []);
  assert.match(r.avisos[0], /Solo cabe 1 documento más \(máximo 3\)/);
  const q = evaluarLote([f("a.pdf"), f("nota.docx")], 2, 3);
  assert.deepEqual(q.enviar.map((x) => x.name), ["a.pdf"]);
  assert.equal(q.avisos[0], "Solo se aceptan archivos PDF. No se agregó: nota.docx.");
});

test("aviso: solo documentos indexados no avisados, y la lista no se arrastra a otra sesión del servidor", () => {
  const docs = [doc("D1"), doc("D2"), doc("D3", "error")];
  assert.deepEqual(idsParaAviso(docs, null, 10), ["D1", "D2"]);
  const av = unirAvisados(null, 10, ["D1"]);
  assert.deepEqual(idsParaAviso(docs, av, 10), ["D2"]);
  assert.deepEqual(idsParaAviso(docs, av, 11), ["D1", "D2"]);
  assert.deepEqual(unirAvisados(av, 11, ["D2"]).ids, ["D2"]);
});

const rec: Recuerdo = { usuario: "u", docs: 2, iniciada_ts: 100, ultima_ms: 0, trabajo: false };
const base = { recuerdo: rec, usuario: "u", sesion_nueva: false, iniciada_ts: 200, docs: 0, perdidaConocida: false, retencionHoras: 48 };

test("pérdida: expirada si pasó más que la retención; reinicio en otro caso; nada si no se recordaba nada", () => {
  const hora = 3600 * 1000;
  assert.equal(motivoPerdida({ ...base, ahoraMs: 49 * hora }), "expirada");
  assert.equal(motivoPerdida({ ...base, ahoraMs: 2 * hora }), "reinicio");
  assert.equal(motivoPerdida({ ...base, recuerdo: null, ahoraMs: 2 * hora }), null);
  assert.equal(motivoPerdida({ ...base, ahoraMs: 2 * hora, iniciada_ts: 100 }), null);           // misma sesión del servidor
  assert.equal(motivoPerdida({ ...base, ahoraMs: 2 * hora, docs: 1 }), null);                    // hay documentos
  assert.equal(motivoPerdida({ ...base, recuerdo: { ...rec, usuario: "otro" }, ahoraMs: 2 * hora }), null);
});

test("pérdida: sesion_nueva y 410 la muestran; quien no tenía nada cargado no perdió nada", () => {
  assert.equal(motivoPerdida({ ...base, recuerdo: null, sesion_nueva: true, ahoraMs: 1 }), "reinicio");
  assert.equal(motivoPerdida({ ...base, recuerdo: { ...rec, docs: 0 }, sesion_nueva: true, ahoraMs: 1 }), null);
  assert.equal(motivoPerdida({ ...base, perdidaConocida: true, ahoraMs: 49 * 3600 * 1000 }), "expirada");
});

test("reenganche y fin de trabajo: el estado sigue al trabajo activo", () => {
  const r = reducir(inicial, { t: "reenganchar", trabajo: { id: "J1", tipo: "comparacion" } });
  assert.equal(r.paso, "comparando");
  assert.equal(r.reenganche?.id, "J1");
  assert.equal(reducir(r, { t: "job", job: null }).trabajoActivo, null);
});
