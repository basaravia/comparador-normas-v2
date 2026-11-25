import { useEffect, useRef, useState } from "react";
import {
  anuncioInicial, chipDe, citasVerificadas, contarNuevos, contarPorFiltro, corteVisible, debeRetener, duracion, estadoCita, estimadoDesdePares,
  etiquetaPar, partesPar, FILTROS, filtrar, maxSeq, ordenarFilas, paginar, paresPorPagina, porRevisar, siguienteAnuncio, textoCancelada, textoContador, textoEstimado, textoFase,
  visiblesHasta, type EstadoAnuncio, type Filtro, type FilaPar,
} from "../progresoComparacion.ts";
import type { FragmentoOut, JobOut, ParResuelto } from "../tipos";
import { Cancelar, transcurridoDe } from "./ProgresoVivo";
import { Icono, type NombreIcono } from "./Icono";

const ALTO_FILA = 48;   // px; para saber cuántas filas bajó la persona

function Cita({ titulo, frag, texto, estado }: { titulo: string; frag: FragmentoOut | string; texto?: string; estado: string }) {
  const f = typeof frag === "string" ? null : frag;
  return (
    <div className="cita-col">
      <h4>{titulo}</h4>
      <p className="cita-fuente">
        {f ? `${f.documento} · ${f.identificador}${f.pagina ? ` · pág. ${f.pagina}` : ""}` : String(frag)}
      </p>
      <p className="cita-estado">{estado}</p>
      {texto ? <blockquote>{texto}</blockquote> : null}
    </div>
  );
}

