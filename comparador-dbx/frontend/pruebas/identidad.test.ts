// Identidad visual paramétrica (docs/ux/identidad-visual-v1.md §6): el bloque :root es el único lugar con valores visuales y cada par
// de colores cumple WCAG 2.2 AA. Quien sustituya la paleta por la del banco corre `npm test` y ve qué par falla.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const css = readFileSync(new URL("../src/estilos.css", import.meta.url), "utf-8");
const inicio = css.indexOf(":root");
const fin = css.indexOf("\n}\n", inicio) + 3;
const raiz = css.slice(inicio, fin);
const resto = css.slice(0, inicio) + css.slice(fin);

const T: Record<string, string> = {};
for (const m of raiz.matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})\b/g)) T[m[1]] = m[2];
const TODOS: Record<string, string> = {};                  // todos los tokens del :root, también los que no son color
for (const m of raiz.matchAll(/(--[\w-]+):\s*([^;]+);/g)) TODOS[m[1]] = m[2].trim();
for (const [k, v] of Object.entries(TODOS)) {              // un alias var(--otro) toma el color real del otro
  const alias = v.match(/^var\((--[\w-]+)\)$/);
  if (alias && T[alias[1]]) T[k] = T[alias[1]];
}

const luz = (hex: string) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const contraste = (a: string, b: string) => {
  const [x, y] = [luz(T[a]), luz(T[b])].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

// Texto ≥ 4,5:1 (WCAG 1.4.3)
const TEXTO: [string, string][] = [
  ["--texto", "--superficie"], ["--texto", "--fondo"], ["--texto", "--neutro-fondo"],
  ["--texto-suave", "--superficie"], ["--texto-suave", "--fondo"], ["--texto-suave", "--marca-claro"], ["--texto-suave", "--pista"], ["--texto-suave", "--suave-1"], ["--texto-suave", "--suave-2"],
  ["--sobre-marca", "--marca"], ["--sobre-marca", "--marca-osc"], ["--marca", "--marca-claro"], ["--marca-osc", "--marca-claro"], ["--marca", "--superficie"], ["--marca", "--fondo"],
  ["--sobre-A", "--A"], ["--sobre-L", "--L"], ["--sobre-R", "--R"], ["--sobre-X", "--X"], ["--sobre-P", "--P"], ["--R", "--superficie"], ["--R", "--fondo"],
  ["--aviso-texto", "--aviso-fondo"], ["--aviso-texto", "--superficie"], ["--aviso-texto", "--fondo"], ["--parcial-texto", "--parcial-fondo"],
  ["--error-texto", "--error-fondo"], ["--error-texto", "--superficie"], ["--info-texto", "--info-fondo"],
  ["--ok-texto", "--ok-fondo"], ["--ok-texto", "--superficie"], ["--texto-suave", "--marca-claro"], ["--marca-osc", "--marca-claro"],
];
// Componentes e iconos ≥ 3:1 (WCAG 1.4.11)
const COMPONENTE: [string, string][] = [
  ["--borde-control", "--superficie"], ["--borde-control", "--fondo"], ["--foco", "--superficie"], ["--foco", "--fondo"], ["--marca", "--fondo"], ["--marca", "--pista"], ["--acento", "--superficie"], ["--acento", "--fondo"],
];

test("todos los tokens de color del bloque :root son #rrggbb medibles", () => {
  for (const t of [...TEXTO, ...COMPONENTE].flat()) assert.ok(T[t], `falta o no es #rrggbb el token ${t}`);
});

test("el texto secundario llega a 7:1 sobre blanco y sobre el fondo (objetivo reforzado)", () => {
  for (const f of ["--superficie", "--fondo"]) assert.ok(contraste("--texto-suave", f) >= 7, `--texto-suave sobre ${f}: ${contraste("--texto-suave", f).toFixed(2)} (< 7)`);
});

test("texto: cada par cumple 4,5:1", () => {
  for (const [a, b] of TEXTO) assert.ok(contraste(a, b) >= 4.5, `${a} sobre ${b}: ${contraste(a, b).toFixed(2)} (< 4,5)`);
});

test("componentes: cada par cumple 3:1", () => {
  for (const [a, b] of COMPONENTE) assert.ok(contraste(a, b) >= 3, `${a} sobre ${b}: ${contraste(a, b).toFixed(2)} (< 3)`);
});

test("ninguna regla fuera de :root lleva colores literales", () => {
  const sinComentarios = resto.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.deepEqual(sinComentarios.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(/g) ?? [], []);
});

test("el CSS no supera el doble del tamaño de partida (32 KB)", () => {
  assert.ok(Buffer.byteLength(css) <= 32 * 1024, `estilos.css pesa ${Buffer.byteLength(css)} bytes`);
});

test("hay un solo :root: un segundo bloque podría cambiar un token sin pasar por la medición", () => {
  assert.equal((css.match(/:root/g) ?? []).length, 1);
});

test("fuera de :root tampoco hay hsl(), color-mix con literales ni colores con nombre", () => {
  const sinComentarios = resto.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.deepEqual(sinComentarios.match(/\bhsla?\(|\bhwb\(|\blab\(|\blch\(|\boklch\(/g) ?? [], []);
  const NOMBRES = "white|black|red|green|blue|gray|grey|orange|yellow|purple|pink|brown|silver|navy|teal|maroon|lime|aqua|fuchsia|olive";
  const propiedades = sinComentarios.match(new RegExp(`(?:color|background|border[\\w-]*|outline[\\w-]*|fill|stroke)\\s*:[^;}]*\\b(?:${NOMBRES})\\b`, "gi")) ?? [];
  assert.deepEqual(propiedades, []);
});

test("todo var(--token) usado en una regla está definido en :root", () => {
  const sinComentarios = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const usados = new Set([...sinComentarios.matchAll(/var\((--[\w-]+)/g)].map((m) => m[1]));
  assert.deepEqual([...usados].filter((u) => !(u in TODOS)), []);
});

test("fuera de :root los radios y las fuentes salen de tokens (sin px ni nombres de fuente literales)", () => {
  const sinComentarios = resto.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.deepEqual(sinComentarios.match(/border(?:-[a-z]+)*-radius\s*:[^;}]*\d(?:px|rem|em|%)/g) ?? [], []);
  assert.deepEqual(sinComentarios.match(/font-family\s*:(?!\s*(?:var\(|inherit))[^;}]*/g) ?? [], []);
});

test("ningún carácter hace de icono en los componentes: se usa <Icono> (la única excepción es el título de la pestaña)", () => {
  const dir = new URL("../src/", import.meta.url);
  const archivos = ["App.tsx", "pages/Ajustes.tsx", "pages/Results.tsx", "pages/Selector.tsx", "pages/Processing.tsx", "components/ComparacionEnCurso.tsx",
    "components/DocTable.tsx", "components/DropZone.tsx", "components/DualTree.tsx", "components/Marca.tsx", "progresoComparacion.ts"];
  for (const a of archivos) {
    const codigo = readFileSync(new URL(a, dir), "utf-8").replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, "").replace(/document\.title = `[^`]*`/g, "");
    assert.deepEqual(codigo.match(/[⚖⚙⬆⚠✓✔▸▾◌◐✕]/g) ?? [], [], `${a} usa un carácter como icono`);
  }
});

test("la cabecera no se mueve entre pantallas: barra reservada, mismo peso en los pasos, paso actual legible aunque esté deshabilitado y sitio para el estado del servicio", () => {
  assert.match(css, /html\s*\{[^}]*scrollbar-gutter:\s*stable/);
  assert.match(css, /\.paso\s*\{[^}]*font-weight:\s*600/);
  assert.doesNotMatch(css, /\.paso\.activo\s*\{[^}]*font-weight/);                       // el activo no cambia de peso: ensancharía su botón
  assert.match(css, /\.paso\.activo:disabled\s*\{[^}]*opacity:\s*1/);
  assert.match(css, /\.estado-servicio\s*\{[^}]*min-width/);
});
