import { useEffect, useId, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { useStore } from "../store";
import type { AjusteOut } from "../tipos";

const num = (s: string): number | null => (s.trim() === "" || !Number.isFinite(Number(s)) ? null : Number(s));
const coma = (n: number) => String(n).replace(".", ",");

/** Avisos locales «suaves»: el servidor manda y valida de verdad. `bloquea` solo cuando no hay número que enviar. */
function revisar(a: AjusteOut, texto: string): { bloquea: boolean; aviso: string } {
  const v = num(texto);
  if (v === null) return { bloquea: true, aviso: "Escribe un número." };
  if (a.tipo === "entero" && !Number.isInteger(v)) return { bloquea: false, aviso: "Debe ser un número entero." };
  if (v < a.minimo || v > a.maximo) return { bloquea: false, aviso: `Debe estar entre ${coma(a.minimo)} y ${coma(a.maximo)}.` };
  return { bloquea: false, aviso: "" };
}

function Campo({ a, texto, onCambio }: { a: AjusteOut; texto: string; onCambio: (t: string) => void }) {
  const id = useId();
  const r = revisar(a, texto);
  const v = num(texto);
  const distinto = v !== null && v !== a.defecto;
  return (
    <div className={`ajuste${r.aviso ? " con-aviso" : ""}`}>
      <label htmlFor={id}>{a.etiqueta}</label>
      <p className="ayuda" id={`${id}-ayuda`}>{a.ayuda}</p>
      <div className="ajuste-control">
        <input id={id} type="number" inputMode="decimal" value={texto} min={a.minimo} max={a.maximo} step={a.paso}
          aria-describedby={`${id}-ayuda ${id}-meta`} aria-invalid={r.aviso ? true : undefined} onChange={(ev) => onCambio(ev.target.value)} />
        <span className="ajuste-meta" id={`${id}-meta`}>
          Por defecto: <strong>{coma(a.defecto)}</strong> · rango {coma(a.minimo)} a {coma(a.maximo)}
          {distinto && <span className="distinto"> · ● Distinto del valor por defecto</span>}
        </span>
        {r.aviso && <span className="ajuste-aviso" role="alert">⚠ {r.aviso}</span>}
      </div>
    </div>
  );
}

export function Ajustes({ onSesionPerdida }: { onSesionPerdida: () => void }) {
  const { d } = useStore();
  const [params, setParams] = useState<AjusteOut[] | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const archivo = useRef<HTMLInputElement>(null);

  const aplicar = (p: AjusteOut[]) => { setParams(p); setForm(Object.fromEntries(p.map((a) => [a.clave, String(a.valor)]))); };
  const falla = (x: unknown) => {
    if (x instanceof ApiError && x.sesionPerdida) { d({ t: "sesionPerdida" }); onSesionPerdida(); return; }
    setMsg({ tipo: "error", texto: x instanceof ApiError ? x.message : "Ocurrió un problema inesperado. Intenta de nuevo." });
  };
  const correr = async (fn: () => Promise<void>) => { setOcupado(true); setMsg(null); try { await fn(); } catch (x) { falla(x); } finally { setOcupado(false); } };

  useEffect(() => { correr(async () => aplicar((await api.ajustes()).parametros)); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!params) return <div className="pagina"><h2>Ajustes</h2>{msg ? <div className="banner banner-error">{msg.texto}</div> : <p className="ocupado">Cargando los ajustes…</p>}</div>;

  const valoresForm = (): Record<string, number> => Object.fromEntries(params.map((a) => [a.clave, num(form[a.clave]) as number]));
  const hayBloqueo = params.some((a) => revisar(a, form[a.clave] ?? "").bloquea);
  const m = num(form.CITATION_SHOW_MIN ?? ""), v = num(form.CITATION_FUZZY_MIN ?? "");
  const cruce = m !== null && v !== null && m > v;
  const sinGuardar = params.some((a) => num(form[a.clave]) !== a.valor);
  const hayDistintos = params.some((a) => a.valor !== a.defecto);

  const guardar = () => correr(async () => {
    aplicar((await api.guardarAjustes({ valores: valoresForm() })).parametros);
    setMsg({ tipo: "ok", texto: "Ajustes guardados. Se usarán en la próxima comparación." });
  });
  const restablecer = () => correr(async () => {
    aplicar((await api.restablecerAjustes()).parametros);
    setMsg({ tipo: "ok", texto: "Se restablecieron los valores por defecto." });
  });
  const exportar = () => {
    const blob = new Blob([JSON.stringify({ valores: Object.fromEntries(params.map((a) => [a.clave, a.valor])) }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "ajustes-comparador.json"; a.click();
    URL.revokeObjectURL(url);
    setMsg({ tipo: "ok", texto: "Archivo ajustes-comparador.json descargado (con los ajustes ya guardados en esta sesión)." });
  };
  const importar = (f: File) => correr(async () => {
    let datos: unknown;
    try { datos = JSON.parse(await f.text()); } catch { throw new ApiError(0, "ERR-AJU-002", "El archivo no es un JSON válido."); }
    const vals = (datos as { valores?: unknown })?.valores;
    if (!datos || typeof datos !== "object" || Array.isArray(datos) || !vals || typeof vals !== "object" || Array.isArray(vals)
      || !Object.values(vals).every((x) => typeof x === "number" && Number.isFinite(x)) || Object.keys(vals).length === 0)
      throw new ApiError(0, "ERR-AJU-002", "El archivo no tiene el formato esperado: un objeto «valores» con números.");
    const conocidas = new Set(params.map((a) => a.clave));
    const ignoradas = Object.keys(vals).filter((k) => !conocidas.has(k)).length;
    aplicar((await api.guardarAjustes({ valores: vals as Record<string, number> })).parametros);
    setMsg({ tipo: "ok", texto: `Ajustes importados y guardados en esta sesión.${ignoradas ? ` Se ignoraron ${ignoradas} ajuste${ignoradas > 1 ? "s" : ""} que no se pueden cambiar.` : ""}` });
  });

  const basicos = params.filter((a) => !a.avanzado), avanzados = params.filter((a) => a.avanzado);
  const campo = (a: AjusteOut) => <Campo key={a.clave} a={a} texto={form[a.clave] ?? ""} onCambio={(t) => { setForm({ ...form, [a.clave]: t }); setMsg(null); }} />;

  return (
    <div className="pagina">
      <h2>Ajustes</h2>
      <p className="nota-info">Los ajustes aplican a la <strong>próxima comparación</strong> y <strong>expiran con la sesión</strong>. No cambian lo ya procesado ni los resultados que ya tienes. Para reutilizarlos en otra sesión, exporta el archivo.</p>
      {msg && <div className={msg.tipo === "ok" ? "banner banner-ok" : "banner banner-error"} role={msg.tipo === "ok" ? "status" : "alert"}>{msg.texto}</div>}
      <section className="ajustes-grupo">{basicos.map(campo)}</section>
      <details className="avanzado">
        <summary>Avanzado</summary>
        <div className="nota-aviso">Estos ajustes afectan la calidad de la verificación o el costo y el tiempo del análisis. Cámbialos solo si sabes lo que haces.</div>
        <section className="ajustes-grupo">{avanzados.map(campo)}</section>
      </details>
      {cruce && <div className="nota-aviso" role="alert">⚠ La exigencia para mostrar una cita no puede ser mayor que la exigida para validarla como literal.</div>}
      <div className="barra-acciones">
        <button className="primario" onClick={guardar} disabled={ocupado || hayBloqueo || !sinGuardar}>Guardar</button>
        <button className="secundario" onClick={restablecer} disabled={ocupado || (!hayDistintos && !sinGuardar)}>Restablecer valores por defecto</button>
        <span className="espaciador" />
        <button className="secundario" onClick={exportar} disabled={ocupado}>Exportar ajustes</button>
        <button className="secundario" onClick={() => archivo.current?.click()} disabled={ocupado}>Importar ajustes</button>
        <input ref={archivo} type="file" accept="application/json,.json" hidden aria-label="Importar ajustes desde un archivo JSON"
          onChange={(ev) => { const f = ev.target.files?.[0]; ev.target.value = ""; if (f) importar(f); }} />
      </div>
    </div>
  );
}
