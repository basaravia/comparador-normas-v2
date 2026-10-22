import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { hojas } from "../arbol.ts";
import type { ArbolDocOut, NodoOut } from "../tipos";

const MAX_NODOS_ABIERTO = 150;   // hasta este tamaño el índice nace abierto hasta el artículo; si no, hasta el nivel 2

export { hojas };

/** Hojas que mueve un nodo al marcarlo: las no excluidas; si todas lo están, todas. */
function objetivo(n: NodoOut): NodoOut[] {
  const todas = hojas(n);
  const utiles = todas.filter((h) => !h.excluida);
  return utiles.length ? utiles : todas;
}

const esRama = (n: NodoOut) => !(n.hoja || n.hijos.length === 0);
const contar = (nodos: NodoOut[]): number => nodos.reduce((t, n) => t + 1 + contar(n.hijos), 0);
const ramas = (nodos: NodoOut[]): NodoOut[] => nodos.flatMap((n) => (esRama(n) ? [n, ...ramas(n.hijos)] : []));
const texto = (n: NodoOut) => `${n.identificador} ${n.titulo}`.toLowerCase();

/** Ramas cerradas al inicio: ninguna si el documento es pequeño; las de nivel ≥ 2 si es grande. */
function cerradasIniciales(nodos: NodoOut[]): Set<string> {
  if (contar(nodos) <= MAX_NODOS_ABIERTO) return new Set();
  const cerradas = new Set<string>();
  const ir = (ns: NodoOut[], nivel: number) => ns.forEach((n) => { if (esRama(n)) { if (nivel >= 2) cerradas.add(n.id); ir(n.hijos, nivel + 1); } });
  ir(nodos, 0);
  return cerradas;
}

interface Ctx {
  sel: Set<string>; onSel: (s: Set<string>) => void; onVer: (id: string) => void;
  cerradas: Set<string>; alternarRama: (id: string) => void; busqueda: string; soloMarcados: boolean;
}

/** ¿Debe verse el nodo con el filtro actual? Coincide él, un descendiente (y entonces se ve su camino) o, en "solo marcados", tiene marcas. */
function visible(n: NodoOut, c: Ctx): boolean {
  const q = c.busqueda.trim().toLowerCase();
  if (c.soloMarcados && !hojas(n).some((h) => c.sel.has(h.id))) return false;
  if (!q) return true;
  return texto(n).includes(q) || n.hijos.some((h) => visible(h, c));
}

function Nodo({ n, c, nivel }: { n: NodoOut; c: Ctx; nivel: number }) {
  const meta = objetivo(n);
  const marcadas = meta.filter((h) => c.sel.has(h.id)).length;
  const estado = marcadas === 0 ? "ninguna" : marcadas === meta.length ? "todas" : "algunas";
  const rama = esRama(n);
  const filtrando = c.busqueda.trim() !== "" || c.soloMarcados;
  const abierto = rama && (filtrando || !c.cerradas.has(n.id));       // al filtrar se ve el camino completo hasta lo encontrado
  const hijosVisibles = n.hijos.filter((h) => visible(h, c));
  if (!visible(n, c)) return null;

  const alternar = () => {
    const s = new Set(c.sel);
    if (estado === "todas") meta.forEach((h) => s.delete(h.id));
    else meta.forEach((h) => s.add(h.id));
    c.onSel(s);
  };
  const abrir = () => (rama ? c.alternarRama(n.id) : c.onVer(n.id));

  return (
    <li className={n.excluida ? "nodo excluida" : "nodo"} role="treeitem" aria-level={nivel + 1} aria-expanded={rama ? abierto : undefined}
        aria-checked={estado === "algunas" ? "mixed" : estado === "todas"}>
      <div className="nodo-fila" style={{ paddingLeft: nivel * 18 }} tabIndex={-1} data-fila data-id={n.id} data-rama={rama ? "1" : "0"} data-abierto={abierto ? "1" : "0"}>
        {rama
          ? <button className="plegar" tabIndex={-1} onClick={() => c.alternarRama(n.id)} aria-label={abierto ? "Contraer" : "Expandir"}>{abierto ? "▾" : "▸"}</button>
          : <span className="plegar vacio" />}
        <input type="checkbox" tabIndex={-1} checked={estado === "todas"} disabled={meta.length === 0} aria-label={`Marcar ${n.identificador}`}
          ref={(el) => { if (el) el.indeterminate = estado === "algunas"; }} onChange={alternar} />
        <div className="nodo-texto" onClick={abrir}>
          <span className="nodo-id">{n.identificador}</span>
          {n.titulo && <span className="nodo-titulo"> {n.titulo}</span>}
          {n.incierto && <span className="incierto" title="Esta sección se detectó por longitud; revísala"> ⚠</span>}
          {!rama && n.preview && <div className="nodo-preview">{n.preview}</div>}
          {meta.length === 0 && <div className="nodo-motivo">No se detectaron artículos en este título</div>}
          {n.excluida && n.motivo && <div className="nodo-motivo">No se comparará: {n.motivo}</div>}
        </div>
        <span className="nodo-meta">
          {rama && <span className="nodo-cuenta" title="Marcados / total">{marcadas}/{meta.length}</span>}
          <span className="nodo-pag">pág. {n.pagina_inicio}</span>
        </span>
      </div>
      {rama && abierto && <ul role="group">{hijosVisibles.map((h) => <Nodo key={h.id} n={h} c={c} nivel={nivel + 1} />)}</ul>}
    </li>
  );
}

