import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { DocumentoOut, JobOut, VeredictoVivo } from "../tipos";

/** Reloj del servidor: `ahora()` devuelve la hora del servidor interpolada con el reloj local entre sondeos (así no importa el desfase del equipo). */
export function useReloj(job: JobOut | null): () => number {
  const ref = useRef({ s: 0, l: 0 });
  if (job && job.ahora_ts && job.ahora_ts !== ref.current.s) ref.current = { s: job.ahora_ts, l: performance.now() };
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(t); }, []);
  return () => ref.current.s + (performance.now() - ref.current.l) / 1000;
}

export function duracion(seg: number): string {
  const s = Math.max(0, Math.round(seg));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m} min ${s % 60} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

/** Tiempo restante con rango (±35 %), solo después de la primera medición real. */
function estimado(hechos: number, total: number, transcurrido: number): string | null {
  if (hechos <= 0 || total <= hechos || transcurrido < 3) return null;
  const resto = ((total - hechos) * transcurrido) / hechos;
  return `entre ${duracion(resto * 0.65)} y ${duracion(resto * 1.35)}`;
}

function Tiempos({ job, hechos, total, ahora }: { job: JobOut; hechos: number; total: number; ahora: () => number }) {
  const transcurrido = ahora() - job.inicio_ts;
  const sinNovedad = ahora() - job.ultimo_evento_ts;
  const est = estimado(hechos, total, transcurrido);
  return (
    <p className="tiempos">
      Transcurrido: <strong>{duracion(transcurrido)}</strong>
      {est && <> · Falta aproximadamente: <strong>{est}</strong></>}
      <> · Última novedad hace {duracion(sinNovedad)}</>
      {sinNovedad > 40 && job.estado === "en_curso" && <span className="lento"> · Sigue trabajando: una tanda de páginas puede tardar varios minutos.</span>}
    </p>
  );
}

function Cancelar({ job }: { job: JobOut }) {
  const [pedido, setPedido] = useState(false);
  if (!job.cancelable && !pedido) return null;
  return (
    <button className="secundario" disabled={pedido} onClick={async () => { setPedido(true); try { await api.cancelar(job.job_id); } catch { setPedido(false); } }}>
      {pedido ? "Cancelando…" : "Cancelar"}
    </button>
  );
}

const ETAPAS = ["Leyendo el texto", "Armando el índice", "Preparando la búsqueda"];

function etapaActual(job: JobOut): number {
  if (job.indexacion_total > 0 || job.etapa.startsWith("Preparando")) return 2;
  const docs = Object.values(job.por_documento);
  return docs.length > 0 && docs.every((p) => p.etapa !== "En cola" && p.etapa !== "Leyendo el texto") ? 1 : 0;
}

const MAX_PAG_CON_MINIATURA = 80;     // más páginas que esto: celdas lisas (cada miniatura se renderiza al pedirla)

