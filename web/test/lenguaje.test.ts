import { describe, expect, it } from "vitest";

import { leerMano } from "../src/nucleo/cartas";
import { opcionesDescarte } from "../src/nucleo/descarte";
import {
  conSigno,
  describirMano,
  describirPares,
  frecuencia,
  frecuenciaCorta,
  porcentaje,
  tantosPorMano,
  textoOpcion,
  textoSinConexion,
  textoVersion,
} from "../src/vista/lenguaje";

// Intl en español usa un espacio duro antes del %; se normaliza para comparar.
const normal = (s: string) => s.replace(/\s/g, " ");

describe("cifras", () => {
  it("porcentajes", () => {
    expect([0, 0.003, 0.62, 0.996, 1].map((p) => normal(porcentaje(p))))
      .toEqual(["0 %", "<1 %", "62 %", ">99 %", "100 %"]);
  });

  it("frecuencias en palabras", () => {
    expect([0, 0.004, 0.07, 0.1, 0.34, 0.66, 0.94, 0.96, 1].map(frecuencia)).toEqual([
      "nunca",
      "casi nunca",
      "1 de cada 14 veces",
      "1 de cada 10 veces",
      "unas 3 de cada 10 veces",
      "unas 7 de cada 10 veces",
      "unas 9 de cada 10 veces",
      "casi siempre",
      "siempre",
    ]);
  });

  it("frecuencias en corto, con los mismos cortes", () => {
    expect([0, 0.004, 0.07, 0.1, 0.34, 0.66, 0.94, 0.96, 1].map(frecuenciaCorta)).toEqual([
      "nunca", "casi nunca", "1 de 14", "1 de 10", "3 de 10", "7 de 10", "9 de 10", "casi siempre", "siempre",
    ]);
  });

  it("tantos dichos como los notaría un jugador", () => {
    expect(tantosPorMano(0.283)).toBe("unos 3 tantos cada 10 manos");
    expect(tantosPorMano(-0.07)).toBe("unos 7 tantos cada 100 manos");
    expect(tantosPorMano(0.1)).toBe("1 tanto cada 10 manos");
    expect(tantosPorMano(1)).toBe("1 tanto por mano");
    expect(tantosPorMano(2.0)).toBe("unos 2 tantos por mano");
    expect(tantosPorMano(-1.14)).toBe("unos 1,1 tantos por mano");
    expect(tantosPorMano(0.004)).toBe("menos de 1 tanto cada 100 manos");
    expect(tantosPorMano(0.283, true)).toBe("unos 3 tantos más cada 10 manos");
    expect(tantosPorMano(0.004, true)).toBe("menos de 1 tanto más cada 100 manos");
  });

  it("signo", () => {
    expect([conSigno(0.07), conSigno(-0.07), conSigno(0), conSigno(-0.001)])
      .toEqual(["+0,07", "−0,07", "0,00", "0,00"]);
  });
});

describe("jugadas", () => {
  it.each([
    ["R R C 5", "Par de reyes"],
    ["7 7 7 S", "Medias de sietes"],
    ["R R A A", "Duples de reyes y ases"],
    ["5 5 5 5", "Duples de cuatro cincos"],
    ["R C 5 4", "Sin pares"],
  ])("%s: %s", (mano, texto) => {
    expect(describirPares(leerMano(mano))).toBe(texto);
  });

  it("la mano en dos datos: pares y juego o punto", () => {
    expect(describirMano(leerMano("R C S A"))).toEqual(["Sin pares", "31 de juego"]);
    expect(describirMano(leerMano("R R C S"))).toEqual(["Par de reyes", "40 de juego"]);
    expect(describirMano(leerMano("R C 5 4"))).toEqual(["Sin pares", "29 al punto"]);
  });
});

describe("descartes en palabras", () => {
  const texto = (mano: string, quedo: string) => {
    const conteos = leerMano(mano);
    const opcion = opcionesDescarte(conteos).find((o) => textoOpcion(o).quedo === quedo);
    if (opcion === undefined) throw new Error(`no hay opción ${quedo}`);
    return textoOpcion(opcion);
  };

  it("lo que se queda y lo que se tira, con cartas iguales agrupadas", () => {
    expect(texto("R C 5 4", "R C")).toMatchObject({
      titulo: "Quédate con R C",
      detalle: "Pides 2: tiras el cinco y el cuatro",
    });
    expect(texto("R 4 4 S", "R").detalle).toBe("Pides 3: tiras la sota y los dos cuatros");
    expect(texto("A A 4 5", "")).toMatchObject({ titulo: "Tíralas todas", detalle: "Pides 4: tiras las cuatro" });
  });
});

describe("versión y modo sin conexión", () => {
  it("una frase para cada estado", () => {
    expect(textoSinConexion({ tipo: "lista", version: "abc1234def567890" })).toBe("Lista para usar sin conexión.");
    expect(textoSinConexion({ tipo: "nueva", version: null })).toBe("Lista para usar sin conexión. Hay una versión nueva.");
    expect(textoSinConexion({ tipo: "preparando" })).toBe("Guardando la web para usarla sin conexión…");
    expect(textoSinConexion({ tipo: "error" })).toMatch(/^No se ha podido guardar/);
    expect(textoSinConexion({ tipo: "no-disponible" })).toBe("Aquí no se puede usar sin conexión.");
  });

  it("la versión, el identificador de lo guardado (si lo hay) y la fecha de los datos", () => {
    expect(textoVersion("0.1.0", { tipo: "lista", version: "abc1234def567890" }, "2026-10-07"))
      .toBe("Versión 0.1.0 (abc1234) · datos del 2026-10-07");
    expect(textoVersion("0.1.0", { tipo: "nueva", version: "abc1234def567890" }, "2026-10-07"))
      .toBe("Versión 0.1.0 (abc1234) · datos del 2026-10-07");
    expect(textoVersion("0.1.0", { tipo: "nueva", version: null }, "2026-10-07")).toBe("Versión 0.1.0 · datos del 2026-10-07");
    expect(textoVersion("0.1.0", { tipo: "preparando" }, null)).toBe("Versión 0.1.0");
  });
});
