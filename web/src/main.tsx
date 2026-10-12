import "./estilos.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { cargadorWeb } from "./cargador";
import { crearSinConexion } from "./sinConexion";

const raiz = document.getElementById("raiz");
if (raiz === null) {
  throw new Error("Falta el elemento #raiz en index.html");
}

// El service worker solo existe en contextos seguros (HTTPS o localhost): por la
// red local (http://192.168…) no lo hay, y la web funciona igual sin guardar nada.
// Tampoco se registra en desarrollo ni con el service worker de emergencia.
const contenedor = __MODO_SW__ === "normal" && "serviceWorker" in navigator
  // eslint-disable-next-line no-restricted-properties -- se acaba de comprobar que existe
  ? navigator.serviceWorker
  : undefined;
const sinConexion = crearSinConexion(contenedor, {
  url: `${import.meta.env.BASE_URL}sw.js`,
  recargar: () => {
    window.location.reload();
  },
  documento: document,
});

createRoot(raiz).render(
  <StrictMode>
    <App cargador={cargadorWeb} sinConexion={sinConexion} />
  </StrictMode>,
);