function ArbolDoc({ a, sel, onSel, onVer }: { a: ArbolDocOut; sel: Set<string>; onSel: (s: Set<string>) => void; onVer: (id: string) => void }) {
  const [cerradas, setCerradas] = useState<Set<string>>(() => cerradasIniciales(a.nodos));
  const [busqueda, setBusqueda] = useState("");
  const [soloMarcados, setSoloMarcados] = useState(false);
  const raiz = useRef<HTMLUListElement>(null);
  const todasLasHojas = useMemo(() => a.nodos.flatMap(hojas), [a.nodos]);
  const total = todasLasHojas.filter((h) => !h.excluida).length;
  const marcados = todasLasHojas.filter((h) => sel.has(h.id)).length;

  const alternarRama = (id: string) => setCerradas((p) => { const s = new Set(p); if (s.has(id)) s.delete(id); else s.add(id); return s; });
  const ctx: Ctx = { sel, onSel, onVer, cerradas, alternarRama, busqueda, soloMarcados };

  // Teclado (patrón ARIA tree): ↑↓ se mueven por las filas visibles, → abre, ← cierra, Espacio marca, * abre todo.
  const teclas = (ev: KeyboardEvent<HTMLUListElement>) => {
    const filas = Array.from(raiz.current?.querySelectorAll<HTMLElement>("[data-fila]") ?? []);
    const i = filas.findIndex((f) => f === document.activeElement);
    const fila = i >= 0 ? filas[i] : null;
    const ir = (j: number) => { ev.preventDefault(); filas[Math.max(0, Math.min(filas.length - 1, j))]?.focus(); };
    if (ev.key === "ArrowDown") return ir(i + 1);
    if (ev.key === "ArrowUp") return ir(i - 1);
    if (ev.key === "Home") return ir(0);
    if (ev.key === "End") return ir(filas.length - 1);
    if (!fila) return;
    const id = fila.dataset.id!, rama = fila.dataset.rama === "1", abierta = fila.dataset.abierto === "1";
    if (ev.key === "ArrowRight" && rama && !abierta) { ev.preventDefault(); alternarRama(id); }
    else if (ev.key === "ArrowLeft" && rama && abierta) { ev.preventDefault(); alternarRama(id); }
    else if (ev.key === " ") { ev.preventDefault(); fila.querySelector<HTMLInputElement>("input")?.click(); }
    else if (ev.key === "Enter" && !rama) { ev.preventDefault(); onVer(id); }
    else if (ev.key === "*") { ev.preventDefault(); setCerradas(new Set()); }
  };

  return (
    <div className="arbol-doc">
      <h3>{a.nombre}</h3>
      {a.avisos.map((av, i) => <div key={i} className="nota-aviso">ℹ {av}</div>)}
      <div className="arbol-barra" role="toolbar" aria-label={`Herramientas del índice de ${a.nombre}`}>
        <input type="search" placeholder="Buscar en el índice…" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} aria-label="Buscar en el índice" />
        <button className="enlace" onClick={() => setCerradas(new Set())}>Expandir todo</button>
        <button className="enlace" onClick={() => setCerradas(new Set(ramas(a.nodos).map((n) => n.id)))}>Contraer todo</button>
        <label className="solo-marcados"><input type="checkbox" checked={soloMarcados} onChange={(e) => setSoloMarcados(e.target.checked)} /> Solo marcados</label>
        <span className="arbol-total" aria-live="polite">{marcados} de {total} marcados</span>
      </div>
      <ul className="arbol" role="tree" aria-label={`Índice de ${a.nombre}`} ref={raiz} onKeyDown={teclas}>
        {a.nodos.map((n) => <Nodo key={n.id} n={n} c={ctx} nivel={0} />)}
      </ul>
    </div>
  );
}

export function DualTree({ titulo, vacio, arboles, sel, onSel, onVer }: {
  titulo: string; vacio: string; arboles: ArbolDocOut[]; sel: Set<string>; onSel: (s: Set<string>) => void; onVer: (id: string) => void;
}) {
  return (
    <section className="panel">
      <h2>{titulo}</h2>
      {arboles.length === 0 && <p className="vacio-texto">{vacio}</p>}
      {arboles.map((a) => <ArbolDoc key={a.doc_id} a={a} sel={sel} onSel={onSel} onVer={onVer} />)}
    </section>
  );
}
