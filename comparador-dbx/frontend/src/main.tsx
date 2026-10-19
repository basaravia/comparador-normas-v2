import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { Proveedor } from "./store";
import "./estilos.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><Proveedor><App /></Proveedor></StrictMode>,
);
