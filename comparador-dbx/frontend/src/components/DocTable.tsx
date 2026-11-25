import { useState } from "react";
import { api, ApiError } from "../api";
import { Icono } from "./Icono";
import type { DocumentoOut, Metadatos, Tipo } from "../tipos";

export const ESTADOS: Record<string, string> = {
  cargado: "Cargado", en_cola: "En cola", extrayendo: "Extrayendo", seccionando: "Seccionando",
  indexando: "Indexando", listo: "Indexado · PDF no guardado", error: "Error",
};

const CAMPOS: [keyof Metadatos, string][] = [
  ["entidad_emisora", "Entidad emisora"], ["titulo_oficial", "Título oficial"], ["libro", "Libro"], ["titulo", "Título"],
  ["capitulo", "Capítulo"], ["numero_norma", "Número de norma"], ["fecha_vigencia", "Fecha de vigencia"],
];

const EN_PROCESO = ["en_cola", "extrayendo", "seccionando", "indexando"];

interface Acciones {
  max?: number;                          // máximo de documentos (para la nota de los fallidos)
  bloqueado: boolean;                    // hay un proceso en marcha: no se puede quitar
  reintentos: Set<string>;               // fallidos que la persona quiere volver a procesar
  onReintentar: (d: DocumentoOut) => void;
  onQuitar: (d: DocumentoOut) => void;
}

function Fila({ doc, editable, onCambio, onError, acc }: {
  doc: DocumentoOut; editable: boolean; onCambio: (d: DocumentoOut) => void; onError: (m: string) => void; acc: Acciones;
}) {
  const [abierto, setAbierto] = useState(false);
  const [ayuda, setAyuda] = useState(false);
  const reintento = acc.reintentos.has(doc.id);
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
          <select value={doc.tipo ?? ""} disabled={!editable || (doc.estado === "error" && !reintento)}
            onChange={(ev) => guardar({ tipo: (ev.target.value || null) as Tipo | null })} aria-label={`Tipo de ${doc.nombre}`}>
            <option value="">Elige el tipo…</option>
            <option value="normativa">Normativa</option>
            <option value="manual_control">Manual de control</option>
          </select>
          {doc.tipo_sugerido && doc.tipo && <small className="sugerido"> sugerido</small>}
        </td>
        <td>
          <span className={`estado estado-${doc.estado}`}>{doc.es_ejemplo && doc.estado === "listo" ? "Indexado" : (ESTADOS[doc.estado] ?? doc.estado)}</span>
          {doc.estado === "listo" && !doc.es_ejemplo && (          // el ejemplo no viene de un PDF: no hay nada que explicar (D-53)
            <button className="enlace ayuda-btn" aria-expanded={ayuda} aria-controls={`ayuda-${doc.id}`} aria-label="¿Qué significa Indexado?" onClick={() => setAyuda(!ayuda)}>?</button>
          )}
          {ayuda && <small id={`ayuda-${doc.id}`} className="ayuda-estado">La aplicación conserva los datos y el contenido buscable, no el archivo PDF original.</small>}
          {reintento && <small className="ayuda-estado">Se reintentará al pulsar Procesar.</small>}
        </td>
        <td className="acciones">
          {doc.estado !== "error" && (
            <button className="enlace" onClick={() => setAbierto(!abierto)}>{abierto ? "Ocultar datos" : "Datos del documento"}</button>
          )}
          {doc.estado === "error" && (
            <button className="enlace" aria-pressed={reintento} aria-label={`Reintentar ${doc.nombre}`} disabled={!editable || acc.bloqueado} onClick={() => acc.onReintentar(doc)}>Reintentar</button>
          )}
          <button className="enlace" aria-label={`Quitar ${doc.nombre}`} aria-describedby={acc.bloqueado ? "ayuda-quitar" : undefined}
            disabled={!editable || acc.bloqueado || EN_PROCESO.includes(doc.estado)} onClick={() => acc.onQuitar(doc)}>Quitar</button>
        </td>
      </tr>
      {(doc.error || doc.advertencias.length > 0) && (
        <tr className="fila-nota"><td colSpan={4}>
          {doc.error && <div className="nota-error">{doc.error.mensaje} <small>({doc.error.codigo})</small></div>}
          {doc.estado === "error" && <div className="nota-aviso">Este documento no cuenta para el máximo{acc.max !== undefined ? ` de ${acc.max}` : ""}.</div>}
          {doc.advertencias.map((a, i) => <div key={i} className="nota-aviso"><Icono nombre="aviso" /> {a}</div>)}
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

export function DocTable({ docs, editable, onCambio, onError, acciones }: {
  docs: DocumentoOut[]; editable: boolean; onCambio: (d: DocumentoOut) => void; onError: (m: string) => void; acciones: Acciones;
}) {
  if (docs.length === 0) return null;
  return (
    <>
    {acciones.bloqueado && <p id="ayuda-quitar" className="ayuda">Espera a que termine el proceso o cancélalo para quitar documentos.</p>}
    <table className="tabla docs">
      <thead><tr><th>Archivo</th><th>Tipo</th><th>Estado</th><th></th></tr></thead>
      <tbody>{docs.map((d) => <Fila key={d.id} doc={d} editable={editable} onCambio={onCambio} onError={onError} acc={acciones} />)}</tbody>
    </table>
    </>
  );
}
