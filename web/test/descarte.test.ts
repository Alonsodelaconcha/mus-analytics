import { describe, expect, it } from "vitest";

import { leerMano, texto } from "../src/nucleo/cartas";
import {
  distribucionTrasDescarte,
  esperanza,
  numeradoresPorJugada,
  opcionesDescarte,
  resumenDistribucion,
} from "../src/nucleo/descarte";
import { tabla } from "../src/nucleo/tablas";
import { type ReferenciaDescartes, leerReferencia } from "./ayuda";

const REFERENCIA = leerReferencia("descartes.json") as ReferenciaDescartes;
const t = tabla();

describe("opciones de descarte", () => {
  it("son las de Python, en el mismo orden canónico (3 546 en total)", () => {
    let total = 0;
    REFERENCIA.manos.forEach((fila, i) => {
      const mano = t.manos[i] ?? [];
      expect(texto(mano)).toBe(fila.texto);
      const opciones = opcionesDescarte(mano);
      expect(opciones.map((o) => [o.codigo, o.nDescartes])).toEqual(
        fila.opciones.map((f) => [f[0], f[1]]),
      );
      total += opciones.length;
    });
    expect(total).toBe(3546);
  });

  it("descartadas + conservadas = la mano", () => {
    const mano = leerMano("R R C 5");
    const opciones = opcionesDescarte(mano);
    expect(opciones).toHaveLength(11);
    for (const o of opciones) {
      expect(o.conservadas.map((c, r) => c + (o.descartadas[r] ?? 0))).toEqual(mano);
    }
    expect(texto(opciones[0]?.conservadas ?? [])).toBe("R R C"); // tirar una, quedándose lo más alto
  });
});

describe("distribución exacta de la mano final", () => {
  it("coincide con Python en las 3 546 opciones (numeradores enteros y huellas)", () => {
    const [pesos1 = [], pesos2 = []] = REFERENCIA.pesos_huella;
    REFERENCIA.manos.forEach((fila, i) => {
      const mano = t.manos[i] ?? [];
      opcionesDescarte(mano).forEach((opcion, j) => {
        const esperado = fila.opciones[j] ?? [];
        const d = distribucionTrasDescarte(mano, opcion);
        const n = numeradoresPorJugada(d);
        // Suma entera de numerador · peso: exacta en doble precisión (< 2^53).
        const huella = (pesos: number[]) =>
          [...d.numeradores].reduce((total, [k, x]) => total + x * (pesos[k] ?? 0), 0);
        const [huella1, huella2] = [huella(pesos1), huella(pesos2)];
        expect([d.denominador, n.pares, n.medias, n.duples, n.juego, n.juego31, huella1, huella2],
          `${fila.texto}, opción ${j}`).toEqual(esperado.slice(2));
      });
    });
  });

  it("coincide mano final a mano final en la muestra completa", () => {
    expect(REFERENCIA.distribuciones.length).toBeGreaterThan(200);
    for (const caso of REFERENCIA.distribuciones) {
      const mano = leerMano(caso.mano);
      const opcion = opcionesDescarte(mano).find((o) => o.codigo === caso.conservadas);
      expect(opcion).toBeDefined();
      if (opcion === undefined) continue;
      const d = distribucionTrasDescarte(mano, opcion);
      expect([...d.numeradores].sort((a, b) => a[0] - b[0])).toEqual(caso.numeradores);
    }
  });

  it("la esperanza pondera cada mano final por su probabilidad", () => {
    const mano = leerMano("A A 4 5");
    const opcion = opcionesDescarte(mano).find((o) => texto(o.conservadas) === "A A");
    if (opcion === undefined) throw new Error("falta la opción");
    const d = distribucionTrasDescarte(mano, opcion);
    expect(esperanza(d, () => 1)).toBeCloseTo(1, 12);
    expect(esperanza(d, (k) => (t.jugadaPares[k] ?? 0) > 0 ? 1 : 0))
      .toBeCloseTo(resumenDistribucion(d).pares, 12);
  });

  it("R C 5 4 tirando el 4: P(juego) = 22/36 (calculado a mano)", () => {
    const mano = leerMano("R C 5 4");
    const opcion = opcionesDescarte(mano).find((o) => texto(o.conservadas) === "R C 5");
    expect(opcion).toBeDefined();
    if (opcion === undefined) return;
    // R C 5 suma 25: hace falta un 6, un 7 o una figura de las 36 que no veo: 4 + 4 + 4 + 3 + 7 = 22.
    expect(resumenDistribucion(distribucionTrasDescarte(mano, opcion)).juego).toBeCloseTo(22 / 36, 12);
  });
});
