import { useState } from "react";
import type { MarcaOut } from "../tipos";
import { Icono } from "./Icono";

/** Sin configuración (o si el servicio no responde) la cabecera es la de siempre: las escalas y el nombre del producto. */
export const MARCA_POR_DEFECTO: MarcaOut = { nombre_producto: "Comparador Normativo", texto_alternativo: "", logo_org: "", logo_producto: "", logo_pie: "" };

/** Un logo que no carga se oculta (sin icono de imagen rota): queda el texto. */
function Logo({ src, alt, clase }: { src: string; alt: string; clase: string }) {
  const [falla, setFalla] = useState(false);
  if (!src || falla) return null;
  return <img className={clase} src={src} alt={alt} onError={() => setFalla(true)} />;
}

const altOrg = (m: MarcaOut) => (m.texto_alternativo ? `Logo de ${m.texto_alternativo}` : "Logo");

/** Zona de marca de la cabecera: logo de la organización, logo del producto (opcional) y el nombre, que siempre se muestra. */
export function Marca({ marca }: { marca: MarcaOut }) {
  return (
    <div className="marca-app">
      <Logo src={marca.logo_org} alt={altOrg(marca)} clase="logo-org" />
      {marca.logo_producto ? <Logo src={marca.logo_producto} alt="" clase="logo-prod" /> : <span className="logo"><Icono nombre="escalas" tam="1.5rem" /></span>}
      <span className="nombre-producto">{marca.nombre_producto || MARCA_POR_DEFECTO.nombre_producto}</span>
    </div>
  );
}

/** Logo de «Acerca de» al pie de Ajustes; sin logo configurado no aparece nada. */
export function LogoPie({ marca }: { marca: MarcaOut }) {
  return <Logo src={marca.logo_pie} alt={altOrg(marca)} clase="logo-pie" />;
}
