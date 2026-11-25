// Prueba de navegador real (Brave o Chromium) contra la app, sin tocar el navegador personal del usuario: perfil limpio, headless.
// Comprueba lo que se afirma de la interfaz (D-64 fuentes, D-53 ejemplo sin aviso, botón único de plegar, CSP sin errores y que la app no confía en una cabecera de identidad falsificada).
//
//   NODE_PATH=<carpeta node_modules con playwright-core> node scripts/prueba_navegador.mjs http://localhost:8000
//   NODE_PATH=... node scripts/prueba_navegador.mjs https://<app>.databricksapps.com --perfil-databricks DEFAULT --navegador /usr/bin/brave-browser
//
// `playwright-core` NO es una dependencia del proyecto (docs/12): se usa el que ya tenga la máquina (p. ej. el de `npx playwright`). Con --perfil-databricks se usa el token del
// CLI de Databricks, solo como cabecera hacia ese mismo host, y nunca se imprime. Sale con código 0 si todo cumple y 1 si algo falla; las capturas van a --capturas.
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");

const args = process.argv.slice(2);
const opcion = (nombre, porDefecto = "") => { const i = args.indexOf(nombre); return i >= 0 ? args[i + 1] : porDefecto; };
const url = args.find((a) => /^https?:\/\//.test(a));
if (!url) { console.error("Uso: prueba_navegador.mjs URL [--perfil-databricks PERFIL] [--navegador RUTA] [--capturas CARPETA]"); process.exit(2); }
const perfil = opcion("--perfil-databricks");
const capturas = opcion("--capturas", "capturas-navegador");
if (perfil && !url.toLowerCase().startsWith("https://")) { console.error("Con --perfil-databricks la URL debe empezar por https:// (el token no viaja en claro)."); process.exit(2); }
const origen = new URL(url).origin;
mkdirSync(capturas, { recursive: true });

const token = perfil ? JSON.parse(execFileSync("databricks", ["auth", "token", "--profile", perfil, "-o", "json"], { encoding: "utf8" })).access_token : "";
const navegador = await chromium.launch({ headless: true, executablePath: opcion("--navegador") || undefined, args: process.getuid?.() === 0 ? ["--no-sandbox"] : [] });          // el sandbox de Chromium solo se quita si se corre como root (contenedor)
const contexto = await navegador.newContext({ viewport: { width: 1280, height: 900 }, locale: "es-EC" });
if (token) await contexto.route(`${origen}/**`, (ruta) => ruta.continue({ headers: { ...ruta.request().headers(), authorization: `Bearer ${token}` } }));   // solo hacia el host de la app

const pagina = await contexto.newPage();
const errores = [];
pagina.on("console", (m) => { if (m.type() === "error") errores.push(m.text()); });
pagina.on("pageerror", (e) => errores.push(String(e)));

const fallos = [];
const comprobar = (nombre, ok, detalle = "") => { console.log(`${ok ? "OK   " : "FALLA"} ${nombre}${detalle ? " · " + detalle : ""}`); if (!ok) fallos.push(nombre); };

console.log(`Navegador: ${(await navegador.version())} ${opcion("--navegador") ? "(" + opcion("--navegador") + ")" : ""}`);
await pagina.goto(url, { waitUntil: "networkidle" });
await pagina.getByRole("heading", { name: /Carga/i }).first().waitFor({ timeout: 30000 }).catch(() => {});
comprobar("la app carga y muestra el nombre del producto", (await pagina.title()).length > 0 && (await pagina.locator(".nombre-producto").count()) > 0, `título «${await pagina.title()}»`);

// D-64: IBM Plex Sans realmente descargada y aplicada
await pagina.evaluate(() => document.fonts.ready);
const tipografia = await pagina.evaluate(() => ({
  cargadas: [...document.fonts].filter((f) => f.status === "loaded").map((f) => `${f.family.replace(/"/g, "")} ${f.weight}`),
  pila: getComputedStyle(document.body).fontFamily,
}));
comprobar("IBM Plex Sans descargada por el navegador", tipografia.cargadas.some((f) => f.startsWith("IBM Plex Sans")), tipografia.cargadas.join(", "));
comprobar("el cuerpo usa IBM Plex Sans con la pila del sistema de respaldo", /^"?IBM Plex Sans"?,/.test(tipografia.pila) && /system-ui/.test(tipografia.pila));
await pagina.screenshot({ path: `${capturas}/1-carga.png` });

// D-53: el ejemplo no muestra el aviso del PDF. Tras «Cargar ejemplo» la app pasa directo a Selección.
await pagina.getByRole("button", { name: "Cargar ejemplo" }).click();
await pagina.getByRole("heading", { name: "Elige qué comparar" }).waitFor({ timeout: 60000 });
await pagina.locator("footer").getByRole("button", { name: "Comparar" }).waitFor({ timeout: 30000 });      // la pantalla completa, no solo el título
await pagina.waitForTimeout(1000);                                                                         // y asentada: una comprobación «no aparece…» solo vale si el aviso habría tenido tiempo de salir
comprobar("tras cargar el ejemplo no aparece el aviso modal del PDF", (await pagina.locator("dialog[open]").count()) === 0);
comprobar("la franja de selección no dice «Conserva los PDF originales» ni ofrece «Ver aviso»", (await pagina.getByText("Conserva los PDF originales").count()) === 0 && (await pagina.getByRole("button", { name: "Ver aviso" }).count()) === 0);
comprobar("la franja conserva «Agregar documentos»", (await pagina.getByRole("note").getByRole("button", { name: "Agregar documentos" }).count()) === 1);
await pagina.screenshot({ path: `${capturas}/2-seleccion.png` });

// botón único de plegar (D-65) en el árbol
const boton = pagina.getByRole("button", { name: /^(Contraer|Expandir) todo$/ }).first();
const antes = (await boton.innerText()).trim();
const filasAntes = await pagina.locator("[data-fila]").count();
await boton.click();
const despues = (await boton.innerText()).trim();
comprobar("un solo botón alterna «Contraer todo» y «Expandir todo»", antes !== despues && /todo$/.test(despues), `${antes} → ${despues}`);
comprobar("plegar oculta filas del árbol", antes === "Contraer todo" ? (await pagina.locator("[data-fila]").count()) < filasAntes : true, `${filasAntes} → ${await pagina.locator("[data-fila]").count()} filas`);
await pagina.screenshot({ path: `${capturas}/3-seleccion.png` });

// vuelta a Carga: la tabla de documentos del ejemplo
await pagina.locator("footer").getByRole("button", { name: "Agregar documentos" }).click();
await pagina.getByText("Indexado", { exact: true }).first().waitFor({ timeout: 30000 });
comprobar("la tabla dice «Indexado» para el ejemplo, sin «PDF no guardado»", (await pagina.getByText("PDF no guardado").count()) === 0 && (await pagina.getByText("Indexado", { exact: true }).count()) >= 1);
comprobar("la tabla no ofrece el «?» del PDF original para el ejemplo", (await pagina.getByRole("button", { name: "¿Qué significa Indexado?" }).count()) === 0);
await pagina.screenshot({ path: `${capturas}/4-carga-con-ejemplo.png` });

// identidad: la app no confía en una cabecera x-forwarded-email falsificada mientras TRUST_PROXY_IDENTITY esté apagada
const usuario = await pagina.evaluate(async () => (await (await fetch("/api/session", { headers: { "x-forwarded-email": "falso@otro-dominio.test" } })).json()).usuario);
const real = await pagina.evaluate(async () => (await (await fetch("/api/session")).json()).usuario);
comprobar("una cabecera de identidad falsificada no cambia al usuario de la sesión", usuario === real && !String(usuario).includes("falso"), `usuario de la sesión = ${usuario === "Sesión local" ? "«Sesión local» (identidad apagada)" : "(usuario real, no el falsificado)"}`);

// política de seguridad: ningún recurso bloqueado por la CSP y ningún error de página
const csp = errores.filter((e) => /Content Security Policy|Refused to/i.test(e));
comprobar("la política de seguridad no bloquea nada (fuentes incluidas)", csp.length === 0, csp[0] ?? "");
const otros = errores.filter((e) => !/Content Security Policy|Refused to/i.test(e));
comprobar("sin errores en la consola ni excepciones de la página", otros.length === 0, otros[0] ?? "");

await navegador.close();
console.log(`\nRESULTADO: ${fallos.length === 0 ? "todo cumple" : "FALLAN: " + fallos.join("; ")}  (capturas en ${capturas}/)`);
process.exit(fallos.length === 0 ? 0 : 1);
