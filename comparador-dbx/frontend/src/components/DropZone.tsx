import { useRef, useState } from "react";

export function DropZone({ onArchivos, deshabilitado }: { onArchivos: (a: File[]) => void; deshabilitado?: boolean }) {
  const entrada = useRef<HTMLInputElement>(null);
  const [encima, setEncima] = useState(false);

  const recibir = (lista: FileList | null) => {
    if (!lista || deshabilitado) return;
    const pdfs = Array.from(lista).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length) onArchivos(pdfs);
  };

  return (
    <div
      className={`dropzone${encima ? " encima" : ""}${deshabilitado ? " off" : ""}`}
      onDragOver={(ev) => { ev.preventDefault(); setEncima(true); }}
      onDragLeave={() => setEncima(false)}
      onDrop={(ev) => { ev.preventDefault(); setEncima(false); recibir(ev.dataTransfer.files); }}
      onClick={() => entrada.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") entrada.current?.click(); }}
    >
      <div className="dz-icono" aria-hidden>⬆</div>
      <p className="dz-titulo">Arrastra aquí tus normativas y manuales (PDF)</p>
      <p className="dz-sub">o haz clic para elegirlos desde tu equipo</p>
      <input ref={entrada} type="file" accept="application/pdf,.pdf" multiple hidden
        onChange={(ev) => { recibir(ev.target.files); ev.target.value = ""; }} />
    </div>
  );
}
