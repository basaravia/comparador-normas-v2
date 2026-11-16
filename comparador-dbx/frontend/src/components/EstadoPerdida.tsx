import { useStore } from "../store";

/** Estado claro cuando se perdió lo cargado (docs/ux/mejoras-sesion-multicarga-v1.md §4). Estilo de aviso, no de error. */
export function EstadoPerdida() {
  const { e, d } = useStore();
  const p = e.perdida;
  if (!p) return null;
  const horas = e.sesionInfo?.retencion_horas;
  const cargarDeNuevo = () => { d({ t: "descartarPerdida" }); requestAnimationFrame(() => document.getElementById("zona-carga")?.focus()); };
  return (
    <div className="banner banner-aviso estado-perdida" role="alert">
      {p.motivo === "expirada" ? (
        <>
          <h2>Tus documentos se borraron por inactividad</h2>
          <p>Pasaron más de {horas !== undefined ? `${horas} horas` : "el tiempo de conservación"} sin uso y, por seguridad, se borraron tus documentos procesados y el resultado.
            Los papeles de trabajo que descargaste no cambian. Para seguir, carga de nuevo tus PDF.</p>
          <button className="secundario" onClick={() => d({ t: "descartarPerdida" })}>Entendido</button>
        </>
      ) : (
        <>
          <h2>Se perdió lo que tenías cargado</h2>
          <p>La aplicación se reinició y no guarda copias: tus documentos procesados, tus marcas y el resultado que no hayas descargado ya no están.
            No fue por algo que hiciste. Para seguir, carga de nuevo tus PDF originales y vuelve a procesarlos.
            {p.conProceso && " El proceso que estaba en curso también se detuvo."} <small>(ERR-SES-001)</small></p>
          <button className="secundario" onClick={cargarDeNuevo}>Cargar documentos de nuevo</button>
        </>
      )}
    </div>
  );
}
