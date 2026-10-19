import { useEffect, useRef } from "react";
import { api, ApiError } from "../api";
import { ESTADOS } from "../components/DocTable";
import { useStore } from "../store";

/** Progreso de un job (procesamiento de documentos o comparación). Sondea cada 1,5 s. */
export function Processing({ tipo }: { tipo: "procesamiento" | "comparacion" }) {
  const { e, d } = useStore();
  const job = e.job;
  const fin = useRef(false);

  useEffect(() => {
    fin.current = false;                        // job nuevo
    if (!job) return;
    const id = job.job_id;
    const t = setInterval(async () => {
      try {
        const j = await api.job(id);
        d({ t: "job", job: j });
        if (j.estado === "error") clearInterval(t);
        if (j.estado === "listo" && !fin.current) {
          fin.current = true;
          if (tipo === "procesamiento") {
            const s = await api.sesion();
            d({ t: "documentos", documentos: s.documentos });
            d({ t: "paso", paso: "seleccion" });
          } else if (j.comparacion_id) {
            d({ t: "comparacion", comparacion: await api.comparacion(j.comparacion_id) });
            d({ t: "paso", paso: "resultados" });
          }
        }
      } catch (x) {
        if (x instanceof ApiError && x.sesionPerdida) { d({ t: "sesionPerdida" }); }
      }
    }, 1500);
    return () => clearInterval(t);
  }, [job?.job_id, tipo, d]);

  if (!job) return <div className="pagina"><p>No hay ningún proceso en curso.</p></div>;
  const pct = Math.round(Math.min(Math.max(job.progreso, 0), 1) * 100);
  const error = job.estado === "error";

  return (
    <div className="pagina">
      <h2>{tipo === "procesamiento" ? "Procesando los documentos" : "Comparando"}</h2>
      <div className="progreso" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`progreso-barra${error ? " error" : ""}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="progreso-texto"><strong>{pct} %</strong> · {job.etapa || "En cola"}
        {job.doc_actual && <> · {job.doc_actual}</>}</p>
      {job.mensaje && <p className="progreso-mensaje">{job.mensaje}</p>}

      {tipo === "procesamiento" && (
        <table className="tabla docs">
          <thead><tr><th>Documento</th><th>Estado</th></tr></thead>
          <tbody>
            {e.documentos.filter((x) => job.documentos[x.id]).map((x) => (
              <tr key={x.id}><td className="nombre">{x.nombre}</td>
                <td><span className={`estado estado-${job.documentos[x.id]}`}>{ESTADOS[job.documentos[x.id]] ?? job.documentos[x.id]}</span></td></tr>
            ))}
          </tbody>
        </table>
      )}

      {error && (
        <>
          {job.errores.map((x, i) => <div key={i} className="banner banner-error">{x.mensaje} <small>({x.codigo})</small></div>)}
          {job.errores.length === 0 && <div className="banner banner-error">No pudimos completar el proceso. Intenta de nuevo.</div>}
          <button className="secundario" onClick={() => { fin.current = false; d({ t: "job", job: null }); d({ t: "paso", paso: tipo === "procesamiento" ? "carga" : "seleccion" }); }}>
            Volver
          </button>
        </>
      )}
    </div>
  );
}
