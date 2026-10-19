import type { Marca } from "../tipos";

export const SIGNIFICADO: Record<Marca, string> = {
  A: "Sí cumple",
  L: "Cumple parcialmente",
  R: "No cumple",
  X: "No aplica",
  P: "Información obtenida de la normativa",
};

export function MarkBadge({ marca, grande = false }: { marca: Marca; grande?: boolean }) {
  return (
    <span className={`marca marca-${marca}${grande ? " grande" : ""}`} title={SIGNIFICADO[marca]} aria-label={SIGNIFICADO[marca]}>
      {marca}
    </span>
  );
}
