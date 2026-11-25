// Compila un componente .tsx con el propio Vite (sin dependencias nuevas) y lo carga para renderizarlo a HTML con react-dom/server (P-35).
// Solo prueba el marcado inicial (sin eventos ni efectos): lo interactivo sigue pendiente de una prueba en navegador.
import { mkdirSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "vite";

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const salida = join(raiz, "node_modules", ".cache", "pruebas-componentes");

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function cargarComponente(rutaRelativa: string): Promise<Record<string, any>> {
  const entrada = resolve(raiz, rutaRelativa);
  if (!entrada.startsWith(join(raiz, "src") + sep)) throw new Error(`Solo se cargan componentes de src/: ${rutaRelativa}`);      // nunca código de fuera del propio frontend
  const resultado = await build({
    root: raiz, configFile: false, logLevel: "silent", plugins: [],
    oxc: { jsx: { runtime: "automatic" } },
    build: { ssr: entrada, write: false, minify: false, target: "node20", rollupOptions: { output: { format: "es" } } },
  });
  const salidas = (Array.isArray(resultado) ? resultado[0].output : "output" in resultado ? resultado.output : []) as { type: string; isEntry?: boolean; code?: string }[];
  const codigo = salidas.find((o) => o.type === "chunk" && o.isEntry)?.code ?? "";
  mkdirSync(salida, { recursive: true });
  const archivo = join(salida, createHash("sha1").update(entrada + codigo).digest("hex").slice(0, 12) + ".mjs");
  writeFileSync(archivo, codigo);
  return import(pathToFileURL(archivo).href);
}
