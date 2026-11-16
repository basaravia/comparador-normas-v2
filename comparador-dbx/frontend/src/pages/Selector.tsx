import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { hayConflictoDeManuales, hojas, manualesConMarcas, quitarMarcasDeDoc, seleccionTrasRecarga } from "../arbol.ts";
import { DualTree } from "../components/DualTree";
import { verAvance } from "../sincronizar.ts";
import { useStore } from "../store";
import type { ArbolDocOut, SeccionOut } from "../tipos";

/** "Se conservaron tus N marcas." y, si un manual nuevo llegó sin marcar porque ya se trabaja con otro, por qué. */
function mensajeTrasAgregar(previa: Set<string>, nueva: Set<string>, vistos: ArbolDocOut[], manuales: ArbolDocOut[]): string {
  const n = [...nueva].filter((i) => previa.has(i)).length;
  const partes: string[] = [];
  if (n > 0) partes.push(n === 1 ? "Se conservó tu marca." : `Se conservaron tus ${n} marcas.`);
  const docsVistos = new Set(vistos.map((a) => a.doc_id));
  const enUso = manualesConMarcas(manuales.filter((a) => docsVistos.has(a.doc_id)), nueva)[0];
  if (enUso) manuales.filter((a) => !docsVistos.has(a.doc_id)).forEach((a) => partes.push(`«${a.nombre}» llegó sin marcar porque ya trabajas con «${enUso.nombre}».`));
  return partes.join(" ");
}