function Tira({ docId, p }: { docId: string; p: { paginas_hechas: number; paginas_total: number; lote: number[] } }) {
  const [ini, fin] = p.lote.length === 2 ? p.lote : [0, -1];
  const con = p.paginas_total <= MAX_PAG_CON_MINIATURA;
  return (
    <div className="tira" aria-hidden="true">
      {Array.from({ length: p.paginas_total }, (_, i) => i + 1).map((n) => {
        const leida = n <= p.paginas_hechas, leyendo = n >= ini && n <= fin;
        return (
          <span key={n} className={`pag ${leida ? "leida" : leyendo ? "leyendo" : "pendiente"}`} title={`Página ${n}`}>
            {leida && con ? <img src={api.miniatura(docId, n)} alt="" loading="lazy" /> : <i>{n}</i>}
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
      <div className="barra-acciones"><Cancelar job={job} /></div>
      <p className="nota-honesta">Cada recuadro es una página real del PDF; se ilumina cuando el lector termina esa tanda.</p>
    </>
  );
}

const COBERTURA: Record<VeredictoVivo["cobertura"], { icono: string; texto: string }> = {
  total: { icono: "●", texto: "Cobertura total" }, parcial: { icono: "◐", texto: "Cobertura parcial" },
  nula: { icono: "○", texto: "Sin cobertura" }, sin_veredicto: { icono: "?", texto: "Sin veredicto (a revisión)" },
};

function Veredicto({ v }: { v: VeredictoVivo }) {
  const [abierto, setAbierto] = useState(false);
  const c = COBERTURA[v.cobertura];
  const citas = v.cita_norma_ok && v.cita_manual_ok;
  return (
    <li className="veredicto">
      <span className={`cob cob-${v.cobertura}`}><span aria-hidden="true">{c.icono}</span> {c.texto}</span>
      <span> · {v.articulo} ↔ {v.seccion}</span>
      <span> · confianza {Math.round(v.confianza * 100)} %</span>
      <span className={citas ? "ok" : "revisar"}> · {citas ? "✓ citas verificadas" : "⚠ citas por revisar"}</span>
      {v.comentario && <button className="enlace" onClick={() => setAbierto(!abierto)}>{abierto ? "Ocultar comentario" : "Ver comentario del modelo"}</button>}
      {abierto && <p className="comentario-modelo">{v.comentario}</p>}
    </li>
  );
}

const FASES: Record<string, string> = { recuperando: "Buscando coincidencias", juzgando: "Evaluando cada par", armando: "Armando el papel de trabajo" };

export function ProgresoComparacion({ job, ahora }: { job: JobOut; ahora: () => number }) {
  const espera = job.espera_limite;
  const faltan = espera.activa ? Math.max(0, Math.ceil(espera.hasta_ts - ahora())) : 0;
  const cc = job.conteo_cobertura;
  return (
    <>
      <p className="doc-etapa"><strong>{FASES[job.fase] ?? job.etapa}</strong>{job.pares_total > 0 && <> · par {job.pares_hechos} de {job.pares_total}</>}</p>
      {espera.activa && (
        <div className="banner banner-aviso" role="status">
          Esperando al servicio de IA (límite de uso del proveedor). Se reanuda en {faltan} s · intento {espera.intento} de {espera.max}.
        </div>
      )}
      <Tiempos job={job} hechos={job.pares_hechos} total={job.pares_total} ahora={ahora} />

      {job.pares_en_curso.length > 0 && (
        <section className="actividad">
          <h3>Ahora se analizan</h3>
          {job.pares_en_curso.map((p) => (
            <div key={p.par_id} className="par-en-curso">
              <div className="frag"><small>Norma · {p.articulo.documento} · {p.articulo.identificador} · pág. {p.articulo.pagina}</small><p>{p.articulo.preview}…</p></div>
              <div className="frag"><small>Manual · {p.seccion.documento} · {p.seccion.identificador} · pág. {p.seccion.pagina}</small><p>{p.seccion.preview}…</p></div>
              <small className="par-meta">Similitud {p.score.toFixed(2)} · encontrado por {p.origen.map((o) => (o === "v1" ? "la norma" : "el manual")).join(" y ")}</small>
            </div>
          ))}
        </section>
      )}

      {job.ultimos_veredictos.length > 0 && (
        <section className="actividad">
          <h3>Últimos veredictos</h3>
          <ul className="veredictos">{[...job.ultimos_veredictos].reverse().slice(0, 8).map((v) => <Veredicto key={v.seq} v={v} />)}</ul>
          <p className="conteos" title="Conteo provisional por par; las marcas A/L/R/X/P se calculan al final">
            Hasta ahora (por par, provisional): {cc.total ?? 0} totales · {cc.parcial ?? 0} parciales · {cc.nula ?? 0} sin cobertura · {job.a_revision} a revisión
          </p>
        </section>
      )}
      <div className="barra-acciones"><Cancelar job={job} /></div>
      <p className="nota-honesta">No mostramos razonamiento: el modelo solo entrega un veredicto con citas, y cada cita se verifica contra el texto del documento.</p>
    </>
  );
}
