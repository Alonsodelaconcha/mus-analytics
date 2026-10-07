import { describe, expect, it } from "vitest";

import {
  ErrorLectura,
  codigo,
  combinaciones,
  desdeCodigo,
  enumerarManos,
  leerMano,
  texto,
} from "../src/nucleo/cartas";
import { tabla } from "../src/nucleo/tablas";
import { type ReferenciaEvaluacion, leerReferencia } from "./ayuda";

const REFERENCIA = leerReferencia("evaluacion.json") as ReferenciaEvaluacion;

describe("manos", () => {
  it("son las 330 de Python, en el mismo orden y con el mismo código", () => {
    const manos = enumerarManos();
    expect(manos).toHaveLength(330);
    expect(manos.map(texto)).toEqual(REFERENCIA.manos.map((f) => f[0]));
    expect(manos).toEqual(REFERENCIA.manos.map((f) => f[1]));
    expect(manos.map(codigo)).toEqual(REFERENCIA.manos.map((f) => f[2]));
  });

  it("tienen las mismas combinaciones físicas, que suman C(40, 4)", () => {
    const t = tabla();
    expect(t.combinaciones).toEqual(REFERENCIA.manos.map((f) => f[3]));
    expect(t.combinaciones.reduce((a, b) => a + b, 0)).toBe(combinaciones(40, 4));
    expect(combinaciones(40, 4)).toBe(91_390);
  });

  it("el código se puede deshacer", () => {
    for (const mano of enumerarManos()) {
      expect(desdeCodigo(codigo(mano))).toEqual(mano);
    }
  });
});

describe("lectura de manos", () => {
  it.each(REFERENCIA.lectura)("«$entrada» se lee igual que en Python", (caso) => {
    if ("error" in caso) {
      expect(() => leerMano(caso.entrada)).toThrow(ErrorLectura);
    } else {
      expect(texto(leerMano(caso.entrada))).toBe(caso.mano);
    }
  });

  it("los treses son reyes y los doses, ases", () => {
    expect(texto(leerMano("3 3 2 2"))).toBe("R R A A");
  });

  it("explica el error", () => {
    expect(() => leerMano("R R X 5")).toThrow(/Carta desconocida: «X»/);
    expect(() => leerMano("R R C")).toThrow(/Se esperaban 4 cartas y hay 3/);
  });
});

describe("combinaciones", () => {
  it("son exactas", () => {
    expect([combinaciones(36, 4), combinaciones(8, 2), combinaciones(4, 5), combinaciones(5, 0)])
      .toEqual([58_905, 28, 0, 1]);
  });
});
