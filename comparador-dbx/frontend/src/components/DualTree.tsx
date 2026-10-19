import { useState } from "react";
import type { ArbolDocOut, NodoOut } from "../tipos";

export function hojas(n: NodoOut): NodoOut[] {
  return n.hoja || n.hijos.length === 0 ? [n] : n.hijos.flatMap(hojas);
}

/** Hojas que mueve un nodo al marcarlo: las no excluidas; si todas lo están, todas. */
function objetivo(n: NodoOut): NodoOut[] {
  const todas = hojas(n);
  const utiles = todas.filter((h) => !h.excluida);
  return utiles.length ? utiles : todas;
}

function Nodo({ n, sel, onSel, onVer, nivel }: {
  n: NodoOut; sel: Set<string>; onSel: (s: Set<string>) => void; onVer: (id: string) => void; nivel: number;
}) {
  const [abierto, setAbierto] = useState(nivel < 1);
  const meta = objetivo(n);
  const marcadas = meta.filter((h) => sel.has(h.id)).length;
  const estado = marcadas === 0 ? "ninguna" : marcadas === meta.length ? "todas" : "algunas";
  const esHoja = n.hoja || n.hijos.length === 0;

  const alternar = () => {
    const s = new Set(sel);
    if (estado === "todas") meta.forEach((h) => s.delete(h.id));
    else meta.forEach((h) => s.add(h.id));
    onSel(s);
  };

  return (
    <li className={n.excluida ? "nodo excluida" : "nodo"}>
      <div className="nodo-fila" style={{ paddingLeft: nivel * 16 }}>
        {!esHoja
          ? <button className="plegar" onClick={() => setAbierto(!abierto)} aria-label={abierto ? "Contraer" : "Expandir"}>{abierto ? "▾" : "▸"}</button>
          : <span className="plegar vacio" />}
        <input type="checkbox" checked={estado === "todas"} aria-checked={estado === "algunas" ? "mixed" : estado === "todas"}
          ref={(el) => { if (el) el.indeterminate = estado === "algunas"; }} onChange={alternar} />
        <div className="nodo-texto" onClick={() => (esHoja ? onVer(n.id) : setAbierto(!abierto))}>
          <span className="nodo-id">{n.identificador}</span>
          {n.titulo && <span className="nodo-titulo"> {n.titulo}</span>}
          {n.incierto && <span className="incierto" title="Esta sección se detectó por longitud; revísala"> ⚠</span>}
          {esHoja && n.preview && <div className="nodo-preview">{n.preview}</div>}
          {n.excluida && n.motivo && <div className="nodo-motivo">No se comparará: {n.motivo}</div>}
        </div>
      </div>
      {!esHoja && abierto && (
        <ul>{n.hijos.map((h) => <Nodo key={h.id} n={h} sel={sel} onSel={onSel} onVer={onVer} nivel={nivel + 1} />)}</ul>
      )}
    </li>
  );
}

export function DualTree({ titulo, vacio, arboles, sel, onSel, onVer }: {
  titulo: string; vacio: string; arboles: ArbolDocOut[]; sel: Set<string>; onSel: (s: Set<string>) => void; onVer: (id: string) => void;
}) {
  return (
    <section className="panel">
      <h2>{titulo}</h2>
      {arboles.length === 0 && <p className="vacio-texto">{vacio}</p>}
      {arboles.map((a) => (
        <div key={a.doc_id} className="arbol-doc">
          <h3>{a.nombre}</h3>
          {a.avisos.map((av, i) => <div key={i} className="nota-aviso">ℹ {av}</div>)}
          <ul className="arbol">{a.nodos.map((n) => <Nodo key={n.id} n={n} sel={sel} onSel={onSel} onVer={onVer} nivel={0} />)}</ul>
        </div>
      ))}
    </section>
  );
}
