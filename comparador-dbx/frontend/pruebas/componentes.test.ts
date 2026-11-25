// Componentes React: marcado inicial renderizado a HTML con react-dom/server (P-35, sin dependencias nuevas: ver pruebas/ayudas/componente.ts).
// No cubre eventos ni efectos (p. ej. el `onError` que oculta un logo roto): eso necesita un navegador.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { cargarComponente } from "./ayudas/componente.ts";

const { Marca, LogoPie, MARCA_POR_DEFECTO } = await cargarComponente("src/components/Marca.tsx");
const { Icono } = await cargarComponente("src/components/Icono.tsx");

const marca = (extra = {}) => ({ nombre_producto: "Comparador Normativo", texto_alternativo: "", logo_org: "", logo_producto: "", logo_pie: "", ...extra });
const html = (el: unknown) => renderToStaticMarkup(el as never);

test("Marca sin logos: las escalas decorativas y el nombre, sin ninguna imagen", () => {
  const s = html(h(Marca, { marca: marca() }));
  assert.ok(!s.includes("<img"));
  assert.match(s, /class="icono icono-escalas"[^>]*aria-hidden="true"/);
  assert.match(s, /<span class="nombre-producto">Comparador Normativo<\/span>/);
});

test("Marca con logo de la organización: alt «Logo de …» con la organización y «Logo» sin ella", () => {
  assert.match(html(h(Marca, { marca: marca({ logo_org: "/marca/a.svg", texto_alternativo: "Banco X" }) })), /<img class="logo-org" src="\/marca\/a\.svg" alt="Logo de Banco X"\/>/);
  assert.match(html(h(Marca, { marca: marca({ logo_org: "/marca/a.svg" }) })), /alt="Logo"/);
});

test("Marca con logo de producto: imagen decorativa (alt vacío) en lugar de las escalas; el nombre sigue visible", () => {
  const s = html(h(Marca, { marca: marca({ logo_producto: "/marca/p.svg" }) }));
  assert.match(s, /<img class="logo-prod" src="\/marca\/p\.svg" alt=""\/>/);
  assert.ok(!s.includes("icono-escalas"));
  assert.match(s, /Comparador Normativo/);
});

test("Marca: un nombre vacío cae al nombre por defecto y uno con HTML se escapa", () => {
  assert.match(html(h(Marca, { marca: marca({ nombre_producto: "" }) })), new RegExp(MARCA_POR_DEFECTO.nombre_producto));
  const s = html(h(Marca, { marca: marca({ nombre_producto: "<script>alert(1)</script>" }) }));
  assert.ok(!s.includes("<script>") && s.includes("&lt;script&gt;"));
});

test("LogoPie: sin logo no pinta nada; con logo, su alt", () => {
  assert.equal(html(h(LogoPie, { marca: marca() })), "");
  assert.match(html(h(LogoPie, { marca: marca({ logo_pie: "/marca/pie.svg", texto_alternativo: "Banco X" }) })), /<img class="logo-pie" src="\/marca\/pie\.svg" alt="Logo de Banco X"\/>/);
});

test("Icono: decorativo por defecto; con título se anuncia y lo muestra", () => {
  const deco = html(h(Icono, { nombre: "check" }));
  assert.match(deco, /aria-hidden="true"/);
  assert.ok(!deco.includes("role=") && !deco.includes("<title>"));
  const con = html(h(Icono, { nombre: "aviso", titulo: "Requiere revisión" }));
  assert.match(con, /role="img"/);
  assert.match(con, /aria-label="Requiere revisión"/);
  assert.match(con, /<title>Requiere revisión<\/title>/);
  assert.ok(!con.includes("aria-hidden"));
});

test("Icono: cada nombre pinta un trazo y la clase del icono", () => {
  for (const n of ["escalas", "ajustes", "subir", "check", "equis", "info", "aviso", "abajo", "derecha", "cargando", "mitad"]) {
    const s = html(h(Icono, { nombre: n }));
    assert.match(s, new RegExp(`class="icono icono-${n}"`));
    assert.match(s, /<(path|circle)/);
  }
});

test("el ayudante rechaza una ruta fuera de src/", async () => {
  await assert.rejects(() => cargarComponente("../backend/main.py"), /Solo se cargan componentes de src/);
  await assert.rejects(() => cargarComponente("/etc/passwd"), /Solo se cargan componentes de src/);
});
