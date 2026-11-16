import { useEffect, useRef, useState } from "react";
import { marcarAvisados, ocultarAvisoEnSesion } from "../recuerdo.ts";
import { useStore } from "../store";

/** Aviso "tus PDF no se guardan" (docs/ux/aviso-pdf-no-guardado.md): diálogo modal; Esc equivale a "Entendido, continuar". */
export function AvisoPdf() {
  const { e, d } = useStore();
  const dlg = useRef<HTMLDialogElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const [ocultar, setOcultar] = useState(false);
  const aviso = e.avisoPdf;

  useEffect(() => {
    const el = dlg.current;
    if (el && !el.open) el.showModal();
    boton.current?.focus();
    return () => { if (el?.open) el.close(); };
  }, []);

  if (!aviso) return null;
  const docs = e.documentos.filter((x) => aviso.ids.includes(x.id));
  const horas = e.sesionInfo?.retencion_horas;
  const plazo = horas !== undefined ? `hasta ${horas} horas sin actividad` : "un tiempo limitado sin actividad";

  const continuar = () => {
    marcarAvisados(aviso.ids, e.sesionInfo?.iniciada_ts);
    if (ocultar) ocultarAvisoEnSesion();
    d({ t: "cerrarAviso" });
    requestAnimationFrame(() => document.getElementById("encabezado-seleccion")?.focus());     // el botón anterior ya no existe
  };

  return (
    <dialog ref={dlg} className="dialogo" aria-labelledby="aviso-titulo" aria-describedby="aviso-cuerpo"
      onCancel={(ev) => { ev.preventDefault(); continuar(); }}>
      <h2 id="aviso-titulo">Tus documentos están listos. Guarda tus PDF.</h2>
      <div id="aviso-cuerpo">
        <p>Esta aplicación no guarda tus PDF. Solo conserva los datos de cada documento y su contenido preparado para buscar,
          {" "}{plazo} o hasta que la aplicación se reinicie. Después tendrás que cargarlos de nuevo.</p>
        <p>Conserva tu PDF original y anota qué archivo es (nombre, versión y fecha). Lo necesitarás para respaldar tu papel de trabajo.</p>
        <ul>{docs.map((x) => <li key={x.id}>{x.nombre}{x.paginas > 0 && <> · {x.paginas} pág.</>}</li>)}</ul>
      </div>
      <label className="casilla"><input type="checkbox" checked={ocultar} onChange={(ev) => setOcultar(ev.target.checked)} /> No volver a mostrar en esta sesión</label>
      <div className="barra-acciones">
        <button className="primario" ref={boton} onClick={continuar}>Entendido, continuar</button>
      </div>
    </dialog>
  );
}
