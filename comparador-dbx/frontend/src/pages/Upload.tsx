import { useState } from "react";
import { api, ApiError } from "../api";
import { DocTable } from "../components/DocTable";
import { DropZone } from "../components/DropZone";
import { useStore } from "../store";

export function Upload() {
  const { e, d } = useStore();
  const [ocupado, setOcupado] = useState("");
  const [error, setError] = useState("");

  const manejar = async (fn: () => Promise<void>, texto: string) => {
    setOcupado(texto); setError("");
    try { await fn(); }
    catch (x) {
      if (x instanceof ApiError && x.sesionPerdida) d({ t: "sesionPerdida" });
      else setError(x instanceof ApiError ? x.message : "Ocurrió un problema inesperado.");
    } finally { setOcupado(""); }
  };

  const validos = e.documentos.filter((x) => x.estado !== "error");
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
    d({ t: "job", job }); d({ t: "paso", paso: "procesando" });
  }, "Iniciando…");

  return (
    <div className="pagina">
      {e.sesionPerdida && (
        <div className="banner banner-aviso">
          La sesión se reinició y los documentos ya no están disponibles. Vuelve a cargarlos o usa el ejemplo.
        </div>
      )}
      <DropZone deshabilitado={!!ocupado} onArchivos={(f) => manejar(async () => {
        d({ t: "agregar", documentos: await api.subir(f) });
      }, "Leyendo los documentos…")} />
      {ocupado && <p className="ocupado">{ocupado}</p>}
      {error && <div className="banner banner-error">{error}</div>}
      <DocTable docs={e.documentos} editable={!ocupado} onCambio={(x) => d({ t: "doc", documento: x })} onError={setError} />
      {ayuda && <p className="ayuda">{ayuda}</p>}
      <div className="barra-acciones">
        <button className="primario" disabled={!puedeProcesar} onClick={procesar}>
          {validos.length > 0 && pendientes.length === 0 ? "Continuar a la selección" : "Procesar"}
        </button>
        <button className="secundario" disabled={!!ocupado} onClick={() => manejar(async () => {
          d({ t: "documentos", documentos: await api.ejemplo() });
          d({ t: "paso", paso: "seleccion" });
        }, "Cargando el ejemplo…")}>Cargar ejemplo</button>
        <button className="enlace" disabled={!!ocupado} onClick={() => manejar(async () => {
          await api.reiniciar(); d({ t: "reiniciar" });
        }, "Reiniciando…")}>Reiniciar sesión</button>
      </div>
    </div>
  );
}
