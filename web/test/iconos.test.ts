/**
 * Los iconos de la web instalable. El del iPhone tiene sus reglas: 180 × 180,
 * sin transparencia (iOS la rellena de negro) y con el fondo hasta el borde
 * (las esquinas las redondea iOS). Se regeneran con `npm run iconos`.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const PUBLICO = join(process.cwd(), "public");

/** Cabecera de un PNG: tamaño y si lleva canal de transparencia (tipos de color 4 y 6). */
function cabecera(ruta: string) {
  const png = readFileSync(join(PUBLICO, ruta));
  expect(png.subarray(1, 4).toString("latin1")).toBe("PNG");
  expect(png.subarray(12, 16).toString("latin1")).toBe("IHDR");
  const tipoColor = png.readUInt8(25);
  return {
    ancho: png.readUInt32BE(16),
    alto: png.readUInt32BE(20),
    conTransparencia: tipoColor === 4 || tipoColor === 6 || png.includes("tRNS", 0, "latin1"),
  };
}

describe("iconos", () => {
  it("el del iPhone mide 180 × 180 y no tiene transparencia", () => {
    expect(cabecera("iconos/apple-touch-icon.png")).toEqual({ ancho: 180, alto: 180, conTransparencia: false });
  });

  it("el manifiesto apunta a iconos que existen, con el tamaño que dice", () => {
    const manifiesto = JSON.parse(readFileSync(join(PUBLICO, "manifest.webmanifest"), "utf8")) as {
      icons: { src: string; sizes: string; purpose: string }[];
    };
    expect(manifiesto.icons.map((i) => i.sizes).sort()).toEqual(["192x192", "512x512", "512x512"]);
    for (const icono of manifiesto.icons) {
      const { ancho, alto, conTransparencia } = cabecera(icono.src);
      expect(`${String(ancho)}x${String(alto)}`).toBe(icono.sizes);
      // El "maskable" lo recorta Android con su propia forma: el fondo tiene que llegar al borde.
      if (icono.purpose === "maskable") expect(conTransparencia).toBe(false);
    }
  });
});
