import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { ProgresoComparacion, ProgresoProcesamiento, useReloj } from "../components/ProgresoVivo";
import { avisoParaMostrar } from "../recuerdo.ts";
import { traerSesion } from "../sincronizar.ts";
import { useStore } from "../store";
import type { JobOut } from "../tipos";

/** Progreso de un job (procesamiento de documentos o comparación). Sondea cada 1,5 s. */
export function Processing({ tipo }: { tipo: "procesamiento" | "comparacion" }) {
  const { e, d } = useStore();
  const job = e.job;
  const fin = useRef(false);

  const [fallos, setFallos] = useState(0);        // consultas seguidas que no llegaron al servidor
  const idSondeo = job?.job_id ?? e.reenganche?.id;

  useEffect(() => {
    fin.current = false;                        // job nuevo
    setFallos(0);
    if (!idSondeo) return;
    const id = idSondeo;
    const t = setInterval(async () => {
      try {
        let j: JobOut;
        try { j = await api.job(id); }
        catch (x) {
          // Al reengancharse a una comparación el servidor puede dar el id de la comparación: se espera a que termine.
          if (!job && tipo === "comparacion" && x instanceof ApiError && x.codigo === "ERR-JOB-404") {
            const c = await api.comparacion(id);
            setFallos(0);
            if (c.estado === "en_curso") return;
            clearInterval(t);
            if (c.estado === "listo") { d({ t: "comparacion", comparacion: c }); d({ t: "paso", paso: "resultados" }); }
            else { d({ t: "job", job: null }); d({ t: "paso", paso: "seleccion" }); }
            return;
          }
          throw x;
        }
        setFallos(0);
        d({ t: "job", job: j });
        if (j.estado === "error" || j.estado === "cancelado") clearInterval(t);
        if (j.estado === "cancelado" && tipo === "procesamiento") await traerSesion(d);
        if (j.estado === "listo" && !fin.current) {
          fin.current = true;
          if (tipo === "procesamiento") {
            const s = await traerSesion(d);
            d({ t: "entrarSeleccion", aviso: avisoParaMostrar(s.documentos, s.iniciada_ts) });
          } else if (j.comparacion_id) {
            d({ t: "comparacion", comparacion: await api.comparacion(j.comparacion_id) });
            d({ t: "paso", paso: "resultados" });
          }
        }
      } catch (x) {
        if (x instanceof ApiError && (x.sesionPerdida || x.status === 404)) { clearInterval(t); d({ t: "sesionPerdida", conProceso: true }); }
        else if (!(x instanceof ApiError) || x.status === 0) setFallos((n) => n + 1);
      }
    }, 1500);
    return () => clearInterval(t);
  }, [idSondeo, tipo, d]);   // eslint-disable-line react-hooks/exhaustive-deps

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

  const reenganchado = e.reenganche && (
    <p className="nota-info" role="status">Este proceso sigue en marcha desde antes. Puedes esperar aquí o volver más tarde.</p>
  );
  if (!job) {
    return <div className="pagina">{reenganchado}{e.reenganche ? <p className="ocupado">Conectando con el proceso…</p> : <p>No hay ningún proceso en curso.</p>}</div>;
  }
  const pct = Math.round(Math.min(Math.max(job.progreso, 0), 1) * 100);
  const error = job.estado === "error";

  return (
    <div className="pagina">
      {reenganchado}
      <h2>{tipo === "procesamiento" ? "Procesando los documentos" : "Comparando"}</h2>
      {fallos >= 3 && <div className="banner banner-aviso" role="status">No logramos consultar el avance. Seguimos intentando; el proceso continúa en el servidor.</div>}
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
