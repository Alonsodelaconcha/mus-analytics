/**
 * Evaluación de los lances y resolución de un lance entre 4 jugadores.
 *
 * Traducción de `mus.evaluacion`. Cada lance tiene una *clave*: una lista de
 * números que se compara elemento a elemento, en la que mayor = mejor jugada.
 * `null` significa que la mano no participa (sin pares, sin juego o, en el
 * punto, con juego). Los empates de clave los gana el jugador más cercano a
 * la mano.
 */

import { type Conteos, VALORES, rangos } from "./cartas";

export const LANCES = ["grande", "chica", "pares", "juego", "punto"] as const;
export type Lance = (typeof LANCES)[number];

/** Categorías de pares, de peor a mejor. */
export const Pares = { SIN_PARES: 0, PAR: 1, MEDIAS: 2, DUPLES: 3 } as const;
export type Pares = (typeof Pares)[keyof typeof Pares];

export type Clave = readonly number[];

/** Puntuación en paso (sin envites). En pares y juego, la pareja ganadora cobra las jugadas de los dos. */
export interface Puntuacion {
  readonly grande: number;
  readonly chica: number;
  readonly par: number;
  readonly medias: number;
  readonly duples: number;
  readonly juego_31: number;
  readonly juego_otro: number;
  readonly punto: number;
}

/**
 * Reglas que usa el núcleo. Son las de la web (8 reyes, sin 31 real); los
 * datos traen las suyas en el manifiesto y la carga comprueba que coinciden.
 */
export interface Reglas {
  /** Sumas con juego, de mejor a peor. */
  readonly ordenJuego: readonly number[];
  readonly puntuacion: Puntuacion;
}

export const REGLAS_POR_DEFECTO: Reglas = {
  ordenJuego: [31, 32, 40, 37, 36, 35, 34, 33],
  puntuacion: {
    grande: 1,
    chica: 1,
    par: 1,
    medias: 2,
    duples: 3,
    juego_31: 3,
    juego_otro: 2,
    punto: 1,
  },
};

export const JUGADORES = 4;

/** Compara dos claves elemento a elemento (como las tuplas de Python): <0, 0 o >0. */
export function compararClaves(a: Clave, b: Clave): number {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    const diferencia = (a[i] ?? 0) - (b[i] ?? 0);
    if (diferencia !== 0) {
      return diferencia;
    }
  }
  return a.length - b.length;
}

/** Grande: cartas de mayor a menor. */
export function claveGrande(mano: Conteos): Clave {
  return rangos(mano);
}

/** Chica: cartas de menor a mayor, negadas (la mano más baja tiene la clave mayor). */
export function claveChica(mano: Conteos): Clave {
  return rangos(mano)
    .reverse()
    .map((r) => -r);
}

/**
 * Pares: `[categoría, rango alto, rango bajo]` o `null` sin pares.
 *
 * - Par: solo cuenta el rango de la pareja.
 * - Medias: rango del trío.
 * - Duples: pareja alta y luego baja. Cuatro iguales son duples de ese rango
 *   (RRRR > RRCC; RR44 > 5555).
 */
export function clavePares(mano: Conteos): Clave | null {
  const grupos: [number, number][] = [];
  mano.forEach((k, r) => {
    if (k >= 2) {
      grupos.push([r, k]);
    }
  });
  grupos.sort((a, b) => b[0] - a[0]); // rango más alto primero
  const [alto, bajo] = grupos;
  if (alto === undefined) {
    return null;
  }
  if (bajo !== undefined) {
    return [Pares.DUPLES, alto[0], bajo[0]];
  }
  const categoria = alto[1] === 2 ? Pares.PAR : alto[1] === 3 ? Pares.MEDIAS : Pares.DUPLES;
  return [categoria, alto[0], alto[0]];
}

export function jugadaPares(mano: Conteos): Pares {
  const clave = clavePares(mano);
  return clave === null ? Pares.SIN_PARES : (clave[0] as Pares);
}

/** Suma de la mano para el juego y el punto. */
export function suma(mano: Conteos): number {
  return mano.reduce((total, k, r) => total + k * (VALORES[r] ?? 0), 0);
}

/** Juego: prioridad de la suma según el orden del juego, o `null` sin juego. */
export function claveJuego(mano: Conteos, reglas: Reglas = REGLAS_POR_DEFECTO): Clave | null {
  const s = suma(mano);
  if (s < 31) {
    return null;
  }
  const posicion = reglas.ordenJuego.indexOf(s);
  if (posicion < 0) {
    throw new Error(`La suma ${s} tiene juego pero no está en el orden del juego`);
  }
  return [reglas.ordenJuego.length - posicion];
}

