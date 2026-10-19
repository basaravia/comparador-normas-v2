import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { MarkBadge, SIGNIFICADO } from "../components/MarkBadge";
import { useStore } from "../store";
import type { FilaVia1, FilaVia2, Marca } from "../tipos";

const MARCAS: Marca[] = ["A", "L", "R", "X", "P"];
const COBERTURA = { total: "Cubre del todo", parcial: "Cubre en parte", nula: "No cubre" } as const;

function DetalleVia1({ f }: { f: FilaVia1 }) {
  return (
    <div className="detalle">
      {f.requiere_revision && <div className="nota-aviso">⚠ Este resultado quedó marcado para revisión: valídalo antes de usarlo.</div>}
      <h4>Texto de la norma</h4>
      <blockquote>{f.texto_articulo}</blockquote>
      {f.cita_norma && <><h4>Fragmento clave de la norma</h4><blockquote className="cita">{f.cita_norma}</blockquote></>}
      <h4>Respaldo en el manual {f.seccion_respaldo && <small>· {f.seccion_respaldo}</small>}</h4>
      {f.cita_manual ? <blockquote className="cita">{f.cita_manual}</blockquote> : <p className="vacio-texto">No encontramos un fragmento del manual que respalde este artículo.</p>}
      {f.comentario && <><h4>Comentario</h4><p>{f.comentario}</p></>}
      {f.elementos_faltantes.length > 0 && (
        <><h4>Elementos que faltan</h4><ul>{f.elementos_faltantes.map((x, i) => <li key={i}>{x}</li>)}</ul></>
      )}
      {f.confianza !== null && <p className="confianza">Confianza del análisis: {Math.round(f.confianza * 100)} %</p>}
    </div>
  );
}

function Via1({ filas, filtro }: { filas: FilaVia1[]; filtro: Marca | "todas" }) {
  const [abierta, setAbierta] = useState<string | null>(null);
  const visibles = filas.filter((f) => filtro === "todas" || f.marca === filtro);
  if (visibles.length === 0) return <p className="vacio-texto">No hay artículos con esta marca.</p>;
  return (
    <table className="tabla resultados">
      <thead><tr><th>Artículo</th><th>Marca</th><th>Respaldo en el manual</th><th>Comentario</th><th></th></tr></thead>
      <tbody>
        {visibles.map((f) => (
          <FilaExpandible key={f.articulo_id} abierta={abierta === f.articulo_id} onAlternar={() => setAbierta(abierta === f.articulo_id ? null : f.articulo_id)}
            celdas={[
              <><strong>{f.identificador}</strong><br /><small>{f.documento}</small></>,
              <><MarkBadge marca={f.marca} />{f.requiere_revision && <span className="revision" title="Requiere revisión"> ⚠</span>}</>,
              f.seccion_respaldo || <span className="vacio-texto">—</span>,
              <span className="comentario">{f.comentario || "—"}</span>,
            ]} detalle={<DetalleVia1 f={f} />} />
        ))}
      </tbody>
    </table>
  );
}

function FilaExpandible({ celdas, detalle, abierta, onAlternar }: {
  celdas: React.ReactNode[]; detalle: React.ReactNode; abierta: boolean; onAlternar: () => void;
}) {
  return (
    <>
      <tr className={abierta ? "abierta" : ""} onClick={onAlternar}>
        {celdas.map((c, i) => <td key={i}>{c}</td>)}
        <td><button className="enlace" aria-expanded={abierta}>{abierta ? "Ocultar" : "Ver detalle"}</button></td>
      </tr>
      {abierta && <tr className="fila-detalle"><td colSpan={celdas.length + 1}>{detalle}</td></tr>}
    </>
  );
}

