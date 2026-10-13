/**
 * El núcleo del entrenador frente a Python: la valoración de las 3 960
 * decisiones y de todos los descartes, y el peso de cada situación, tienen que
 * ser exactamente los de `mus.entrenador` (web/test/referencia/entrenador.json).
 */

import { describe, expect, it } from "vitest";

import {
  EJERCICIOS,
  MODOS,
  UMBRAL_AJUSTADA,
  decisionesPorMano,
  numeroDeSituacion,
  pesos,
  situacionDe,
  sortear,
} from "../src/entrenador/situaciones";
import { MILESIMAS, valorarCorte, valorarDescartes } from "../src/entrenador/valoracion";
import { leerMano } from "../src/nucleo/cartas";
import { Datos, decisionDe, opcionesDe } from "../src/nucleo/datos";
import { opcionesDescarte } from "../src/nucleo/descarte";
import { indiceMano, tabla } from "../src/nucleo/tablas";
import { UMBRAL_CLARA, UMBRAL_DESCARTE, UMBRAL_IGUAL } from "../src/vista/vista";
import { type ReferenciaEntrenador, azarConSemilla, leerDato, leerReferencia } from "./ayuda";

const ref = leerReferencia("entrenador.json") as ReferenciaEntrenador;
const datos = await Datos.cargar((ruta) => Promise.resolve(leerDato(ruta)));
const { manifiesto } = datos;
const { escalas } = manifiesto;
const MESAS = manifiesto.mesas.map((m) => m.id);
const N_MANOS = 330;
const N_OPCIONES = manifiesto.descartes.conservadas.length;
const POSICIONES = [1, 2, 3, 4];

const CODIGO_VEREDICTO = { mus: 1, corta: -1, igual: 0 } as const;
const CODIGO_INTENSIDAD = { clara: 2, "por-poco": 1, igual: 0 } as const;

describe("la referencia y la web hablan de lo mismo", () => {
  it("los mismos umbrales, veredictos, modos y tipos de mesa", () => {
    expect(ref.umbrales).toEqual({
      igual: Math.round(UMBRAL_IGUAL * MILESIMAS),
      clara: Math.round(UMBRAL_CLARA * MILESIMAS),
      descarte: Math.round(UMBRAL_DESCARTE * MILESIMAS),
      ajustada: UMBRAL_AJUSTADA,
    });
    expect(ref.veredictos).toEqual({ "1": "mus", "-1": "corta", "0": "igual" });
    expect(ref.intensidades).toEqual({ "2": "clara", "1": "por-poco", "0": "igual" });
    expect(ref.modos).toEqual([...MODOS]);
    expect(Object.keys(ref.mesas)).toEqual(MESAS);
  });
});

describe.each(MESAS)("valoración frente a Python, sin tolerancia (mesa %s)", (id) => {
  const r = ref.mesas[id];
  if (r === undefined) throw new Error(`la referencia no tiene la mesa ${id}`);

  it("¿mus o corto?: veredicto, intensidad y tantos perdidos de las 1 320 situaciones", async () => {
    const mesa = await datos.mesa(id);
    const veredicto: number[] = [];
    const intensidad: number[] = [];
    const perdidosMus: number[] = [];
    const perdidosCorto: number[] = [];
    for (let h = 0; h < N_MANOS; h++) {
      for (const p of POSICIONES) {
        const d = decisionDe(mesa, escalas, h, p);
        if (d === null) throw new Error("falta una decisión");
        const v = valorarCorte(d);
        veredicto.push(CODIGO_VEREDICTO[v.veredicto]);
        intensidad.push(CODIGO_INTENSIDAD[v.intensidad]);
        perdidosMus.push(v.perdidos.mus);
        perdidosCorto.push(v.perdidos.corta);
      }
    }
    expect(veredicto).toEqual(r.corte.veredicto);
    expect(intensidad).toEqual(r.corte.intensidad);
    expect(perdidosMus).toEqual(r.corte.perdidos_mus);
    expect(perdidosCorto).toEqual(r.corte.perdidos_corto);
  });

  it("¿qué tiras?: tantos perdidos, opciones que valen y la mejor, de los 14 184 descartes", async () => {
    const mesa = await datos.mesa(id);
    const perdidos = new Array<number>(4 * N_OPCIONES).fill(0);
    const vale = new Array<number>(4 * N_OPCIONES).fill(0);
    const mejor: number[] = [];
    for (let h = 0; h < N_MANOS; h++) {
      const mano = tabla().manos[h] ?? [];
      // Posición de cada opción en el orden canónico, que es el de los ficheros.
      const canonico = new Map(opcionesDescarte(mano).map((o, i) => [o.codigo, i]));
      for (const p of POSICIONES) {
        const valoradas = valorarDescartes(opcionesDe(mesa, manifiesto, mano, h, p));
        const base = (p - 1) * N_OPCIONES + (manifiesto.descartes.inicio[h] ?? 0);
        for (const o of valoradas) {
          const i = canonico.get(o.valor.opcion.codigo) ?? -1;
          perdidos[base + i] = o.perdidos;
          vale[base + i] = o.vale ? 1 : 0;
        }
        mejor.push(canonico.get(valoradas[0]?.valor.opcion.codigo ?? -1) ?? -1);
      }
    }
    expect(perdidos).toEqual(r.descarte.perdidos);
    expect(vale).toEqual(r.descarte.vale);
    expect(mejor).toEqual(r.descarte.mejor);
  });

  it("el peso de cada situación en cada modo, y cuántas decisiones hay por mano", async () => {
    const mesa = await datos.mesa(id);
    for (const ejercicio of EJERCICIOS) {
      for (const modo of MODOS) {
        expect(pesos(ejercicio, modo, mesa, manifiesto)).toEqual(r[ejercicio].pesos[modo]);
      }
      const [numerador, denominador] = r[ejercicio].decisiones_por_mano;
      expect(decisionesPorMano(ejercicio, pesos(ejercicio, "mesa", mesa, manifiesto), escalas))
        .toBe(numerador / denominador);
    }
  });
});

