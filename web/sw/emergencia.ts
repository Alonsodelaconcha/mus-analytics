/**
 * Salida de emergencia: un *service worker* que se quita a sí mismo.
 *
 * Si se publica un `sw.js` con un fallo, los móviles que ya lo tienen siguen
 * usándolo aunque se corrija la web, porque es él quien sirve la página. Lo
 * único que el navegador pide siempre a la red, sin pasar por el *service
 * worker*, es el propio `sw.js`. Por eso la salida es publicar ESTE fichero en
 * esa misma dirección (`npm run build:emergencia`): toma el mando enseguida,
 * borra las cachés de la web, se desregistra y recarga las páginas abiertas,
 * que vuelven a salir de la red. Ver docs/decisiones.md.
 *
 * No tiene `fetch`: mientras esté activo, todo va a la red.
 */

/// <reference lib="webworker" />

import { PREFIJO_CACHE } from "./logica";

declare const self: ServiceWorkerGlobalScope;

self.addEventListener("install", (evento) => {
  evento.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil((async () => {
    for (const nombre of await self.caches.keys()) {
      if (nombre.startsWith(PREFIJO_CACHE)) await self.caches.delete(nombre);
    }
    await self.registration.unregister();
    for (const ventana of await self.clients.matchAll({ type: "window" })) {
      // Puede fallar si la página ya se está recargando por su cuenta: da igual.
      await ventana.navigate(ventana.url).catch(() => null);
    }
  })());
});
