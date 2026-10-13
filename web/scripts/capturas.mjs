// Capturas de la web a tamaño de móvil (iPhone 15: 393 × 852), con Edge sin
// ventana (scripts/edge.mjs). Sin dependencias: solo Node (>= 22) y Edge.
//
// Uso (desde web/, con la web servida: npm run dev, npm run movil-final...):
//   npm run capturas                                    # escenas por defecto, http://localhost:5173/
//   npm run capturas -- --url http://192.168.1.37:4173/ # por la IP de red
//   npm run capturas -- --instalada --tema ambos        # como instalada en el iPhone, con sus zonas seguras
//   npm run capturas -- --escenas mis-escenas.json --salida ../resultados/otra --tema oscuro
//
// Cada escena es { "nombre", "pasos" }: "pasos" es código que se ejecuta en la
// página con las ayudas de edge.mjs (cartas("R C 5 4"), posicion("Mano"),
// pestana("Se ha cortado"), toca("Dos reyes")...). Además de las capturas,
// comprueba que la página no da errores en la consola y dice si es un contexto
// seguro (por la IP de red no lo es: sin crypto.subtle ni service worker).
//
// --instalada simula las zonas seguras del iPhone 15 con la web a pantalla
// completa (59 px arriba por la isla, 34 px abajo por la barra de inicio), las
// dibuja encima y comprueba que ningún botón ni texto queda dentro de ellas.
// Sale con código 1 si algo falla.

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { parseArgs } from "node:util";

import { AYUDAS, abrirEdge } from "./edge.mjs";

const { values: opciones } = parseArgs({
  options: {
    url: { type: "string", default: "http://localhost:5173/" },
    salida: { type: "string", default: "../resultados/capturas" },
    escenas: { type: "string" },
    tema: { type: "string", default: "claro" }, // claro, oscuro o ambos
    ancho: { type: "string", default: "393" },
    alto: { type: "string", default: "852" },
    instalada: { type: "boolean", default: false },
  },
});

/** Las tres pestañas con las manos de las maquetas, el detalle de un lance y el teclado a medio meter. */
const CORTADO = 'await cartas("R C 5 4"); await posicion("Mano"); await pestana("Se ha cortado"); await toca("Dos reyes");';
const ESCENAS_POR_DEFECTO = [
  { nombre: "1-mus-o-corto", pasos: 'await cartas("R C 5 4"); await posicion("Mano");' },
  { nombre: "2-se-ha-cortado", pasos: CORTADO },
  {
    nombre: "3-ha-habido-mus",
    pasos: 'await posicion("Postre"); await pestana("Ha habido mus"); await cartas("R R C S");',
  },
  { nombre: "4-detalle-de-un-lance", pasos: `${CORTADO} await toca("Grande");` },
  { nombre: "5-teclado", pasos: 'await posicion("Tercero"); await cartas("R 7");' },
];

/** Zonas seguras del iPhone 15 en vertical, con la web a pantalla completa. */
const ZONAS = { top: 59, bottom: 34, left: 0, right: 0 };

/**
 * Dibuja la isla, la barra de inicio y el límite de cada zona segura, y
 * devuelve los botones, enlaces y textos visibles que se meten en ellas.
 */
const COMPROBAR_ZONAS = `
  const alto = window.innerHeight;
  const dentro = [];
  for (const el of document.querySelectorAll("button, a, [role=tab], h1, h2, p, span, img")) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0 || r.bottom < 0 || r.top > alto) continue;
    // Solo cuenta lo que está fijo en la pantalla o al principio de la página sin desplazar.
    if (r.top < ${String(ZONAS.top)} - 0.5 && window.scrollY === 0) dentro.push("arriba: " + (el.innerText ?? el.tagName).trim().slice(0, 40));
    const fijo = el.closest(".pie, .velo") !== null;
    if (fijo && r.bottom > alto - ${String(ZONAS.bottom)} + 0.5) dentro.push("abajo: " + (el.innerText ?? el.tagName).trim().slice(0, 40));
  }
  const capa = document.createElement("div");
  capa.style.cssText = "position:fixed;inset:0;z-index:99999;pointer-events:none";
  capa.innerHTML = \`
    <div style="position:absolute;left:0;right:0;top:${String(ZONAS.top)}px;border-top:1px dashed rgb(220 0 80 / 70%)"></div>
    <div style="position:absolute;left:0;right:0;bottom:${String(ZONAS.bottom)}px;border-top:1px dashed rgb(220 0 80 / 70%)"></div>
    <div style="position:absolute;left:50%;top:11px;width:126px;height:37px;margin-left:-63px;border-radius:19px;background:#000"></div>
    <div style="position:absolute;left:50%;bottom:8px;width:139px;height:5px;margin-left:-69.5px;border-radius:3px;background:#000;opacity:.85"></div>\`;
  document.body.append(capa);
  return dentro;
`;