function Via2({ filas, soloSinBase }: { filas: FilaVia2[]; soloSinBase: boolean }) {
  const visibles = filas.filter((f) => !soloSinBase || f.sin_base);
  if (visibles.length === 0) return <p className="vacio-texto">No hay controles para mostrar.</p>;
  return (
    <table className="tabla resultados">
      <thead><tr><th>Control del manual</th><th>Estado</th><th>Artículos relacionados</th></tr></thead>
      <tbody>
        {visibles.map((f) => (
          <tr key={f.seccion_id}>
            <td><strong>{f.identificador}</strong>{f.titulo && <><br /><small>{f.titulo}</small></>}</td>
            <td>{f.sin_base ? <span className="estado estado-sinbase">Control sin base normativa</span> : <span className="estado estado-listo">Con respaldo normativo</span>}</td>
            <td>{f.pares.length === 0 ? <span className="vacio-texto">—</span> : f.pares.map((p) => (
              <span key={p.articulo_id} className={`par par-${p.cobertura}`} title={COBERTURA[p.cobertura]}>{p.identificador}</span>
            ))}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Results() {
  const { e, d } = useStore();
  const c = e.comparacion;
  const [vista, setVista] = useState<"via1" | "via2">("via1");
  const [filtro, setFiltro] = useState<Marca | "todas">("todas");
  const [soloSinBase, setSoloSinBase] = useState(false);
  const [texto, setTexto] = useState(c?.conclusion ?? "");
  const [msg, setMsg] = useState("");

  useEffect(() => { setTexto(c?.conclusion ?? ""); }, [c?.id, c?.conclusion]);

  if (!c) return <div className="pagina"><p>Aún no hay resultados. Elige las secciones y pulsa Comparar.</p></div>;

  const guardar = async () => {
    setMsg("");
    try { d({ t: "comparacion", comparacion: await api.guardarConclusion(c.id, texto) }); setMsg("Conclusión guardada."); }
    catch (x) {
      if (x instanceof ApiError && x.sesionPerdida) d({ t: "sesionPerdida" });
      else setMsg(x instanceof ApiError ? x.message : "No pudimos guardar la conclusión.");
    }
  };

  return (
    <div className="pagina ancha">
      <section className="resumen">
        {MARCAS.map((m) => (
          <button key={m} className={`resumen-marca${filtro === m && vista === "via1" ? " activa" : ""}`}
            onClick={() => { setVista("via1"); setFiltro(filtro === m ? "todas" : m); }} title={SIGNIFICADO[m]}>
            <MarkBadge marca={m} grande /><span className="n">{c.conteos[m] ?? 0}</span><span className="et">{SIGNIFICADO[m]}</span>
          </button>
        ))}
        <div className="resumen-extra">
          <div><strong>{c.pares_juzgados}</strong> pares analizados</div>
          <div className={c.pares_a_revision ? "revision" : ""}><strong>{c.pares_a_revision}</strong> a revisión</div>
          <div><strong>{c.via2.filter((f) => f.sin_base).length}</strong> controles sin base normativa</div>
        </div>
      </section>
      {c.avisos.map((a, i) => <div key={i} className="nota-aviso">ℹ {a}</div>)}

      <div className="conmutador" role="tablist">
        <button role="tab" aria-selected={vista === "via1"} className={vista === "via1" ? "activa" : ""} onClick={() => setVista("via1")}>Ver por artículo (vía 1)</button>
        <button role="tab" aria-selected={vista === "via2"} className={vista === "via2" ? "activa" : ""} onClick={() => setVista("via2")}>Ver por control del manual (vía 2)</button>
      </div>

      {vista === "via1" ? (
        <>
          <div className="filtros">
            <button className={filtro === "todas" ? "activa" : ""} onClick={() => setFiltro("todas")}>Todas ({c.via1.length})</button>
            {MARCAS.map((m) => <button key={m} className={filtro === m ? "activa" : ""} onClick={() => setFiltro(m)}>{m} ({c.conteos[m] ?? 0})</button>)}
          </div>
          <Via1 filas={c.via1} filtro={filtro} />
        </>
      ) : (
        <>
          <div className="filtros">
            <button className={!soloSinBase ? "activa" : ""} onClick={() => setSoloSinBase(false)}>Todos ({c.via2.length})</button>
            <button className={soloSinBase ? "activa" : ""} onClick={() => setSoloSinBase(true)}>Sin base normativa ({c.via2.filter((f) => f.sin_base).length})</button>
          </div>
          <Via2 filas={c.via2} soloSinBase={soloSinBase} />
        </>
      )}

      <section className="conclusion">
        <h2>Conclusión</h2>
        <p className="ayuda">Propuesta generada automáticamente — revísala antes de firmar.</p>
        <textarea value={texto} rows={8} onChange={(ev) => { setTexto(ev.target.value); setMsg(""); }} placeholder="Escribe aquí la conclusión del papel de trabajo." />
        <div className="barra-acciones">
          <button className="secundario" onClick={guardar} disabled={texto === c.conclusion}>Guardar conclusión</button>
          {msg && <span className="ayuda">{msg}</span>}
          <a className="primario boton" href={api.urlExcel(c.id)} download>Descargar papel de trabajo (.xlsx)</a>
        </div>
      </section>
    </div>
  );
}