export function Selector() {
  const { e, d } = useStore();
  const [error, setError] = useState("");
  const [vista, setVista] = useState<SeccionOut | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [info, setInfo] = useState("");              // "Se conservaron tus N marcas." al volver de agregar documentos
  const [hayProceso, setHayProceso] = useState(false);

  useEffect(() => {
    if (e.seleccionLista) { if (e.agregando) d({ t: "agregandoFin" }); return; }
    (async () => {
      try {
        const [normas, manuales] = await Promise.all([api.arbol("normativa"), api.arbol("manual_control")]);
        const vistos = [...(e.normas ?? []), ...(e.manuales ?? [])];
        const nueva = seleccionTrasRecarga(e.seleccion, vistos, normas, manuales);
        if (e.agregando) setInfo(mensajeTrasAgregar(e.seleccion, nueva, vistos, manuales));
        d({ t: "arboles", normas, manuales, seleccion: nueva });
      } catch (x) {
        if (x instanceof ApiError && x.sesionPerdida) d({ t: "sesionPerdida" });
        else setError(x instanceof ApiError ? x.message : "No pudimos cargar las secciones.");
      }
    })();
  }, [e.seleccionLista, d]);

  if (!e.normas || !e.manuales) {
    return (
      <div className="pagina">
        <h2 id="encabezado-seleccion" tabIndex={-1}>Elige qué comparar</h2>
        {error ? <div className="banner banner-error" role="alert">{error}</div> : <p className="ocupado">Cargando las secciones…</p>}
      </div>
    );
  }

  const idsDe = (arboles: ArbolDocOut[]) => arboles.flatMap((a) => a.nodos.flatMap(hojas)).map((h) => h.id);
  const delArbol = (arboles: ArbolDocOut[]) => { const ids = new Set(idsDe(arboles)); return [...e.seleccion].filter((i) => ids.has(i)); };
  const articulos = delArbol(e.normas), secciones = delArbol(e.manuales);
  const docsConSel = (arboles: ArbolDocOut[]) => arboles.filter((a) => a.nodos.flatMap(hojas).some((h) => e.seleccion.has(h.id))).length;

  const ver = async (id: string) => {
    try { setVista(await api.seccion(id)); }
    catch (x) { setError(x instanceof ApiError ? x.message : "No pudimos abrir la sección."); }
  };

  const comparar = async () => {
    setOcupado(true); setError("");
    try {
      const job = await api.comparar({ articulo_ids: articulos, seccion_ids: secciones });
      d({ t: "comparacion", comparacion: null }); d({ t: "job", job }); d({ t: "paso", paso: "comparando" });
    } catch (x) {
      if (x instanceof ApiError && x.sesionPerdida) d({ t: "sesionPerdida" });
      else {
        if (x instanceof ApiError && x.procesoEnMarcha) setHayProceso(true);
        setError(x instanceof ApiError ? x.message : "No pudimos iniciar la comparación.");
      }
    } finally { setOcupado(false); }
  };

  const nN = docsConSel(e.normas), nM = docsConSel(e.manuales);
  const usados = manualesConMarcas(e.manuales, e.seleccion);
  const conflicto = hayConflictoDeManuales(e.manuales, e.seleccion);
  const quitarMarcas = (a: ArbolDocOut) => d({ t: "seleccion", seleccion: quitarMarcasDeDoc(a, e.seleccion) });
  const verAviso = () => d({ t: "abrirAviso", ids: e.documentos.filter((x) => x.estado === "listo").map((x) => x.id), entrar: false });
  const agregar = () => d({ t: "agregarDocs" });
  const plural = (n: number, s: string, p: string) => `${n} ${n === 1 ? s : p}`;

  return (
    <div className="pagina ancha">
      <h2 id="encabezado-seleccion" tabIndex={-1}>Elige qué comparar</h2>
      <div className="franja-pdf" role="note">
        <span>Los PDF no se guardan en esta aplicación. Conserva los originales.</span>
        <button className="enlace" onClick={verAviso}>Ver aviso</button>
        <button className="enlace" onClick={agregar}>Agregar documentos</button>
      </div>
      {info && <div className="banner banner-ok" role="status">{info}</div>}
      {error && (
        <div className="banner banner-error" role="alert">{error}
          {hayProceso && <> <button className="secundario" onClick={async () => { try { if (!(await verAvance(d))) setHayProceso(false); } catch { /* se queda el mensaje */ } }}>Ver avance</button></>}
        </div>
      )}
      <div className="duales">
        <DualTree titulo="Normativas" vacio="No hay normativas procesadas." arboles={e.normas} sel={e.seleccion}
          onSel={(s) => d({ t: "seleccion", seleccion: s })} onVer={ver} />
        <DualTree titulo="Manuales de control" vacio="No hay manuales procesados." arboles={e.manuales} sel={e.seleccion}
          nota={e.manuales.length > 1 ? "La comparación usa un manual a la vez. Elige en cuál trabajar." : undefined}
          onQuitarMarcas={conflicto ? quitarMarcas : undefined}
          onSel={(s) => d({ t: "seleccion", seleccion: s })} onVer={ver} />
      </div>

      {vista && (
        <aside className="vista" aria-label="Vista previa del texto">
          <div className="vista-cab">
            <strong>{vista.doc_nombre} · {vista.identificador}{vista.titulo ? ` · ${vista.titulo}` : ""}</strong>
            <small> · pág. {vista.pagina_inicio}{vista.pagina_fin !== vista.pagina_inicio ? `–${vista.pagina_fin}` : ""}</small>
            <button className="enlace" onClick={() => setVista(null)}>Cerrar</button>
          </div>
          {vista.incierto && <div className="nota-aviso">⚠ Esta sección se detectó por longitud; revísala.</div>}
          {vista.ruta.length > 0 && <div className="vista-ruta">{vista.ruta.join(" › ")}</div>}
          <pre className="vista-texto">{vista.texto}</pre>
        </aside>
      )}

      <footer className="pie-seleccion">
        <span id="pie-texto" role={conflicto ? "alert" : undefined}>
          {conflicto
            ? <>Hay marcas en {usados.length} manuales ({usados.map((m) => `«${m.nombre}»`).join(", ")}). La comparación usa un manual a la vez: quita las marcas de los que no vayas a usar.</>
            : <>Vas a comparar <strong>{plural(articulos.length, "artículo", "artículos")}</strong> de {plural(nN, "normativa", "normativas")} contra{" "}
              <strong>{plural(secciones.length, "sección", "secciones")}</strong> {usados.length === 1 ? <>de «{usados[0].nombre}»</> : <>de {plural(nM, "manual", "manuales")}</>}.</>}
        </span>
        <button className="secundario" onClick={agregar}>Agregar documentos</button>
        <button className="primario" aria-describedby="pie-texto" disabled={articulos.length === 0 || secciones.length === 0 || ocupado || conflicto} onClick={comparar}>Comparar</button>
      </footer>
    </div>
  );
}
