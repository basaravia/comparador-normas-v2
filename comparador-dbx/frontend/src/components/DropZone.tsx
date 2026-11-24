import { useRef, useState } from "react";
import { Icono } from "./Icono";

/** Zona de carga. En el tope de documentos queda desactivada y dice por qué (`textoTope`). */
export function DropZone({ onArchivos, deshabilitado, textoTope }: { onArchivos: (a: File[]) => void; deshabilitado?: boolean; textoTope?: string }) {
  const entrada = useRef<HTMLInputElement>(null);
  const [encima, setEncima] = useState(false);
  const off = !!deshabilitado || !!textoTope;

  const recibir = (lista: FileList | null) => {
    if (!lista || off) return;
    const archivos = Array.from(lista);
    if (archivos.length) onArchivos(archivos);        // quién filtra los que no son PDF es la página (así puede avisar cuáles omitió)
  };

  return (
    <div
      id="zona-carga"
      className={`dropzone${encima ? " encima" : ""}${off ? " off" : ""}`}
      onDragOver={(ev) => { ev.preventDefault(); if (!off) setEncima(true); }}
      onDragLeave={() => setEncima(false)}
      onDrop={(ev) => { ev.preventDefault(); setEncima(false); recibir(ev.dataTransfer.files); }}
      onClick={() => { if (!off) entrada.current?.click(); }}
      role="button"
      tabIndex={off ? -1 : 0}
      aria-disabled={off}
      onKeyDown={(ev) => { if (!off && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); entrada.current?.click(); } }}
    >
      <div className="dz-icono" aria-hidden><Icono nombre="subir" tam="2.6rem" /></div>
      {textoTope ? <p className="dz-titulo">{textoTope}</p> : (
        <>
          <p className="dz-titulo">Arrastra aquí tus normativas y manuales (PDF)</p>
          <p className="dz-sub">o haz clic para elegirlos desde tu equipo</p>
        </>
      )}
      <input ref={entrada} type="file" accept="application/pdf,.pdf" multiple hidden
        onChange={(ev) => { recibir(ev.target.files); ev.target.value = ""; }} />
    </div>
  );
}
