/**
 * *Service worker* de Mus Analytics: guarda la web entera para usarla sin
 * conexión. Aquí solo se conectan los eventos del navegador con `logica.ts`.
 *
 * Se publica siempre en la misma dirección (`sw.js`, sin huella en el nombre):
 * el navegador lo compara byte a byte con el que tiene, y como lleva dentro la
 * lista de ficheros con sus huellas (`__PRECARGA__`), cualquier cambio en el
 * código o en los datos lo convierte en una versión nueva.
 *
 * Ciclo de una versión nueva:
 * 1. `install`: se descarga entera a su caché. Si algo falla, se descarta.
 * 2. Espera: la página sigue con la versión anterior, intacta, y avisa de que
 *    hay una nueva. No se cambia a mitad de una mano.
 * 3. `activate`: cuando la página lo pide («Actualizar») o cuando no queda
 *    ninguna abierta. Se borran las cachés anteriores y la página se recarga.
 */

/// <reference lib="webworker" />

import { type Entorno, type Precarga, activar, estado, instalar, rutaDe, servir } from "./logica";

declare const self: ServiceWorkerGlobalScope;
declare const __PRECARGA__: Precarga;

const PRECARGA = __PRECARGA__;

const entorno: Entorno = {
  base: self.registration.scope,
  caches: self.caches,
  fetch: (url, opciones) => fetch(url, opciones),
  sha256: async (contenido) => {
    const resumen = await crypto.subtle.digest("SHA-256", contenido);
    return Array.from(new Uint8Array(resumen), (b) => b.toString(16).padStart(2, "0")).join("");
  },
};

self.addEventListener("install", (evento) => {
  evento.waitUntil(instalar(PRECARGA, entorno));
});

self.addEventListener("activate", (evento) => {
  // `claim`: la primera vez, la página que ya está abierta pasa a servirse de la caché sin recargar.
  evento.waitUntil(activar(PRECARGA, entorno).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (evento) => {
  const ruta = rutaDe(PRECARGA, entorno.base, evento.request.method, evento.request.url);
  if (ruta === null) return;
  evento.respondWith(servir(PRECARGA, entorno, ruta).then((guardado) => guardado ?? fetch(evento.request)));
});

self.addEventListener("message", (evento) => {
  const tipo = (evento.data as { tipo?: unknown } | null)?.tipo;
  if (tipo === "activar") {
    // La página ha pedido pasar a esta versión.
    evento.waitUntil(self.skipWaiting());
  } else if (tipo === "estado") {
    const puerto = evento.ports[0];
    if (puerto !== undefined) {
      evento.waitUntil(estado(PRECARGA, entorno).then((e) => { puerto.postMessage(e); }));
    }
  }
});
