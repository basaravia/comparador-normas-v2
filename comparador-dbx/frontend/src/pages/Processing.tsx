import { useEffect, useRef } from "react";
import { api, ApiError } from "../api";
import { ProgresoComparacion, ProgresoProcesamiento, useReloj } from "../components/ProgresoVivo";
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
        if (j.estado === "error" || j.estado === "cancelado") clearInterval(t);
        if (j.estado === "cancelado" && tipo === "procesamiento") d({ t: "documentos", documentos: (await api.sesion()).documentos });
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

  const ahora = useReloj(job);

  // Aviso al terminar si la persona cambió de pestaña: queda en el título hasta que vuelve.
  useEffect(() => {
    const base = document.title;
    if (job && (job.estado === "listo" || job.estado === "error") && document.hidden) {
      document.title = `${job.estado === "listo" ? "✔ Listo" : "⚠ Revisa"} · ${base}`;
      const volver = () => { if (!document.hidden) { document.title = base; document.removeEventListener("visibilitychange", volver); } };
      document.addEventListener("visibilitychange", volver);
      return () => { document.title = base; document.removeEventListener("visibilitychange", volver); };
    }
  }, [job?.estado]);   // eslint-disable-line react-hooks/exhaustive-deps

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

      <div className="visually-hidden" role="status" aria-live="polite">{job.etapa}</div>
      {tipo === "procesamiento"
        ? <ProgresoProcesamiento job={job} documentos={e.documentos} ahora={ahora} />
        : <ProgresoComparacion job={job} ahora={ahora} />}

      {job.estado === "cancelado" && (
        <>
          <div className="banner banner-aviso">{job.etapa}</div>
          <button className="secundario" onClick={() => { fin.current = false; d({ t: "job", job: null }); d({ t: "paso", paso: tipo === "procesamiento" ? "carga" : "seleccion" }); }}>
            Volver
          </button>
        </>
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
