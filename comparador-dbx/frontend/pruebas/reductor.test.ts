// Lógica pura del frontend (sin React ni navegador): se corre con `npm test` (node:test, sin dependencias nuevas).
import assert from "node:assert/strict";
import { test } from "node:test";
import { hojas, seleccionInicial, seleccionTrasRecarga } from "../src/arbol.ts";
import { inicial, listos, reducir } from "../src/reductor.ts";
import type { ArbolDocOut, DocumentoOut, NodoOut } from "../src/tipos.ts";

const nodo = (id: string, extra: Partial<NodoOut> = {}): NodoOut => ({
  id, identificador: id, titulo: "", preview: "", hoja: true, incierto: false, excluida: false, motivo: "", seleccionada: true, pagina_inicio: 1, hijos: [], ...extra,
});
const arbol = (doc_id: string, nodos: NodoOut[]): ArbolDocOut => ({ doc_id, nombre: doc_id, nodos, avisos: [] });
const doc = (id: string, estado: DocumentoOut["estado"]) => ({ id, nombre: id, estado } as DocumentoOut);

test("hojas recorre el índice hasta los artículos", () => {
  const n = nodo("T1", { hoja: false, hijos: [nodo("C1", { hoja: false, hijos: [nodo("A1"), nodo("A2")] }), nodo("A3")] });
  assert.deepEqual(hojas(n).map((h) => h.id), ["A1", "A2", "A3"]);
});

test("la selección inicial toma lo seleccionado y no excluido", () => {
  const a = arbol("D1", [nodo("A1"), nodo("A2", { excluida: true, seleccionada: false }), nodo("A3", { seleccionada: false })]);
  assert.deepEqual([...seleccionInicial([a])], ["A1"]);
});

test("procesar un documento nuevo pide recargar la selección; los mismos documentos la conservan", () => {
  const lista = { ...inicial, seleccionLista: true, documentos: [doc("D1", "listo"), doc("D2", "listo")] };
  assert.equal(reducir(lista, { t: "documentos", documentos: [doc("D1", "listo"), doc("D2", "listo")] }).seleccionLista, true);
  assert.equal(reducir(lista, { t: "documentos", documentos: [doc("D1", "listo"), doc("D2", "listo"), doc("D3", "listo")] }).seleccionLista, false);
  assert.equal(reducir(lista, { t: "documentos", documentos: [doc("D1", "listo"), doc("D2", "error")] }).seleccionLista, false);
  assert.equal(listos([doc("B", "listo"), doc("A", "listo"), doc("C", "cargado")]), "A,B");
});

test("al recargar se conservan las marcas del auditor y solo los documentos nuevos entran con su preselección", () => {
  const viejoN = arbol("N1", [nodo("A1"), nodo("A2")]), viejoM = arbol("M1", [nodo("S1"), nodo("S2")]);
  const nuevoN = arbol("N2", [nodo("B1"), nodo("B2", { seleccionada: false })]);
  const previa = new Set(["A2", "S1", "ya-no-existe"]);               // el auditor había desmarcado A1 y S2
  const s = seleccionTrasRecarga(previa, [viejoN, viejoM], [viejoN, nuevoN], [viejoM]);
  assert.deepEqual([...s].sort(), ["A2", "B1", "S1"]);                // A1 y S2 siguen desmarcados; B1 entra; lo que ya no existe se descarta
});

test("sesión perdida y reinicio vuelven al estado inicial", () => {
  const e = { ...inicial, paso: "seleccion" as const, seleccion: new Set(["A1"]) };
  assert.equal(reducir(e, { t: "sesionPerdida" }).sesionPerdida, true);
  assert.equal(reducir(e, { t: "sesionPerdida" }).paso, "carga");
  assert.equal(reducir(e, { t: "reiniciar" }).seleccion.size, 0);
});
