import { useState } from "react";
import { api, ApiError } from "../api";
import { Confirmar } from "../components/Confirmar";
import { DocTable } from "../components/DocTable";
import { DropZone } from "../components/DropZone";
import { EstadoPerdida } from "../components/EstadoPerdida";
import { avisoParaMostrar, olvidarTodo } from "../recuerdo.ts";
import { cupoLibre, evaluarLote, usados } from "../sesion.ts";
import { traerSesion, verAvance } from "../sincronizar.ts";
import { useStore } from "../store";
import type { DocumentoOut } from "../tipos";

export function Upload() {
  const { e, d } = useStore();
  const [ocupado, setOcupado] = useState("");
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [avisosLote, setAvisosLote] = useState<string[]>([]);
  const [reintentos, setReintentos] = useState<Set<string>>(new Set());
  const [hayProceso, setHayProceso] = useState(false);          // el servidor dijo que ya hay un proceso en marcha
  const [quitando, setQuitando] = useState<DocumentoOut | null>(null);
  const [borrando, setBorrando] = useState(false);

  const manejar = async (fn: () => Promise<void>, texto: string) => {
    setOcupado(texto); setError(""); setOk("");
    try { await fn(); }
    catch (x) {
      if (x instanceof ApiError && x.sesionPerdida) d({ t: "sesionPerdida" });
      else {
        if (x instanceof ApiError && x.procesoEnMarcha) setHayProceso(true);
        setError(x instanceof ApiError ? x.message : "Ocurrió un problema inesperado.");
      }
    } finally { setOcupado(""); }
  };

  const max = e.sesionInfo?.max_documentos;
  const libres = cupoLibre(e.documentos, max);
  const lleno = libres === 0;
  const trabajoActivo = !!e.trabajoActivo || hayProceso;

  const validos = e.documentos.filter((x) => x.estado !== "error" || reintentos.has(x.id));
  const sinTipo = validos.filter((x) => !x.tipo).length;
  const hayNorma = validos.some((x) => x.tipo === "normativa");
  const hayManual = validos.some((x) => x.tipo === "manual_control");
  const pendientes = validos.filter((x) => x.estado !== "listo");
  const puedeProcesar = validos.length > 0 && sinTipo === 0 && hayNorma && hayManual && !ocupado;

  const ayuda = validos.length === 0 ? "" : sinTipo > 0 ? `Elige el tipo de ${sinTipo} documento${sinTipo > 1 ? "s" : ""} para continuar.`
    : !hayNorma ? "Falta al menos una normativa." : !hayManual ? "Falta al menos un manual de control." : "";

  const procesar = () => manejar(async () => {
    if (pendientes.length === 0) { d({ t: "paso", paso: "seleccion" }); return; }
    const job = await api.procesar(pendientes.map((x) => x.id));
    setReintentos(new Set());
    d({ t: "job", job }); d({ t: "paso", paso: "procesando" });
  }, "Iniciando…");

  const recibir = (archivos: File[]) => {
    const r = evaluarLote(archivos, libres, max);
    setAvisosLote(r.avisos);
    if (r.enviar.length === 0) return;
    manejar(async () => { d({ t: "agregar", documentos: await api.subir(r.enviar) }); }, "Leyendo los documentos…");
  };

  const quitar = (doc: DocumentoOut) => manejar(async () => {
    d({ t: "quitar", id: doc.id, sesion: await api.quitar(doc.id) });
    setReintentos((p) => { const s = new Set(p); s.delete(doc.id); return s; });
    setOk(`Se quitó «${doc.nombre}».`);
  }, "Quitando…");

  const alternarReintento = (doc: DocumentoOut) =>
    setReintentos((p) => { const s = new Set(p); if (s.has(doc.id)) s.delete(doc.id); else s.add(doc.id); return s; });

  const cargarEjemplo = () => manejar(async () => {
    await api.ejemplo();
    const s = await traerSesion(d);            // la lista completa sale del servidor
    if (s.documentos.some((x) => x.estado === "listo")) d({ t: "entrarSeleccion", aviso: avisoParaMostrar(s.documentos, s.iniciada_ts) });
  }, "Cargando el ejemplo…");

  const borrarTodo = () => manejar(async () => {
    await api.reiniciar();
    olvidarTodo(); setReintentos(new Set()); setHayProceso(false);
    d({ t: "reiniciar" });
    await traerSesion(d, { sinPerdida: true });
  }, "Borrando…");

  return (
    <div className="pagina">
      <EstadoPerdida />
      <DropZone deshabilitado={!!ocupado} onArchivos={recibir}
        textoTope={lleno ? `Llegaste al máximo de ${max} documentos. Quita alguno de la lista para agregar otro.` : undefined} />
      {max !== undefined && <p className="ayuda" role="status">{usados(e.documentos)} de {max} documentos</p>}
      {ocupado && <p className="ocupado">{ocupado}</p>}
      {avisosLote.map((a, i) => <div key={i} className="banner banner-aviso" role="status">{a}</div>)}
      {ok && <div className="banner banner-ok" role="status">{ok}</div>}
      {error && (
        <div className="banner banner-error" role="alert">{error}
          {hayProceso && <> <button className="secundario" onClick={() => manejar(async () => { if (!(await verAvance(d))) setHayProceso(false); }, "Abriendo el avance…")}>Ver avance</button></>}
        </div>
      )}
      <DocTable docs={e.documentos} editable={!ocupado} onCambio={(x) => d({ t: "doc", documento: x })} onError={setError}
        acciones={{ max, bloqueado: trabajoActivo, reintentos, onReintentar: alternarReintento,
          onQuitar: (doc) => (doc.estado === "listo" ? setQuitando(doc) : quitar(doc)) }} />
      {ayuda && <p className="ayuda">{ayuda}</p>}
      <div className="barra-acciones">
        {trabajoActivo
          ? <button className="primario" disabled={!!ocupado} onClick={() => manejar(async () => { if (!(await verAvance(d))) setHayProceso(false); }, "Abriendo el avance…")}>Ver avance</button>
          : <button className="primario" disabled={!puedeProcesar} onClick={procesar}>
              {validos.length > 0 && pendientes.length === 0 ? "Continuar a la selección" : "Procesar"}
            </button>}
        {e.documentos.length === 0 && <button className="secundario" disabled={!!ocupado} onClick={cargarEjemplo}>Cargar ejemplo</button>}
      </div>
      {e.documentos.length > 0 && (
        <div className="zona-borrado">
          <button className="enlace" disabled={!!ocupado || trabajoActivo} aria-describedby={trabajoActivo ? "ayuda-borrar" : undefined} onClick={() => setBorrando(true)}>
            Borrar todo y empezar de nuevo
          </button>
          {trabajoActivo && <small id="ayuda-borrar"> Cancela el proceso en curso antes de borrar.</small>}
        </div>
      )}

      {quitando && (
        <Confirmar titulo={`¿Quitar «${quitando.nombre}»?`} textoConfirmar="Quitar documento" onCancelar={() => setQuitando(null)}
          onConfirmar={() => { const x = quitando; setQuitando(null); quitar(x); }}>
          <p>Se borrará su contenido preparado y las marcas que hiciste en él. Si lo necesitas después, tendrás que cargarlo y procesarlo de nuevo (el PDF no está guardado aquí).</p>
          {e.comparacion && <p>Se descartará la comparación actual. Si aún no lo hiciste, descarga antes el papel de trabajo.</p>}
        </Confirmar>
      )}
      {borrando && (
        <Confirmar titulo="¿Borrar todo y empezar de nuevo?" textoConfirmar="Sí, borrar todo" onCancelar={() => setBorrando(false)}
          onConfirmar={() => { setBorrando(false); borrarTodo(); }}>
          <p>Se borrarán tus {e.documentos.length} documentos, tus marcas de selección y el resultado de la comparación, en todos tus dispositivos. No se puede deshacer.</p>
          {e.comparacion && <p>Si aún no lo hiciste, descarga antes el papel de trabajo.</p>}
        </Confirmar>
      )}
    </div>
  );
}