describe("situaciones como en la mesa", async () => {
  const normal = await datos.mesa("normal");
  const corte = pesos("corte", "mesa", normal, manifiesto);
  const descarte = pesos("descarte", "mesa", normal, manifiesto);
  const porPosicion = (ps: readonly number[]) =>
    POSICIONES.map((p) => ps.reduce((t, x, k) => t + (k % 4 === p - 1 ? x : 0), 0));

  it("de mano se habla siempre; cuanto más tarde, menos veces", () => {
    const [mano = 0, segundo = 0, tercero = 0, postre = 0] = porPosicion(corte);
    expect(mano).toBe(91_390 * escalas.probabilidad);
    expect(mano).toBeGreaterThan(segundo);
    expect(segundo).toBeGreaterThan(tercero);
    expect(tercero).toBeGreaterThan(postre);
    expect(postre).toBeGreaterThan(0);
  });

  it("con R R C S no se plantea el descarte: el entrenador corta con ella", () => {
    const rrcs = indiceMano(leerMano("R R C S"));
    for (const p of POSICIONES) {
      expect(corte[numeroDeSituacion(rrcs, p)]).toBeGreaterThan(0);
      expect(descarte[numeroDeSituacion(rrcs, p)]).toBe(0);
    }
    expect(descarte[numeroDeSituacion(indiceMano(leerMano("R C 5 4")), 1)]).toBeGreaterThan(0);
  });

  it("se decide mus o corto en más manos de las que se llega a descartar", () => {
    const fCorte = decisionesPorMano("corte", corte, escalas);
    const fDescarte = decisionesPorMano("descarte", descarte, escalas);
    expect(fCorte).toBeGreaterThan(0.25);   // de mano se habla siempre: 1 de cada 4 manos
    expect(fCorte).toBeLessThan(1);
    expect(fDescarte).toBeGreaterThan(0);
    expect(fDescarte).toBeLessThan(fCorte);
  });

  it("número de situación ↔ mano y posición", () => {
    expect(numeroDeSituacion(7, 3)).toBe(30);
    expect(situacionDe(30, "corte", "normal")).toEqual({ ejercicio: "corte", mesa: "normal", indice: 7, posicion: 3 });
    expect(situacionDe(numeroDeSituacion(329, 4), "descarte", "se-corta")).toMatchObject({ indice: 329, posicion: 4 });
  });
});

describe("sorteo", async () => {
  const normal = await datos.mesa("normal");
  const corte = pesos("corte", "mesa", normal, manifiesto);

  it("con la misma semilla, la misma serie; con otra, otra", () => {
    const a = sortear(corte, 10, azarConSemilla(1));
    expect(sortear(corte, 10, azarConSemilla(1))).toEqual(a);
    expect(sortear(corte, 10, azarConSemilla(2))).not.toEqual(a);
    expect(a).toHaveLength(10);
  });

  it("una serie no repite situaciones", () => {
    for (let semilla = 0; semilla < 50; semilla++) {
      const serie = sortear(corte, 10, azarConSemilla(semilla));
      expect(new Set(serie).size).toBe(10);
    }
  });

  it("nunca sale una situación sin peso, y se acaban si no hay más", () => {
    expect(sortear([0, 3, 0, 5, 0], 10, azarConSemilla(3)).sort()).toEqual([1, 3]);
    expect(sortear([0, 0], 3, azarConSemilla(3))).toEqual([]);
    expect(sortear([], 3, azarConSemilla(3))).toEqual([]);
    // Aunque el azar dé el valor más alto posible, el redondeo no saca una sin peso.
    expect(sortear([2, 1, 0], 1, () => 1 - Number.EPSILON)).toEqual([1]);
    expect(sortear([2, 1, 0], 1, () => 0)).toEqual([0]);
    const ajustadas = pesos("corte", "ajustadas", normal, manifiesto);
    for (const k of sortear(ajustadas, 10, azarConSemilla(4))) {
      expect(ajustadas[k]).toBeGreaterThan(0);
    }
  });

  it("las situaciones salen en proporción a su peso", () => {
    // 40 000 sorteos de una situación: la frecuencia de cada posición y de una mano
    // corriente, frente a la que les toca por su peso, con 4 errores típicos de margen.
    const n = 40_000;
    const azar = azarConSemilla(20261012);
    const veces = [0, 0, 0, 0];
    const rc54 = numeroDeSituacion(indiceMano(leerMano("R C 5 4")), 1);
    let vecesMano = 0;
    for (let i = 0; i < n; i++) {
      const [k = -1] = sortear(corte, 1, azar);
      veces[k % 4] = (veces[k % 4] ?? 0) + 1;
      if (k === rc54) vecesMano++;
    }
    const total = corte.reduce((a, b) => a + b, 0);
    const margen = (p: number) => 4 * Math.sqrt((p * (1 - p)) / n);
    for (const p of POSICIONES) {
      const esperada = corte.reduce((t, x, k) => t + (k % 4 === p - 1 ? x : 0), 0) / total;
      expect(Math.abs((veces[p - 1] ?? 0) / n - esperada)).toBeLessThan(margen(esperada));
    }
    const esperadaMano = (corte[rc54] ?? 0) / total;
    expect(Math.abs(vecesMano / n - esperadaMano)).toBeLessThan(margen(esperadaMano));
  });
});
