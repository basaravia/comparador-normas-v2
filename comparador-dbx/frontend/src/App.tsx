import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { AvisoPdf } from "./components/AvisoPdf";
import { avisoParaMostrar, guardarRecuerdo } from "./recuerdo.ts";
import { traerSesion } from "./sincronizar.ts";
import { huellaUsuario } from "./sesion.ts";
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

  const [errorSesion, setErrorSesion] = useState("");
  const ultimo = useRef(e);
  ultimo.current = e;

  // Al abrir (o recargar la página) se recupera lo que haya en la sesión.
  useEffect(() => {
    (async () => {
      try {
        const s = await traerSesion(d);
        if (s.trabajo_activo) d({ t: "reenganchar", trabajo: s.trabajo_activo });
        else if (s.comparacion_id) {
          d({ t: "comparacion", comparacion: await api.comparacion(s.comparacion_id) });
          d({ t: "paso", paso: "resultados" });
        } else if (s.documentos.length > 0 && s.documentos.every((x) => x.estado === "listo")) {
          d({ t: "paso", paso: "seleccion" });
        }
        const ids = avisoParaMostrar(s.documentos, s.iniciada_ts);       // procesados mientras no estabas y aún sin avisar
        if (ids.length > 0 && !s.trabajo_activo) d({ t: "abrirAviso", ids, entrar: false });
      } catch (x) {
        if (x instanceof ApiError && x.sesionPerdida) d({ t: "sesionPerdida" });
        else if (x instanceof ApiError) setErrorSesion(x.message);          // por ejemplo ERR-SES-003: no pudimos identificar la cuenta
      } finally { setListo(true); }
      api.salud().then(setSalud).catch(() => setSalud({ estado: "degradado", stage: "", llm: false, mensaje: "No pudimos conectarnos al servicio." }));
    })();
  }, [d]);

  // Una llamada dijo "sesión perdida": se pide una sesión nueva para que la app quede usable al primer intento.
  useEffect(() => {
    if (!e.renovar) return;
    traerSesion(d, { perdidaConocida: true, conProceso: e.perdida?.conProceso })
      .catch((x) => { if (x instanceof ApiError) setErrorSesion(x.message); })
      .finally(() => d({ t: "renovada" }));
  }, [e.renovar, d]);   // eslint-disable-line react-hooks/exhaustive-deps

  // Dos pestañas: al volver a ésta se reconcilia con el servidor (lista de documentos, trabajo activo).
  useEffect(() => {
    const alVolver = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const s = await traerSesion(d);
        setErrorSesion("");
        const p = ultimo.current.paso;
        if (s.trabajo_activo && p !== "procesando" && p !== "comparando") d({ t: "reenganchar", trabajo: s.trabajo_activo });
      } catch (x) {
        if (x instanceof ApiError && x.sesionPerdida) d({ t: "sesionPerdida" });
      }
    };
    document.addEventListener("visibilitychange", alVolver);
    return () => document.removeEventListener("visibilitychange", alVolver);
  }, [d]);

  // El navegador recuerda cuándo fue la última actividad y cuántos documentos había (para explicar una pérdida).
  useEffect(() => {
    const i = e.sesionInfo;
    if (i?.iniciada_ts === undefined) return;
    guardarRecuerdo({ usuario: huellaUsuario(i.usuario), docs: e.documentos.length, iniciada_ts: i.iniciada_ts, ultima_ms: Date.now(), trabajo: !!e.trabajoActivo });
  }, [e.documentos, e.sesionInfo, e.job, e.trabajoActivo]);

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
      {e.sesionInfo?.usuario !== undefined && e.sesionInfo.retencion_horas !== undefined && (
        <p className="linea-cuenta" role="note">
          <strong>{e.sesionInfo.usuario}</strong> · Tus documentos procesados se conservan hasta {e.sesionInfo.retencion_horas} horas sin actividad o hasta que la aplicación se reinicie. Los PDF no se guardan.
        </p>
      )}
      {errorSesion && <div className="banner banner-error" role="alert">{errorSesion}</div>}
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
      {e.avisoPdf && <AvisoPdf />}
    </>
  );
}
