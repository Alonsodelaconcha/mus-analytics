// Genera los iconos de la web (public/iconos) a partir del dibujo de abajo, con
// Edge sin ventana (scripts/edge.mjs). Los PNG se guardan en git: solo hay que
// volver a ejecutarlo si cambia el dibujo.
//
//   npm run iconos
//
// Diseño propio: dos naipes lisos sobre el verde de la web, y un 31, la mejor
// jugada del juego. No usa dibujos de ninguna baraja.

import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { abrirEdge } from "./edge.mjs";

const VERDE = "#1f6f43";
const VERDE_OSCURO = "#17573a";
const NAIPE = "#fbf8f1";
const NAIPE_ATRAS = "#dfd8c6";

/**
 * El dibujo, en un lienzo de 512. `escala` encoge los naipes (los iconos
 * "maskable" de Android se recortan en círculo: lo importante tiene que caber
 * en el 80 % central) y `radio` redondea el fondo (0 = a sangre, para el
 * iPhone y Android, que recortan ellos).
 */
function dibujo({ escala, radio }) {
  const naipe = (relleno) => `<rect x="-88" y="-132" width="176" height="264" rx="22" fill="${relleno}"/>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="fondo" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${VERDE}"/><stop offset="1" stop-color="${VERDE_OSCURO}"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="${String(radio)}" fill="url(#fondo)"/>
  <g transform="translate(256 258) scale(${String(escala)})">
    <g transform="translate(-52 6) rotate(-14)">${naipe(NAIPE_ATRAS)}</g>
    <g transform="translate(38 4) rotate(8)">
      <g transform="translate(5 7)" opacity="0.22">${naipe("#000")}</g>
      ${naipe(NAIPE)}
      <rect x="-72" y="-116" width="144" height="232" rx="12" fill="none" stroke="${VERDE}" stroke-opacity="0.3" stroke-width="5"/>
      <text x="0" y="40" text-anchor="middle" font-family="'Segoe UI', system-ui, sans-serif" font-weight="800"
        font-size="112" letter-spacing="-4" fill="${VERDE}">31</text>
    </g>
  </g>
</svg>`;
}

const ICONOS = [
  { fichero: "icono-512.png", lado: 512, escala: 1.28, radio: 112 },
  { fichero: "icono-192.png", lado: 192, escala: 1.28, radio: 112 },
  { fichero: "icono-maskable-512.png", lado: 512, escala: 1.02, radio: 0 },
  { fichero: "apple-touch-icon.png", lado: 180, escala: 1.28, radio: 0 },
  { fichero: "favicon-32.png", lado: 32, escala: 1.4, radio: 112 },
];

const salida = resolve("public/iconos");
mkdirSync(salida, { recursive: true });

const edge = await abrirEdge({ nombre: "iconos", puerto: 9334 });
try {
  // Fondo transparente: las esquinas redondeadas no llevan color.
  await edge.cdp("Emulation.setDefaultBackgroundColorOverride", { color: { r: 0, g: 0, b: 0, a: 0 } });
  for (const { fichero, lado, escala, radio } of ICONOS) {
    await edge.cdp("Emulation.setDeviceMetricsOverride", { width: lado, height: lado, deviceScaleFactor: 1, mobile: false });
    const pagina = `<html><body style="margin:0;overflow:hidden">${dibujo({ escala, radio })}</body></html>`;
    await edge.cdp("Page.navigate", { url: `data:text/html;charset=utf-8,${encodeURIComponent(pagina)}` });
    await edge.evaluar("await document.fonts.ready; await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));");
    const { data } = await edge.cdp("Page.captureScreenshot", {
      format: "png", clip: { x: 0, y: 0, width: lado, height: lado, scale: 1 },
    });
    writeFileSync(resolve(salida, fichero), Buffer.from(data, "base64"));
    console.log(`✓ ${fichero} (${String(lado)} × ${String(lado)})`);
  }
} finally {
  await edge.cerrar();
}
