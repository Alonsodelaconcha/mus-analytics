import "./estilos.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { cargadorWeb } from "./cargador";

const raiz = document.getElementById("raiz");
if (raiz === null) {
  throw new Error("Falta el elemento #raiz en index.html");
}
createRoot(raiz).render(
  <StrictMode>
    <App cargador={cargadorWeb} />
  </StrictMode>,
);