const escenas = opciones.escenas ? JSON.parse(readFileSync(opciones.escenas, "utf8")) : ESCENAS_POR_DEFECTO;
const temas = opciones.tema === "ambos" ? ["claro", "oscuro"] : [opciones.tema];
const salida = resolve(opciones.salida);
mkdirSync(salida, { recursive: true });

let fallos = 0;
const edge = await abrirEdge();
try {
  // Empezar de cero: sin el service worker ni las cachés de una ejecución anterior,
  // que servirían una versión vieja de la web.
  await edge.cdp("Storage.clearDataForOrigin", { origin: new URL(opciones.url).origin, storageTypes: "all" });
  await edge.cdp("Network.clearBrowserCache");
  await edge.cdp("Emulation.setDeviceMetricsOverride", {
    width: Number(opciones.ancho), height: Number(opciones.alto), deviceScaleFactor: 2, mobile: true,
  });
  if (opciones.instalada) {
    await edge.cdp("Emulation.setSafeAreaInsetsOverride", { insets: ZONAS });
  }
  for (const tema of temas) {
    await edge.cdp("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-color-scheme", value: tema === "oscuro" ? "dark" : "light" }],
    });
    for (const escena of escenas) {
      const nombre = [escena.nombre, ...(opciones.instalada ? ["instalada"] : []), ...(temas.length > 1 ? [tema] : [])].join("-");
      edge.errores.length = 0;
      // Cada escena empieza sin nada recordado (el modo, el tipo de mesa, el progreso del
      // entrenador). Se borra antes de cargar la página: borrarlo desde dentro llega tarde
      // si la web ya ha leído sus preferencias.
      await edge.cdp("Storage.clearDataForOrigin", { origin: new URL(opciones.url).origin, storageTypes: "local_storage" });
      await edge.cdp("Page.navigate", { url: opciones.url });
      let datos;
      try {
        datos = await edge.evaluar(`
          ${AYUDAS}
          try { localStorage.clear(); } catch {}
          await cargada();
          ${escena.pasos ?? ""};
          await calculada();
          await espera(300);
          const zonas = ${opciones.instalada ? `await (async () => { ${COMPROBAR_ZONAS} })()` : "[]"};
          return {
            seguro: window.isSecureContext,
            subtle: typeof crypto !== "undefined" && crypto.subtle !== undefined,
            arriba: getComputedStyle(document.querySelector(".app")).paddingTop,
            zonas,
          };`);
      } catch (error) {
        fallos++;
        console.error(`✗ ${nombre}: ${error.message}`);
        continue;
      }
      const { data } = await edge.cdp("Page.captureScreenshot", { format: "png" });
      writeFileSync(join(salida, `${nombre}.png`), Buffer.from(data, "base64"));
      console.log(`✓ ${nombre}.png  (contexto ${datos.seguro ? "seguro" : "NO seguro"}; crypto.subtle ${datos.subtle ? "sí" : "no"})`);
      if (opciones.instalada && datos.arriba !== `${String(ZONAS.top)}px`) {
        fallos++;
        console.error(`  la zona segura de arriba no se respeta: el margen es ${datos.arriba}`);
      }
      if (datos.zonas.length > 0) {
        fallos++;
        console.error(`  dentro de una zona segura:\n  - ${datos.zonas.join("\n  - ")}`);
      }
      if (edge.errores.length > 0) {
        fallos++;
        console.error(`  errores en la consola:\n  - ${edge.errores.join("\n  - ")}`);
      }
    }
  }
  console.log(`\nCapturas en ${salida}`);
} finally {
  await edge.cerrar();
}
process.exitCode = fallos > 0 ? 1 : 0;
