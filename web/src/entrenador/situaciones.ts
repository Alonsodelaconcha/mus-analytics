/**
 * Qué situaciones plantea el entrenador y con qué frecuencia.
 *
 * Una situación es una mano en una posición, en un tipo de mesa. Cada modo da
 * un peso a cada una de las 1 320 (330 manos × 4 posiciones) y se sortea en
 * proporción a él:
 *
 * - **Como en la mesa** (`mesa`): cada situación sale con la frecuencia con
 *   que se da en una partida. En «¿Mus o corto?», las combinaciones de la mano
 *   por la probabilidad de que te toque hablar con ella (que den mus los
 *   anteriores): de mano se decide más veces que de postre. En «¿Qué tiras?»,
 *   además, la probabilidad de que den mus los de después, y solo con las
 *   manos con las que el entrenador no corta: con R R C S no llegas a
 *   descartarte.
 * - **Ajustadas** (`ajustadas`): solo las situaciones en que hay una opción
 *   peor de verdad, pero por poco (`UMBRAL_AJUSTADA`), con la frecuencia de
 *   la mano.
 *
 * Los pesos son productos de enteros (combinaciones × diezmilésimas), exactos
 * en doble precisión, y se comparan sin tolerancia con los de Python
 * (`mus.entrenador`). El azar se pasa como parámetro: en la web es
 * `Math.random` y cada serie es distinta; solo los tests usan una semilla.
 */

import {
  type FicheroMesa,
  type Manifiesto,
  POSICIONES,
  decisionDe,
  opcionesDe,
} from "../nucleo/datos";
import { tabla } from "../nucleo/tablas";
import { valorarCorte, valorarDescartes } from "./valoracion";

export const EJERCICIOS = ["corte", "descarte"] as const;
/** «¿Mus o corto?» o «¿Qué tiras?». */
export type Ejercicio = (typeof EJERCICIOS)[number];

export const MODOS = ["mesa", "ajustadas"] as const;
export type Modo = (typeof MODOS)[number];

/**
 * Milésimas de tanto. Una situación es "ajustada" si hay una opción peor de
 * verdad, pero por menos de esto: menos de 2 tantos cada 10 manos.
 */
export const UMBRAL_AJUSTADA = 200;

/** Cartas que se reparten a un jugador entre las 40: C(40, 4). */
const TOTAL_COMBINACIONES = 91_390;

export interface Situacion {
  readonly ejercicio: Ejercicio;
  /** Id del tipo de mesa. */
  readonly mesa: string;
  /** Número de la mano (orden del manifiesto). */
  readonly indice: number;
  /** 1 = mano … 4 = postre. */
  readonly posicion: number;
}

/** Número de situación a partir de la mano y la posición, y al revés. */
export function numeroDeSituacion(indice: number, posicion: number): number {
  return indice * POSICIONES.length + posicion - 1;
}

export function situacionDe(numero: number, ejercicio: Ejercicio, mesa: string): Situacion {
  return {
    ejercicio,
    mesa,
    indice: Math.floor(numero / POSICIONES.length),
    posicion: (numero % POSICIONES.length) + 1,
  };
}

function pesoCorte(modo: Modo, mesa: FicheroMesa, manifiesto: Manifiesto, h: number, p: number): number {
  const d = decisionDe(mesa, manifiesto.escalas, h, p);
  const combinaciones = tabla().combinaciones[h] ?? 0;
  if (d === null) return 0;
  if (modo === "mesa") {
    return combinaciones * (mesa.decision.p_habla[numeroDeSituacion(h, p)] ?? 0);
  }
  const { perdidos } = valorarCorte(d);
  const coste = Math.max(perdidos.mus, perdidos.corta);
  return coste > 0 && coste < UMBRAL_AJUSTADA ? combinaciones : 0;
}

function pesoDescarte(modo: Modo, mesa: FicheroMesa, manifiesto: Manifiesto, h: number, p: number): number {
  const mano = tabla().manos[h];
  if (mano === undefined) return 0;
  const valores = opcionesDe(mesa, manifiesto, mano, h, p);
  const combinaciones = tabla().combinaciones[h] ?? 0;
  if (valores.length === 0) return 0;
  if (modo === "mesa") {
    const d = decisionDe(mesa, manifiesto.escalas, h, p);
    // Quien se entrena es quien decide con esta mano: si corta, no llega a descartarse.
    if (d === null || valorarCorte(d).veredicto === "corta") return 0;
    const k = numeroDeSituacion(h, p);
    return combinaciones * (mesa.decision.p_habla[k] ?? 0) * (mesa.decision.p_mus_despues[k] ?? 0);
  }
  const costes = valorarDescartes(valores).filter((o) => !o.vale).map((o) => o.perdidos);
  return costes.length > 0 && Math.min(...costes) < UMBRAL_AJUSTADA ? combinaciones : 0;
}

/**
 * Peso de cada situación de un ejercicio, en orden (mano, posición): 0 si no
 * se plantea en ese modo.
 */
export function pesos(ejercicio: Ejercicio, modo: Modo, mesa: FicheroMesa, manifiesto: Manifiesto): number[] {
  const peso = ejercicio === "corte" ? pesoCorte : pesoDescarte;
  const resultado: number[] = [];
  for (let h = 0; h < tabla().manos.length; h++) {
    for (const p of POSICIONES) {
      resultado.push(peso(modo, mesa, manifiesto, h, p));
    }
  }
  return resultado;
}

/**
 * Fracción de las manos de una partida en que se llega a tomar esa decisión,
 * a partir de los pesos del modo «como en la mesa»: en cada mano se ocupa una
 * de las cuatro posiciones, con la misma probabilidad. Con ella se pasa de
 * "tantos perdidos por decisión" a "tantos perdidos por mano jugada".
 */
export function decisionesPorMano(
  ejercicio: Ejercicio,
  pesosMesa: readonly number[],
  escalas: Manifiesto["escalas"],
): number {
  const escala = ejercicio === "corte" ? escalas.probabilidad : escalas.probabilidad ** 2;
  const suma = pesosMesa.reduce((a, b) => a + b, 0);
  return suma / (POSICIONES.length * TOTAL_COMBINACIONES * escala);
}

/** Un número al azar en [0, 1): `Math.random` en la web, con semilla en los tests. */
export type Azar = () => number;

/**
 * Sortea `cuantas` situaciones distintas, cada una con probabilidad
 * proporcional a su peso entre las que quedan. Devuelve sus números (menos de
 * `cuantas` si no hay tantas con peso).
 */
export function sortear(pesosSituaciones: readonly number[], cuantas: number, azar: Azar): number[] {
  const restantes = [...pesosSituaciones];
  let total = restantes.reduce((a, b) => a + b, 0);
  const elegidas: number[] = [];
  while (elegidas.length < cuantas && total > 0) {
    let resto = azar() * total;
    let elegida = -1;
    for (const [k, peso] of restantes.entries()) {
      if (peso <= 0) continue;
      elegida = k; // por si el redondeo deja `resto` justo al final
      resto -= peso;
      if (resto < 0) break;
    }
    if (elegida < 0) break;
    elegidas.push(elegida);
    total -= restantes[elegida] ?? 0;
    restantes[elegida] = 0;
  }
  return elegidas;
}
