// Tabla de documentos: D-53 (25 nov 2026). El ejemplo no viene de un PDF, así que su estado dice solo «Indexado»; un PDF del auditor conserva «PDF no guardado».
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { DocTable } from "../../src/components/DocTable";
import type { DocumentoOut } from "../../src/tipos";

const meta = { entidad_emisora: null, titulo_oficial: null, libro: null, titulo: null, capitulo: null, numero_norma: null, fecha_vigencia: null };
const doc = (id: string, extra: Partial<DocumentoOut> = {}): DocumentoOut => ({ id, nombre: `${id}.pdf`, paginas: 3, tipo: "normativa", tipo_sugerido: false,
  metadatos: meta as DocumentoOut["metadatos"], estado: "listo", advertencias: [], error: null, ...extra });

const dibujar = (docs: DocumentoOut[]) => render(<DocTable docs={docs} editable onCambio={vi.fn()} onError={vi.fn()}
  acciones={{ max: 8, bloqueado: false, reintentos: new Set(), onReintentar: vi.fn(), onQuitar: vi.fn() }} />);

describe("DocTable y el estado del ejemplo", () => {
  test("un documento del ejemplo ya indexado dice solo «Indexado», sin «PDF no guardado»", () => {
    dibujar([doc("E1", { es_ejemplo: true })]);
    expect(screen.getByText("Indexado")).toBeTruthy();
    expect(screen.queryByText(/PDF no guardado/)).toBeNull();
  });

  test("un PDF del auditor indexado conserva «Indexado · PDF no guardado»", () => {
    dibujar([doc("D1")]);
    expect(screen.getByText("Indexado · PDF no guardado")).toBeTruthy();
  });

  test("el botón «?» que explica lo del PDF original aparece en un PDF y no en el ejemplo", () => {
    dibujar([doc("E1", { es_ejemplo: true })]);
    expect(screen.queryByRole("button", { name: "¿Qué significa Indexado?" })).toBeNull();
    cleanup();
    dibujar([doc("D1")]);
    const boton = screen.getByRole("button", { name: "¿Qué significa Indexado?" });
    fireEvent.click(boton);
    expect(screen.getByText(/no el archivo PDF original/)).toBeTruthy();
  });

  test("un servidor que aún no manda es_ejemplo (campo ausente) se trata como PDF normal", () => {
    dibujar([doc("D1", { es_ejemplo: undefined })]);
    expect(screen.getByText("Indexado · PDF no guardado")).toBeTruthy();
  });

  test("el ejemplo conviviendo con un PDF: cada fila muestra su propio estado", () => {
    dibujar([doc("E1", { es_ejemplo: true }), doc("D2")]);
    expect(screen.getAllByText("Indexado")).toHaveLength(1);
    expect(screen.getAllByText("Indexado · PDF no guardado")).toHaveLength(1);
  });

  test("el ejemplo en otro estado (error) no cambia: el texto especial solo aplica a «listo»", () => {
    dibujar([doc("E1", { es_ejemplo: true, estado: "error", error: { codigo: "ERR-X", mensaje: "No se pudo." } as DocumentoOut["error"] })]);
    expect(screen.getByText("Error")).toBeTruthy();
  });
});
