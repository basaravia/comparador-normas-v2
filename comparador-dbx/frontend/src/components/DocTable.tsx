import { useState } from "react";
import { api, ApiError } from "../api";
import type { DocumentoOut, Metadatos, Tipo } from "../tipos";

export const ESTADOS: Record<string, string> = {
  cargado: "Cargado", en_cola: "En cola", extrayendo: "Extrayendo", seccionando: "Seccionando",
  indexando: "Indexando", listo: "Listo", error: "Error",
};

const CAMPOS: [keyof Metadatos, string][] = [
  ["entidad_emisora", "Entidad emisora"], ["titulo_oficial", "Título oficial"], ["libro", "Libro"], ["titulo", "Título"],
  ["capitulo", "Capítulo"], ["numero_norma", "Número de norma"], ["fecha_vigencia", "Fecha de vigencia"],
];

function Fila({ doc, editable, onCambio, onError }: {
  doc: DocumentoOut; editable: boolean; onCambio: (d: DocumentoOut) => void; onError: (m: string) => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const [meta, setMeta] = useState<Metadatos>(doc.metadatos);

  const guardar = async (parche: { tipo?: Tipo | null; metadatos?: Partial<Metadatos> }) => {
    try { onCambio(await api.editarDoc(doc.id, parche)); }
    catch (e) { onError(e instanceof ApiError ? e.message : "No pudimos guardar el cambio."); }
  };

  const sinTipo = doc.tipo === null && doc.estado !== "error";
  return (
    <>
      <tr className={`${sinTipo ? "fila-alerta" : ""}${doc.estado === "error" ? " fila-error" : ""}`}>
        <td className="nombre">
          <span title={doc.nombre}>{doc.nombre}</span>
          {doc.paginas > 0 && <small> · {doc.paginas} pág.</small>}
        </td>
        <td>
          <select value={doc.tipo ?? ""} disabled={!editable || doc.estado === "error"}
            onChange={(ev) => guardar({ tipo: (ev.target.value || null) as Tipo | null })} aria-label={`Tipo de ${doc.nombre}`}>
            <option value="">Elige el tipo…</option>
            <option value="normativa">Normativa</option>
            <option value="manual_control">Manual de control</option>
          </select>
          {doc.tipo_sugerido && doc.tipo && <small className="sugerido"> sugerido</small>}
        </td>
        <td>
          <span className={`estado estado-${doc.estado}`}>{ESTADOS[doc.estado] ?? doc.estado}</span>
        </td>
        <td className="acciones">
          {doc.estado !== "error" && (
            <button className="enlace" onClick={() => setAbierto(!abierto)}>{abierto ? "Ocultar datos" : "Datos del documento"}</button>
          )}
        </td>
      </tr>
      {(doc.error || doc.advertencias.length > 0) && (
        <tr className="fila-nota"><td colSpan={4}>
          {doc.error && <div className="nota-error">{doc.error.mensaje} <small>({doc.error.codigo})</small></div>}
          {doc.advertencias.map((a, i) => <div key={i} className="nota-aviso">⚠ {a}</div>)}
        </td></tr>
      )}
      {abierto && (
        <tr className="fila-meta"><td colSpan={4}>
          <div className="meta-grid">
            {CAMPOS.map(([k, etiqueta]) => (
              <label key={k}>{etiqueta}
                <input value={meta[k] ?? ""} disabled={!editable}
                  onChange={(ev) => setMeta({ ...meta, [k]: ev.target.value || null })}
                  onBlur={() => { if ((meta[k] ?? "") !== (doc.metadatos[k] ?? "")) guardar({ metadatos: { [k]: meta[k] } }); }} />
              </label>
            ))}
          </div>
        </td></tr>
      )}
    </>
  );
}

export function DocTable({ docs, editable, onCambio, onError }: {
  docs: DocumentoOut[]; editable: boolean; onCambio: (d: DocumentoOut) => void; onError: (m: string) => void;
}) {
  if (docs.length === 0) return null;
  return (
    <table className="tabla docs">
      <thead><tr><th>Archivo</th><th>Tipo</th><th>Estado</th><th></th></tr></thead>
      <tbody>{docs.map((d) => <Fila key={d.id} doc={d} editable={editable} onCambio={onCambio} onError={onError} />)}</tbody>
    </table>
  );
}
