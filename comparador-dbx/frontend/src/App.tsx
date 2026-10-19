import { useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { Processing } from "./pages/Processing";
import { Ajustes } from "./pages/Ajustes";
import { Results } from "./pages/Results";
import { Selector } from "./pages/Selector";
import { Upload } from "./pages/Upload";
import { useStore, type Paso } from "./store";
import type { HealthOut } from "./tipos";

const PASOS: { id: "carga" | "seleccion" | "resultados"; texto: string }[] = [
  { id: "carga", texto: "1 · Carga" }, { id: "seleccion", texto: "2 · Selección" }, { id: "resultados", texto: "3 · Resultados" },
];
const GRUPO: Record<Paso, "carga" | "seleccion" | "resultados"> = {
  carga: "carga", procesando: "carga", seleccion: "seleccion", comparando: "seleccion", resultados: "resultados",
};

export default function App() {
  const { e, d } = useStore();
  const [salud, setSalud] = useState<HealthOut | null>(null);
  const [listo, setListo] = useState(false);
  const [verAjustes, setVerAjustes] = useState(false);     // el panel no cambia `paso`: el flujo sigue montado (y sondeando) detrás

  // Al abrir (o recargar la página) se recupera lo que haya en la sesión.
  useEffect(() => {
    (async () => {
      try {
        const s = await api.sesion();
        d({ t: "documentos", documentos: s.documentos });
        if (s.comparacion_id) {
          d({ t: "comparacion", comparacion: await api.comparacion(s.comparacion_id) });
          d({ t: "paso", paso: "resultados" });
        } else if (s.documentos.length > 0 && s.documentos.every((x) => x.estado === "listo")) {
          d({ t: "paso", paso: "seleccion" });
        }
      } catch (x) {
        if (x instanceof ApiError && x.sesionPerdida) d({ t: "sesionPerdida" });
      } finally { setListo(true); }
      api.salud().then(setSalud).catch(() => setSalud({ estado: "degradado", stage: "", llm: false, mensaje: "No pudimos conectarnos al servicio." }));
    })();
  }, [d]);

  const grupo = GRUPO[e.paso];
  const puedeIr = (id: string) =>
    id === "carga" ? e.paso !== "procesando" && e.paso !== "comparando"
      : id === "seleccion" ? e.paso !== "procesando" && e.paso !== "comparando" && e.documentos.some((x) => x.estado === "listo")
      : e.paso !== "procesando" && e.paso !== "comparando" && e.comparacion !== null;

  return (
    <>
      <header className="cabecera">
        <div className="marca-app"><span className="logo" aria-hidden>⚖</span> Comparador Normativo</div>
        <nav className="pasos" aria-label="Pasos">
          {PASOS.map((p) => (
            <button key={p.id} className={!verAjustes && grupo === p.id ? "paso activo" : "paso"} disabled={!puedeIr(p.id)}
              aria-current={!verAjustes && grupo === p.id ? "step" : undefined} onClick={() => { setVerAjustes(false); d({ t: "paso", paso: p.id }); }}>{p.texto}</button>
          ))}
        </nav>
        <button className={verAjustes ? "paso activo" : "paso"} aria-pressed={verAjustes} onClick={() => setVerAjustes(!verAjustes)}>⚙ Ajustes</button>
        <div className="estado-servicio">
          {salud && <span className={salud.estado === "ok" ? "punto ok" : "punto mal"} title={salud.mensaje || (salud.estado === "ok" ? "Servicio disponible" : "Servicio con problemas")}>
            {salud.estado === "ok" ? "Servicio disponible" : "Servicio con problemas"}</span>}
        </div>
      </header>
      {salud?.estado === "degradado" && (
        <div className="banner banner-aviso">No pudimos conectarnos al servicio de análisis. Intenta de nuevo en un momento.</div>
      )}
      <main>
        {verAjustes && <Ajustes onSesionPerdida={() => setVerAjustes(false)} />}
        <div hidden={verAjustes}>
        {!listo ? <div className="pagina"><p className="ocupado">Cargando…</p></div> :
          e.paso === "carga" ? <Upload /> :
          e.paso === "procesando" ? <Processing tipo="procesamiento" /> :
          e.paso === "seleccion" ? <Selector /> :
          e.paso === "comparando" ? <Processing tipo="comparacion" /> :
          <Results />}
        </div>
      </main>
    </>
  );
}
