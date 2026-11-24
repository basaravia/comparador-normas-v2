import type { ReactNode } from "react";

/** Iconos propios en SVG (24×24, trazo redondeado, `currentColor`): sin biblioteca, sin descargas, sin licencia que atribuir.
 *  Sustituyen a los caracteres ⚖ ⚙ ⬆ ✓ ⚠ ▸ ▾ ◌ ◐ ✕, que se veían distinto en cada sistema. */
const TRAZOS = {
  escalas: <><path d="M12 4v16M8 20h8M4 7h16" /><path d="M4 7 1.8 13.5a2.2 2.2 0 0 0 4.4 0zM20 7l-2.2 6.5a2.2 2.2 0 0 0 4.4 0z" /></>,
  ajustes: <><path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1" /><circle cx="15" cy="6" r="2" /><circle cx="9" cy="12" r="2" /><circle cx="17" cy="18" r="2" /></>,
  subir: <path d="M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  equis: <path d="M6 6l12 12M18 6 6 18" />,
  aviso: <path d="M12 4 2.8 19.5h18.4zM12 10v4.5M12 17.3v.01" />,
  abajo: <path d="m6 9 6 6 6-6" />,
  derecha: <path d="m9 6 6 6-6 6" />,
  cargando: <path d="M12 4a8 8 0 1 0 8 8" />,
  mitad: <><circle cx="12" cy="12" r="8" /><path d="M12 4a8 8 0 0 0 0 16z" fill="currentColor" /></>,
} satisfies Record<string, ReactNode>;

export type NombreIcono = keyof typeof TRAZOS;

/** Decorativo por defecto (el texto de al lado lo nombra). Con `titulo` se anuncia y muestra su texto al pasar el puntero. */
export function Icono({ nombre, titulo, tam = "1.1em" }: { nombre: NombreIcono; titulo?: string; tam?: string }) {
  const a11y = titulo ? { role: "img", "aria-label": titulo } : { "aria-hidden": true, focusable: false };
  return (
    <svg className={`icono icono-${nombre}`} viewBox="0 0 24 24" width={tam} height={tam} fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" {...a11y}>
      {titulo && <title>{titulo}</title>}
      {TRAZOS[nombre]}
    </svg>
  );
}
