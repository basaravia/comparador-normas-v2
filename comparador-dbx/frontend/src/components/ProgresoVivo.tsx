import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { accionCancelar, duracion, ERROR_CANCELAR, estimarRango, textoConfirmacion } from "../progresoComparacion.ts";
import type { DocumentoOut, JobOut } from "../tipos";

/** Reloj del servidor: `ahora()` devuelve la hora del servidor interpolada con el reloj local entre sondeos (así no importa el desfase del equipo). */
export function useReloj(job: JobOut | null): () => number {
  const ref = useRef({ s: 0, l: 0 });
  if (job && job.ahora_ts && job.ahora_ts !== ref.current.s) ref.current = { s: job.ahora_ts, l: performance.now() };
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(t); }, []);
  return () => ref.current.s + (performance.now() - ref.current.l) / 1000;
}

export { duracion };

/** Tiempo transcurrido: el único reloj en pantalla. Al terminar se congela. */
export function transcurridoDe(job: JobOut, ahora: () => number): number {
  const fin = job.estado === "listo" || job.estado === "error" || job.estado === "cancelado";
  return (fin && job.ultimo_evento_ts > job.inicio_ts ? job.ultimo_evento_ts : ahora()) - job.inicio_ts;
}

/** Un solo tiempo («Tiempo transcurrido»); el estimado de procesamiento sale de las páginas leídas. */
function Tiempos({ job, hechos, total, ahora }: { job: JobOut; hechos: number; total: number; ahora: () => number }) {
  const transcurrido = transcurridoDe(job, ahora);
  const r = estimarRango(hechos, total, transcurrido);
  return (
    <p className="tiempos">
      Tiempo transcurrido: <strong>{duracion(transcurrido)}</strong>
      {r && <> · Falta aproximadamente: <strong>entre {duracion(r.desde)} y {duracion(r.hasta)}</strong></>}
    </p>
  );
}

/** Cancelar. `pares` > 0 pide confirmación en línea (comparación). «Cancelando…» se conserva al recargar (`job.cancelando`). */
export function Cancelar({ job, pares = 0, etiqueta = "Cancelar", nota }: { job: JobOut; pares?: number; etiqueta?: string; nota?: string }) {
  const [pedido, setPedido] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [fallo, setFallo] = useState(false);
  const cancelando = pedido || !!job.cancelando;
  if (!job.cancelable && !cancelando) return null;
  const enviar = async () => {
    setConfirmando(false); setFallo(false); setPedido(true);
    try { await api.cancelar(job.job_id); } catch { setPedido(false); setFallo(true); }
  };
  const pulsar = () => (accionCancelar(pares) === "confirmar" ? setConfirmando(true) : enviar());
  return (
    <div className="cancelar">
      {confirmando ? (
        <div className="confirmar-linea" role="group" aria-label="Confirmar cancelación">
          <span>{textoConfirmacion(pares)}</span>
          <button className="secundario" onClick={enviar}>Sí, cancelar</button>
          <button className="secundario" autoFocus onClick={() => setConfirmando(false)}>Seguir comparando</button>
        </div>
      ) : (
        <button className="secundario" disabled={cancelando} onClick={pulsar}>{cancelando ? "Cancelando…" : etiqueta}</button>
      )}
      {cancelando && nota && <small className="cancelando-nota">{nota}</small>}
      {fallo && <span className="nota-error" role="alert">{ERROR_CANCELAR}</span>}
    </div>
  );
}

const ETAPAS = ["Leyendo el texto", "Armando el índice", "Preparando la búsqueda"];

function etapaActual(job: JobOut): number {
  if (job.indexacion_total > 0 || job.etapa.startsWith("Preparando")) return 2;
  const docs = Object.values(job.por_documento);
  return docs.length > 0 && docs.every((p) => p.etapa !== "En cola" && p.etapa !== "Leyendo el texto") ? 1 : 0;
}

const MAX_PAG_CON_MINIATURA = 80;     // más páginas que esto: celdas lisas (cada miniatura se renderiza al pedirla)

/** Miniatura de una página; si el servidor no la puede dar, queda el número. */
function Miniatura({ docId, n }: { docId: string; n: number }) {
  const [falla, setFalla] = useState(false);
  return falla ? <i>{n}</i> : <img src={api.miniatura(docId, n)} alt="" loading="lazy" onError={() => setFalla(true)} />;
}

function Tira({ docId, p }: { docId: string; p: { paginas_hechas: number; paginas_total: number; lote: number[] } }) {
  const [ini, fin] = p.lote.length === 2 ? p.lote : [0, -1];
  const con = p.paginas_total <= MAX_PAG_CON_MINIATURA;
  return (
    <div className="tira" aria-hidden="true">
      {Array.from({ length: p.paginas_total }, (_, i) => i + 1).map((n) => {
        const leida = n <= p.paginas_hechas, leyendo = n >= ini && n <= fin;
        return (
          <span key={n} className={`pag ${leida ? "leida" : leyendo ? "leyendo" : "pendiente"}`} title={`Página ${n}`}>
            {leida && con ? <Miniatura docId={docId} n={n} /> : <i>{n}</i>}
          </span>
        );
      })}
    </div>
  );
}

export function ProgresoProcesamiento({ job, documentos, ahora }: { job: JobOut; documentos: DocumentoOut[]; ahora: () => number }) {
  const etapa = etapaActual(job);
  const prog = Object.values(job.por_documento);
  const hechas = prog.reduce((t, p) => t + p.paginas_hechas, 0), total = prog.reduce((t, p) => t + p.paginas_total, 0);
  return (
    <>
      <ol className="etapas" aria-label="Etapas">
        {ETAPAS.map((t, i) => <li key={t} className={i < etapa ? "hecha" : i === etapa ? "actual" : ""} aria-current={i === etapa ? "step" : undefined}>{t}</li>)}
      </ol>
      {documentos.filter((x) => job.por_documento[x.id]).map((x) => {
        const p = job.por_documento[x.id], ind = job.indice[x.id];
        return (
          <section key={x.id} className="doc-progreso">
            <h3>{x.nombre}</h3>
            <p className="doc-etapa">{p.etapa}{p.paginas_total > 0 && p.etapa !== "En cola" && <> · página {Math.min(p.paginas_hechas, p.paginas_total)} de {p.paginas_total}</>}</p>
            {p.paginas_total > 0 && p.etapa !== "En cola" && <Tira docId={x.id} p={p} />}
            {ind && (
              <p className="hallazgo">Encontramos {ind.secciones} secciones: <strong>{ind.articulos}</strong> para comparar
                {ind.excluidas > 0 && <>, {ind.excluidas} excluidas (carátula, índice, anexos…)</>}
                {ind.por_revisar > 0 && <>, {ind.por_revisar} para revisar</>}.</p>
            )}
          </section>
        );
      })}
      {job.indexacion_total > 0 && <p className="doc-etapa">Preparando la búsqueda: {job.indexacion_hechos} de {job.indexacion_total} lotes.</p>}
      <Tiempos job={job} hechos={hechas} total={total} ahora={ahora} />
      <div className="barra-acciones"><Cancelar job={job} nota="Se termina la lectura en curso; lo ya leído se conserva." /></div>
      <p className="nota-honesta">Cada recuadro es una página real del PDF; se ilumina cuando el lector termina esa tanda.</p>
    </>
  );
}
