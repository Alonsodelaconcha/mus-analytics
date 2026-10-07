import { describe, expect, it } from "vitest";

import { leerMano } from "../src/nucleo/cartas";
import {
  LANCES,
  Pares,
  clave,
  compararClaves,
  jugadaPares,
  resolverMano,
} from "../src/nucleo/evaluacion";
import { tabla } from "../src/nucleo/tablas";
import {
  type ReferenciaEvaluacion,
  type ReferenciaLances,
  leerReferencia,
} from "./ayuda";

const EVALUACION = leerReferencia("evaluacion.json") as ReferenciaEvaluacion;
const LANCES_REF = leerReferencia("lances.json") as ReferenciaLances;

describe("evaluación de las 330 manos", () => {
  const t = tabla();

  it("suma, pares y tantos coinciden con Python", () => {
    expect(t.suma).toEqual(EVALUACION.manos.map((f) => f[4]));
    expect(t.jugadaPares).toEqual(EVALUACION.manos.map((f) => f[5]));
    expect(t.puntosPares).toEqual(EVALUACION.manos.map((f) => f[6]));
    expect(t.puntosJuego).toEqual(EVALUACION.manos.map((f) => f[7]));
  });

  it.each(LANCES.map((l, i) => [l, i] as const))("la fuerza en %s coincide con Python", (lance, i) => {
    expect(t.fuerza[lance]).toEqual(EVALUACION.manos.map((f) => f[8][i]));
  });
});

describe("resolución de lances", () => {
  it(`da el mismo ganador y tantos que Python en ${LANCES_REF.repartos.length} repartos`, () => {
    for (const [manos, esperado] of LANCES_REF.repartos) {
      const resultado = resolverMano(manos.map(leerMano)).map((r) => [r.ganador ?? 0, r.tantos]);
      expect(resultado, manos.join(" | ")).toEqual(esperado);
    }
  });

  it("casos límite de los pares", () => {
    const pares = (m: string) => clave("pares", leerMano(m));
    expect(compararClaves(pares("R R A A") ?? [], pares("C C C C") ?? [])).toBeGreaterThan(0);
    expect(compararClaves(pares("R R 4 4") ?? [], pares("5 5 5 5") ?? [])).toBeGreaterThan(0);
    expect(compararClaves(pares("R R R R") ?? [], pares("R R C C") ?? [])).toBeGreaterThan(0);
    expect(jugadaPares(leerMano("7 7 7 7"))).toBe(Pares.DUPLES);
    expect(pares("R C 5 4")).toBeNull();
  });

  it("el orden del juego: 31 > 32 > 40 > 37 > 33", () => {
    const juego = (m: string) => clave("juego", leerMano(m)) ?? [];
    const enOrden = ["R C S A", "R C 6 6", "R R C S", "R C S 7", "R C 7 6"]; // 31, 32, 40, 37, 33
    for (let i = 1; i < enOrden.length; i++) {
      expect(compararClaves(juego(enOrden[i - 1] ?? ""), juego(enOrden[i] ?? ""))).toBeGreaterThan(0);
    }
  });
});
