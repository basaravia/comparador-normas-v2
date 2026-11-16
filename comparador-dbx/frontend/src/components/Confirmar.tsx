import { useEffect, useRef, type ReactNode } from "react";

/** Confirmación de una acción destructiva: diálogo modal nativo, foco inicial en Cancelar, Esc cancela. */
export function Confirmar({ titulo, children, textoConfirmar, onConfirmar, onCancelar }: {
  titulo: string; children: ReactNode; textoConfirmar: string; onConfirmar: () => void; onCancelar: () => void;
}) {
  const dlg = useRef<HTMLDialogElement>(null);
  const cancelar = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const el = dlg.current;
    if (el && !el.open) el.showModal();
    cancelar.current?.focus();
    return () => { if (el?.open) el.close(); };
  }, []);
  return (
    <dialog ref={dlg} className="dialogo" role="alertdialog" aria-labelledby="conf-titulo" aria-describedby="conf-cuerpo"
      onCancel={(ev) => { ev.preventDefault(); onCancelar(); }}>
      <h2 id="conf-titulo">{titulo}</h2>
      <div id="conf-cuerpo">{children}</div>
      <div className="barra-acciones">
        <button className="secundario" ref={cancelar} onClick={onCancelar}>Cancelar</button>
        <button className="primario" onClick={onConfirmar}>{textoConfirmar}</button>
      </div>
    </dialog>
  );
}
