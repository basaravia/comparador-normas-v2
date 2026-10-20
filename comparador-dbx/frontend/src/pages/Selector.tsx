import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { hojas, seleccionInicial, seleccionTrasRecarga } from "../arbol.ts";
import { DualTree } from "../components/DualTree";
import { useStore } from "../store";
import type { ArbolDocOut, SeccionOut } from "../tipos";

export function Selector() {
  const { e, d } = useStore();
  const [error, setError] = useState("");
  const [vista, setVista] = useState<SeccionOut | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    if (e.seleccionLista) return;
    (async () => {
      try {
        const [normas, manuales] = await Promise.all([api.arbol("normativa"), api.arbol("manual_control")]);
        d({ t: "arboles", normas, manuales, seleccion: seleccionTrasRecarga(e.seleccion, [...(e.normas ?? []), ...(e.manuales ?? [])], normas, manuales) });
      } catch (x) {
        if (x instanceof ApiError && x.sesionPerdida) d({ t: "sesionPerdida" });
        else setError(x instanceof ApiError ? x.message : "No pudimos cargar las secciones.");
      }
    })();
  }, [e.seleccionLista, d]);

  if (!e.normas || !e.manuales) {
    return <div className="pagina">{error ? <div className="banner banner-error">{error}</div> : <p className="ocupado">Cargando las secciones…</p>}</div>;
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
      else setError(x instanceof ApiError ? x.message : "No pudimos iniciar la comparación.");
    } finally { setOcupado(false); }
  };

  const nN = docsConSel(e.normas), nM = docsConSel(e.manuales);
  const plural = (n: number, s: string, p: string) => `${n} ${n === 1 ? s : p}`;

  return (
    <div className="pagina ancha">
      {error && <div className="banner banner-error">{error}</div>}
      <div className="duales">
        <DualTree titulo="Normativas" vacio="No hay normativas procesadas." arboles={e.normas} sel={e.seleccion}
          onSel={(s) => d({ t: "seleccion", seleccion: s })} onVer={ver} />
        <DualTree titulo="Manuales de control" vacio="No hay manuales procesados." arboles={e.manuales} sel={e.seleccion}
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
        <span>Vas a comparar <strong>{plural(articulos.length, "artículo", "artículos")}</strong> de {plural(nN, "normativa", "normativas")} contra{" "}
          <strong>{plural(secciones.length, "sección", "secciones")}</strong> de {plural(nM, "manual", "manuales")}.</span>
        <button className="primario" disabled={articulos.length === 0 || secciones.length === 0 || ocupado} onClick={comparar}>Comparar</button>
      </footer>
    </div>
  );
}