function DetalleResuelto({ p }: { p: ParResuelto }) {
  const [coment, setComent] = useState(false);
  const falta = p.elementos_faltantes ?? [];
  return (
    <>
      <div className="citas">
        <Cita titulo="Cita de la norma" frag={p.articulo} texto={p.cita_norma} estado={estadoCita("norma", p)} />
        <Cita titulo="Cita del manual" frag={p.seccion} texto={p.cita_manual} estado={estadoCita("manual", p)} />
      </div>
      {falta.length > 0 && (
        <div className="que-falta"><h4>Qué falta</h4><ul>{falta.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
      )}
      <p className="confianza">Confianza del modelo {Math.round(p.confianza * 100)} %</p>
      {p.comentario && (
        <>
          <button className="enlace" aria-expanded={coment} onClick={() => setComent(!coment)}>{coment ? "Ocultar comentario del modelo" : "Ver comentario del modelo"}</button>
          {coment && <p className="comentario-modelo">{p.comentario}</p>}
        </>
      )}
    </>
  );
}

function Fila({ f, abierta, alternar, cancelando }: { f: FilaPar; abierta: boolean; alternar: () => void; cancelando: boolean }) {
  const chip = chipDe(f, cancelando);
  const idDetalle = `detalle-${f.clave}`;
  const etiqueta = etiquetaPar(f.par.articulo, f.par.seccion);
  const partes = partesPar(f.par.articulo, f.par.seccion);
  return (
    <li className={`fila-par${f.tipo === "curso" ? " en-curso" : ""}`}>
      <button className="fila-cab" aria-expanded={abierta} aria-controls={idDetalle} onClick={alternar}>
        <span className={`chip chip-${chip.clase}`}><Icono nombre={chip.icono as NombreIcono} /> {chip.texto}</span>
        <span className="fila-etiqueta" title={etiqueta}>
          <span className="fila-ids">{partes.ids}</span>
          {partes.docs && <span className="fila-docs">{partes.docs}</span>}
        </span>
        {f.tipo === "resuelto" && (
          <span className={citasVerificadas(f.par) ? "citas-ok" : "citas-revisar"}>{citasVerificadas(f.par) ? <><Icono nombre="check" /> Citas verificadas</> : <><Icono nombre="aviso" /> Citas por revisar</>}</span>
        )}
        <span className="chevron" aria-hidden="true"><Icono nombre={abierta ? "abajo" : "derecha"} /></span>
      </button>
      <div id={idDetalle} className="fila-detalle" hidden={!abierta}>
        {abierta && (
          f.tipo === "resuelto" ? <DetalleResuelto p={f.par} /> : (
            <>
              <h4>Texto que se está evaluando</h4>
              <div className="citas">
                <div className="cita-col"><p className="cita-fuente">Norma · {f.par.articulo.documento} · {f.par.articulo.identificador} · pág. {f.par.articulo.pagina}</p><blockquote>{f.par.articulo.preview}…</blockquote></div>
                <div className="cita-col"><p className="cita-fuente">Manual · {f.par.seccion.documento} · {f.par.seccion.identificador} · pág. {f.par.seccion.pagina}</p><blockquote>{f.par.seccion.preview}…</blockquote></div>
              </div>
              <p className="confianza">Similitud {f.par.score.toFixed(2)}</p>
            </>
          )
        )}
      </div>
    </li>
  );
}

export function ComparacionEnCurso({ job, resueltos, ahora, alVolver }: { job: JobOut; resueltos: ParResuelto[]; ahora: () => number; alVolver: () => void }) {
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [paginas, setPaginas] = useState(1);
  const [abiertas, setAbiertas] = useState<Set<string>>(new Set());
  const [foco, setFoco] = useState(false);
  const [filasBajadas, setFilasBajadas] = useState(0);
  const [corte, setCorte] = useState(0);
  const [anuncio, setAnuncio] = useState("");
  const resumenRef = useRef<HTMLDivElement>(null);
  const listaRef = useRef<HTMLDivElement>(null);
  const anRef = useRef<EstadoAnuncio>(anuncioInicial);

  const ultimo = maxSeq(resueltos);
  const retener = debeRetener({ filasAbiertas: abiertas.size, focoEnLista: foco, filasBajadas });
  const corteEf = corteVisible(corte, ultimo, retener);
  useEffect(() => { if (!retener) setCorte(ultimo); }, [retener, ultimo]);

  // El resumen fijo no debe tapar el elemento que recibe el foco: se publica su alto y la página lo reserva en scroll-padding-top.
  useEffect(() => {
    const r = resumenRef.current;
    if (!r) return;
    const publicar = () => document.documentElement.style.setProperty("--alto-resumen", `${r.offsetHeight + 8}px`);
    publicar();
    const o = new ResizeObserver(publicar);
    o.observe(r);
    return () => { o.disconnect(); document.documentElement.style.removeProperty("--alto-resumen"); };
  }, []);

  // Cuántas filas dejó atrás la persona al bajar (la parte alta de la lista queda sobre el resumen fijo).
  useEffect(() => {
    const medir = () => {
      const l = listaRef.current, r = resumenRef.current;
      if (!l || !r) return;
      setFilasBajadas(Math.max(0, Math.floor((r.getBoundingClientRect().bottom - l.getBoundingClientRect().top) / ALTO_FILA)));
    };
    medir();
    window.addEventListener("scroll", medir, { passive: true });
    return () => window.removeEventListener("scroll", medir);
  }, []);

  const hechos = job.pares_hechos, total = job.pares_total, enAnalisis = job.pares_en_curso.length;
  const cancelando = !!job.cancelando && job.estado !== "cancelado";
  const activo = job.estado === "en_curso" || job.estado === "en_cola";
  const revisar = resueltos.filter(porRevisar).length;

  // Anuncios por hitos (nunca por par): se evalúa en cada actualización del trabajo.
  useEffect(() => {
    const r = siguienteAnuncio(anRef.current, {
      fase: job.fase, etapa: job.etapa, estado: job.estado, cancelando: !!job.cancelando, espera: job.espera_limite.activa,
      hechos, total, porRevisar: revisar,
    }, performance.now() / 1000);
    anRef.current = r.estado;
    if (r.texto) setAnuncio(r.texto);
  }, [job]);   // eslint-disable-line react-hooks/exhaustive-deps

  const conteos = contarPorFiltro(resueltos);
  const filtrados = filtrar(visiblesHasta(resueltos, corteEf), filtro);
  const { visibles, quedan } = paginar(filtrados, paginas, paresPorPagina(job));
  const filas = ordenarFilas(filtro === "todos" ? job.pares_en_curso : [], visibles);
  const nuevos = contarNuevos(resueltos, corteEf);

  const fase = textoFase(job.fase, job.etapa);
  const transcurrido = transcurridoDe(job, ahora);
  const est = activo && !cancelando ? textoEstimado(job.fase, hechos, total, transcurrido, estimadoDesdePares(job)) : null;
  const conBarra = total > 0 && job.fase !== "recuperando";
  const esp = job.espera_limite;
  const faltan = esp.activa ? Math.max(0, Math.ceil(esp.hasta_ts - ahora())) : 0;

  const alternar = (clave: string) => setAbiertas((s) => { const n = new Set(s); if (!n.delete(clave)) n.add(clave); return n; });
  const mostrarNuevos = () => { setCorte(ultimo); listaRef.current?.focus(); };

  return (
    <>
      <div className="resumen-fijo" ref={resumenRef}>
        <p className="fase-linea"><strong>{fase.texto}</strong></p>
        {conBarra && (
          <>
            <div className="barra-pares" role="progressbar" aria-label="Pares resueltos" aria-valuemin={0} aria-valuemax={total} aria-valuenow={hechos}
              aria-valuetext={`${hechos} de ${total} pares`}>
              <div className="progreso-barra" style={{ width: `${Math.min(100, (100 * hechos) / total)}%` }} />
            </div>
            <p className="contador">{textoContador(hechos, total, enAnalisis, activo)}</p>
          </>
        )}
        <p className="tiempos">Tiempo transcurrido: <strong>{duracion(transcurrido)}</strong>{est && <> · {est}</>}</p>
        {esp.activa && (
          <div className="banner banner-aviso">
            Esperando al servicio de IA (límite de uso del proveedor). Se reanuda en {faltan} s · intento {esp.intento} de {esp.max}.
          </div>
        )}
        {activo && <Cancelar job={job} pares={hechos} etiqueta="Cancelar comparación" nota="No se enviarán más pares." />}
        {job.estado === "cancelado" && (
          <div className="banner banner-aviso">
            {textoCancelada(hechos)} <button className="secundario" onClick={alVolver}>Volver</button>
          </div>
        )}
      </div>

      {activo && <p className="ayuda-linea">Cada par puede tardar varios minutos con el modelo local. Puedes dejar esta pestaña abierta o volver más tarde: el avance se conserva.</p>}
      <div className="filtros" role="group" aria-label="Filtrar pares resueltos" title="Conteo por par; las marcas A, L, R, X y P se calculan al final.">
        {FILTROS.map((f) => (
          <button key={f.id} className={filtro === f.id ? "activa" : ""} aria-pressed={filtro === f.id} onClick={() => { setFiltro(f.id); setPaginas(1); }}>
            {f.etiqueta} ({conteos[f.id]})
          </button>
        ))}
      </div>

      <div className="visually-hidden" role="status" aria-live="polite">{anuncio}</div>

      {nuevos > 0 && (
        <p className="nuevos"><button className="secundario" onClick={mostrarNuevos}>{nuevos === 1 ? "1 resultado nuevo" : `${nuevos} resultados nuevos`} · Mostrar</button></p>
      )}

      <div className="lista-pares" ref={listaRef} tabIndex={-1} aria-label="Pares"
        onFocus={() => setFoco(true)} onBlur={(ev) => { if (!ev.currentTarget.contains(ev.relatedTarget as Node | null)) setFoco(false); }}>
        {filas.length > 0 && (
          <ul className="filas">
            {filas.map((f) => <Fila key={f.clave} f={f} abierta={abiertas.has(f.clave)} alternar={() => alternar(f.clave)} cancelando={cancelando} />)}
          </ul>
        )}
        {resueltos.length === 0 && <p className="vacio-texto">Todavía no hay pares resueltos. El primero aparecerá aquí.</p>}
        {resueltos.length > 0 && filtro !== "todos" && filtrados.length === 0 && (
          <p className="vacio-texto">Ningún par resuelto coincide con este filtro. <button className="enlace" onClick={() => setFiltro("todos")}>Ver todos</button></p>
        )}
        {quedan > 0 && (
          <p><button className="secundario" onClick={() => setPaginas(paginas + 1)}>Mostrar {Math.min(paresPorPagina(job), quedan)} más (quedan {quedan})</button></p>
        )}
      </div>

      <p className="nota-honesta">Mostramos solo el veredicto y las citas, verificadas contra el texto del documento; no el razonamiento del modelo. Los resultados por par son provisionales: las marcas A, L, R, X y P se calculan al final, por artículo.</p>
    </>
  );
}