/** Punto: la suma si no hay juego; `null` si lo hay. */
export function clavePunto(mano: Conteos): Clave | null {
  const s = suma(mano);
  return s >= 31 ? null : [s];
}

export function clave(lance: Lance, mano: Conteos, reglas: Reglas = REGLAS_POR_DEFECTO): Clave | null {
  switch (lance) {
    case "grande":
      return claveGrande(mano);
    case "chica":
      return claveChica(mano);
    case "pares":
      return clavePares(mano);
    case "juego":
      return claveJuego(mano, reglas);
    case "punto":
      return clavePunto(mano);
  }
}

/** Tantos que vale la jugada de pares (0 sin pares). */
export function puntosPares(mano: Conteos, reglas: Reglas = REGLAS_POR_DEFECTO): number {
  const p = reglas.puntuacion;
  return [0, p.par, p.medias, p.duples][jugadaPares(mano)] ?? 0;
}

/** Tantos que vale el juego (0 sin juego). */
export function puntosJuego(mano: Conteos, reglas: Reglas = REGLAS_POR_DEFECTO): number {
  const s = suma(mano);
  if (s < 31) {
    return 0;
  }
  return s === 31 ? reglas.puntuacion.juego_31 : reglas.puntuacion.juego_otro;
}

/** Pareja de una posición (1-4): pareja 1 = (1, 3), pareja 2 = (2, 4). */
export function parejaDe(posicion: number): 1 | 2 {
  return posicion % 2 === 1 ? 1 : 2;
}

/**
 * Posición (1-4) de la mejor clave, o `null` si nadie participa. Como solo
 * se sustituye al ganador con una clave estrictamente mayor, los empates los
 * gana el más cercano a la mano.
 */
export function mejorPosicion(claves: readonly (Clave | null)[]): number | null {
  let mejor: number | null = null;
  let claveMejor: Clave | null = null;
  for (const [i, c] of claves.entries()) {
    if (c !== null && (claveMejor === null || compararClaves(c, claveMejor) > 0)) {
      mejor = i + 1;
      claveMejor = c;
    }
  }
  return mejor;
}

export interface ResultadoLance {
  readonly lance: Lance;
  /** False si nadie participa o, en el punto, si alguien tiene juego. */
  readonly seJuega: boolean;
  /** Posición ganadora (1-4) o `null`. */
  readonly ganador: number | null;
  readonly pareja: 1 | 2 | null;
  /** Tantos que cobra la pareja ganadora. */
  readonly tantos: number;
}

/** Resuelve un lance entre 4 manos en orden de juego (la primera es la mano), en paso. */
export function resolverLance(
  manos: readonly Conteos[],
  lance: Lance,
  reglas: Reglas = REGLAS_POR_DEFECTO,
): ResultadoLance {
  if (manos.length !== JUGADORES) {
    throw new Error(`Se necesitan ${JUGADORES} manos`);
  }
  const nadie: ResultadoLance = { lance, seJuega: false, ganador: null, pareja: null, tantos: 0 };
  if (lance === "punto" && manos.some((m) => suma(m) >= 31)) {
    return nadie;
  }
  const ganador = mejorPosicion(manos.map((m) => clave(lance, m, reglas)));
  if (ganador === null) {
    return nadie;
  }
  const pareja = parejaDe(ganador);
  const companeros = manos.filter((_, i) => parejaDe(i + 1) === pareja);
  const p = reglas.puntuacion;
  let tantos: number;
  switch (lance) {
    case "grande":
      tantos = p.grande;
      break;
    case "chica":
      tantos = p.chica;
      break;
    case "pares":
      tantos = companeros.reduce((t, m) => t + puntosPares(m, reglas), 0);
      break;
    case "juego":
      tantos = companeros.reduce((t, m) => t + puntosJuego(m, reglas), 0);
      break;
    case "punto":
      tantos = p.punto;
      break;
  }
  return { lance, seJuega: true, ganador, pareja, tantos };
}

/** Resuelve los cinco lances de una mano completa jugada en paso. */
export function resolverMano(
  manos: readonly Conteos[],
  reglas: Reglas = REGLAS_POR_DEFECTO,
): ResultadoLance[] {
  return LANCES.map((lance) => resolverLance(manos, lance, reglas));
}
