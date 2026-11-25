// Marca, logo del pie e iconos (identidad visual): marcado inicial y el comportamiento que antes no se podía probar (un logo que no carga).
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { Icono } from "../../src/components/Icono";
import { LogoPie, Marca, MARCA_POR_DEFECTO } from "../../src/components/Marca";

const marca = (extra = {}) => ({ nombre_producto: "Comparador Normativo", texto_alternativo: "", logo_org: "", logo_producto: "", logo_pie: "", ...extra });

describe("Marca", () => {
  test("sin logos: las escalas decorativas y el nombre, sin ninguna imagen", () => {
    const { container } = render(<Marca marca={marca()} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".icono-escalas")?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByText("Comparador Normativo")).toBeTruthy();
  });

  test("logo de la organización: alt «Logo de …» con la organización y «Logo» sin ella", () => {
    const { unmount } = render(<Marca marca={marca({ logo_org: "/marca/a.svg", texto_alternativo: "Banco X" })} />);
    expect(screen.getByAltText("Logo de Banco X").getAttribute("src")).toBe("/marca/a.svg");
    unmount();
    render(<Marca marca={marca({ logo_org: "/marca/a.svg" })} />);
    expect(screen.getByAltText("Logo")).toBeTruthy();
  });

  test("logo de producto: imagen decorativa (alt vacío) en lugar de las escalas; el nombre sigue visible", () => {
    const { container } = render(<Marca marca={marca({ logo_producto: "/marca/p.svg" })} />);
    const img = container.querySelector("img.logo-prod");
    expect(img?.getAttribute("alt")).toBe("");
    expect(container.querySelector(".icono-escalas")).toBeNull();
    expect(screen.getByText("Comparador Normativo")).toBeTruthy();
  });

  test("un nombre vacío cae al nombre por defecto y uno con HTML se muestra como texto, sin crear elementos", () => {
    const { container, unmount } = render(<Marca marca={marca({ nombre_producto: "" })} />);
    expect(screen.getByText(MARCA_POR_DEFECTO.nombre_producto)).toBeTruthy();
    unmount();
    const r = render(<Marca marca={marca({ nombre_producto: "<script>alert(1)</script>" })} />);
    expect(screen.getByText("<script>alert(1)</script>")).toBeTruthy();
    expect(r.container.querySelector("script")).toBeNull();
    expect(container).toBeTruthy();
  });

  test("un logo que no carga se oculta (sin icono de imagen rota) y queda el nombre", () => {
    render(<Marca marca={marca({ logo_org: "/marca/roto.svg", texto_alternativo: "Banco X" })} />);
    const img = screen.getByAltText("Logo de Banco X");
    fireEvent.error(img);
    expect(screen.queryByAltText("Logo de Banco X")).toBeNull();
    expect(screen.getByText("Comparador Normativo")).toBeTruthy();
  });
});

describe("LogoPie", () => {
  test("sin logo no pinta nada; con logo, su alt; y si no carga, se oculta", () => {
    const vacio = render(<LogoPie marca={marca()} />);
    expect(vacio.container.innerHTML).toBe("");
    vacio.unmount();
    render(<LogoPie marca={marca({ logo_pie: "/marca/pie.svg", texto_alternativo: "Banco X" })} />);
    const img = screen.getByAltText("Logo de Banco X");
    expect(img.getAttribute("src")).toBe("/marca/pie.svg");
    fireEvent.error(img);
    expect(screen.queryByAltText("Logo de Banco X")).toBeNull();
  });
});

describe("Icono", () => {
  test("decorativo por defecto; con título se anuncia y lo muestra", () => {
    const deco = render(<Icono nombre="check" />);
    expect(deco.container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
    expect(deco.container.querySelector("[role]")).toBeNull();
    expect(deco.container.querySelector("title")).toBeNull();
    deco.unmount();
    render(<Icono nombre="aviso" titulo="Requiere revisión" />);
    const img = screen.getByRole("img", { name: "Requiere revisión" });
    expect(img.querySelector("title")?.textContent).toBe("Requiere revisión");
    expect(img.hasAttribute("aria-hidden")).toBe(false);
  });

  test.each(["escalas", "ajustes", "subir", "check", "equis", "info", "aviso", "abajo", "derecha", "cargando", "mitad"] as const)("«%s» pinta un trazo y su clase", (nombre) => {
    const { container } = render(<Icono nombre={nombre} />);
    expect(container.querySelector(`svg.icono.icono-${nombre}`)).toBeTruthy();
    expect(container.querySelector("path, circle")).toBeTruthy();
  });
});
