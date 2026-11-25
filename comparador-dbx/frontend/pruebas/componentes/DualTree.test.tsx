// Índice de secciones (DualTree): marcar, plegar, filtrar y moverse con el teclado, como lo hace el auditor.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { DualTree } from "../../src/components/DualTree";
import type { ArbolDocOut, NodoOut } from "../../src/tipos";

const hoja = (id: string, identificador: string): NodoOut => ({ id, identificador, titulo: "", preview: `Texto de ${identificador}`, hoja: true, incierto: false, excluida: false,
  motivo: "", seleccionada: false, pagina_inicio: 1, hijos: [] });

const arbol = (): ArbolDocOut => ({
  doc_id: "D1", nombre: "Norma de prueba", avisos: [],
  nodos: [{ id: "T1", identificador: "Título I", titulo: "Generalidades", preview: "", hoja: false, incierto: false, excluida: false, motivo: "", seleccionada: false,
    pagina_inicio: 1, hijos: [hoja("A1", "Artículo 1"), hoja("A2", "Artículo 2")] }],
});

const dibujar = (sel: string[] = [], extra: { onQuitarMarcas?: (a: ArbolDocOut) => void } = {}) => {
  const onSel = vi.fn(), onVer = vi.fn();
  render(<DualTree titulo="Normativa" vacio="Nada" arboles={[arbol()]} sel={new Set(sel)} onSel={onSel} onVer={onVer} {...extra} />);
  return { onSel, onVer };
};

describe("DualTree", () => {
  test("sin documentos muestra el texto de vacío", () => {
    render(<DualTree titulo="Normativa" vacio="Aún no hay documentos" arboles={[]} sel={new Set()} onSel={() => {}} onVer={() => {}} />);
    expect(screen.getByText("Aún no hay documentos")).toBeTruthy();
  });

  test("marcar un artículo marca solo ese; marcar el título marca todos sus artículos", () => {
    const { onSel } = dibujar();
    fireEvent.click(screen.getByRole("checkbox", { name: "Marcar Artículo 1" }));
    expect([...onSel.mock.calls[0][0]]).toEqual(["A1"]);
    fireEvent.click(screen.getByRole("checkbox", { name: "Marcar Título I" }));
    expect([...onSel.mock.calls[1][0]].sort()).toEqual(["A1", "A2"]);
  });

  test("si el título ya está completo, marcarlo de nuevo quita sus artículos", () => {
    const { onSel } = dibujar(["A1", "A2"]);
    fireEvent.click(screen.getByRole("checkbox", { name: "Marcar Título I" }));
    expect([...onSel.mock.calls[0][0]]).toEqual([]);
  });

  test("el contador dice cuántos van marcados", () => {
    dibujar(["A1"]);
    expect(screen.getByText("1 de 2 marcados")).toBeTruthy();
  });

  test("un solo botón: «Contraer todo» oculta los artículos y pasa a «Expandir todo»; otro clic los muestra", () => {
    dibujar();
    expect(screen.getByText("Artículo 1")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Contraer todo" }));
    expect(screen.queryByText("Artículo 1")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Expandir todo" }));
    expect(screen.getByText("Artículo 1")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Contraer todo" })).toBeTruthy();
  });

  test("la búsqueda deja solo lo que coincide (con su camino) y al borrarla vuelve todo", () => {
    dibujar();
    const caja = screen.getByRole("searchbox", { name: "Buscar en el índice" });
    fireEvent.change(caja, { target: { value: "Artículo 2" } });
    expect(screen.getByText("Artículo 2")).toBeTruthy();
    expect(screen.queryByText("Artículo 1")).toBeNull();
    expect(screen.getByText("Título I")).toBeTruthy();
    fireEvent.change(caja, { target: { value: "" } });
    expect(screen.getByText("Artículo 1")).toBeTruthy();
  });

  test("«Solo marcados» muestra únicamente lo marcado", () => {
    dibujar(["A1"]);
    fireEvent.click(screen.getByRole("checkbox", { name: /Solo marcados/ }));
    expect(screen.getByText("Artículo 1")).toBeTruthy();
    expect(screen.queryByText("Artículo 2")).toBeNull();
  });

  test("hacer clic en el texto de un artículo lo abre para leerlo", () => {
    const { onVer } = dibujar();
    fireEvent.click(screen.getByText("Texto de Artículo 1"));
    expect(onVer).toHaveBeenCalledWith("A1");
  });

  test("teclado: las flechas mueven el foco entre filas y Espacio marca la fila", () => {
    const { onSel } = dibujar();
    const filas = () => Array.from(document.querySelectorAll<HTMLElement>("[data-fila]"));
    filas()[0].focus();
    fireEvent.keyDown(screen.getByRole("tree"), { key: "ArrowDown" });
    expect(document.activeElement).toBe(filas()[1]);
    fireEvent.keyDown(screen.getByRole("tree"), { key: " " });
    expect([...onSel.mock.calls[0][0]]).toEqual(["A1"]);
    fireEvent.keyDown(screen.getByRole("tree"), { key: "ArrowUp" });
    expect(document.activeElement).toBe(filas()[0]);
  });

  test("«Quitar marcas de este manual» solo aparece si se pidió y hay marcas", () => {
    const quitar = vi.fn();
    dibujar(["A1"], { onQuitarMarcas: quitar });
    fireEvent.click(screen.getByRole("button", { name: "Quitar marcas de este manual" }));
    expect(quitar).toHaveBeenCalledTimes(1);
    expect(quitar.mock.calls[0][0].doc_id).toBe("D1");
  });

  test("sin marcas no ofrece quitar marcas", () => {
    dibujar([], { onQuitarMarcas: () => {} });
    expect(screen.queryByRole("button", { name: "Quitar marcas de este manual" })).toBeNull();
  });
});
