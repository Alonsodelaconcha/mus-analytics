/**
 * Opciones de descarte y distribución exacta de la mano tras descartarse.
 *
 * Traducción de `mus.descarte`. Desde el punto de vista del jugador, las
 * cartas que roba son un subconjunto uniforme de las 36 que no ve (las que
 * descarta tampoco pueden volver). La probabilidad de robar el multiconjunto
 * D es una hipergeométrica multivariante: ∏ C(U_r, d_r) / C(36, n), con
 * U = copias − mi mano. Se trabaja con los numeradores enteros, que son
 * exactos en doble precisión (C(36, 4) = 58 905).
 */

import {
  CARTAS_POR_MANO,
  COPIAS,
  type Conteos,
  N_RANGOS,
  TOTAL_CARTAS,
  codigo,
  combinaciones,
  multiconjuntos,
} from "./cartas";
import { Pares } from "./evaluacion";
import { type TablaManos, indiceMano, tabla } from "./tablas";

export interface ReglasDescarte {
  /** Cartas que hay que descartar si hay mus (por defecto, de 1 a 4). */
  readonly minimo: number;
  readonly maximo: number;
}

export const DESCARTE_POR_DEFECTO: ReglasDescarte = { minimo: 1, maximo: 4 };

export interface OpcionDescarte {
  readonly conservadas: Conteos;
  readonly descartadas: Conteos;
  readonly nDescartes: number;
  /** Código de las cartas que se conservan (como el de una mano). */
  readonly codigo: number;
}

/**
 * Formas distintas de descartarse, en el orden de Python: de menos a más
 * cartas tiradas y, a igualdad, conservando antes las cartas más altas.
 */
export function opcionesDescarte(
  mano: Conteos,
  reglas: ReglasDescarte = DESCARTE_POR_DEFECTO,
): OpcionDescarte[] {
  const opciones: OpcionDescarte[] = [];
  const actual = new Array<number>(N_RANGOS).fill(0);
  const recorrer = (rango: number): void => {
    if (rango === N_RANGOS) {
      const n = CARTAS_POR_MANO - actual.reduce((a, b) => a + b, 0);
      if (n >= reglas.minimo && n <= reglas.maximo) {
        const conservadas = [...actual];
        opciones.push({
          conservadas,
          descartadas: mano.map((k, r) => k - (conservadas[r] ?? 0)),
          nDescartes: n,
          codigo: codigo(conservadas),
        });
      }
      return;
    }
    for (let c = 0; c <= (mano[rango] ?? 0); c++) {
      actual[rango] = c;
      recorrer(rango + 1);
    }
  };
  recorrer(0);
  return opciones.sort((a, b) => a.nDescartes - b.nDescartes || ordenConservadas(a, b));
}

/** Compara (−c_R, −c_C, …, −c_A): primero la opción que conserva más cartas altas. */
function ordenConservadas(a: OpcionDescarte, b: OpcionDescarte): number {
  for (let r = N_RANGOS - 1; r >= 0; r--) {
    const diferencia = (b.conservadas[r] ?? 0) - (a.conservadas[r] ?? 0);
    if (diferencia !== 0) {
      return diferencia;
    }
  }
  return 0;
}

/** Distribución exacta de la mano final: numerador entero de cada mano sobre `denominador`. */
export interface Distribucion {
  /** C(36, cartas pedidas). */
  readonly denominador: number;
  /** Número de mano final → numerador (solo las manos posibles). */
  readonly numeradores: ReadonlyMap<number, number>;
}

const robosPorNumero = new Map<number, Conteos[]>();

function robos(n: number): Conteos[] {
  let lista = robosPorNumero.get(n);
  if (lista === undefined) {
    lista = multiconjuntos(n);
    robosPorNumero.set(n, lista);
  }
  return lista;
}

export function distribucionTrasDescarte(
  mano: Conteos,
  opcion: OpcionDescarte,
  t: TablaManos = tabla(),
): Distribucion {
  const noVistas = COPIAS.map((c, r) => c - (mano[r] ?? 0));
  const n = opcion.nDescartes;
  const numeradores = new Map<number, number>();
  let total = 0;
  for (const robo of robos(n)) {
    const peso = robo.reduce((p, d, r) => p * combinaciones(noVistas[r] ?? 0, d), 1);
    if (peso === 0) {
      continue;
    }
    const final = indiceMano(
      opcion.conservadas.map((c, r) => c + (robo[r] ?? 0)),
      t,
    );
    numeradores.set(final, (numeradores.get(final) ?? 0) + peso);
    total += peso;
  }
  const denominador = combinaciones(TOTAL_CARTAS - CARTAS_POR_MANO, n);
  if (total !== denominador) {
    throw new Error(`Los pesos suman ${total} y deberían sumar C(36, ${n}) = ${denominador}`);
  }
  return { denominador, numeradores };
}

/** Probabilidades exactas de la jugada final (como en la Fase 3a). */
export interface ResumenDistribucion {
  readonly pares: number;
  readonly medias: number;
  readonly duples: number;
  readonly juego: number;
  readonly juego31: number;
}

/** Numeradores enteros de cada jugada (para comparar con Python sin redondeos). */
export function numeradoresPorJugada(d: Distribucion, t: TablaManos = tabla()): ResumenDistribucion {
  let pares = 0;
  let medias = 0;
  let duples = 0;
  let juego = 0;
  let juego31 = 0;
  for (const [indice, numerador] of d.numeradores) {
    const jugada = t.jugadaPares[indice] ?? Pares.SIN_PARES;
    const s = t.suma[indice] ?? 0;
    if (jugada !== Pares.SIN_PARES) pares += numerador;
    if (jugada === Pares.MEDIAS) medias += numerador;
    if (jugada === Pares.DUPLES) duples += numerador;
    if (s >= 31) juego += numerador;
    if (s === 31) juego31 += numerador;
  }
  return { pares, medias, duples, juego, juego31 };
}

/** Probabilidad de cada jugada tras el descarte. */
export function resumenDistribucion(d: Distribucion, t: TablaManos = tabla()): ResumenDistribucion {
  const n = numeradoresPorJugada(d, t);
  return {
    pares: n.pares / d.denominador,
    medias: n.medias / d.denominador,
    duples: n.duples / d.denominador,
    juego: n.juego / d.denominador,
    juego31: n.juego31 / d.denominador,
  };
}

/**
 * Valor esperado de una magnitud definida por mano final (p. ej. la
 * probabilidad de ganar el juego tras el mus): Σ P(mano) · valor(mano).
 */
export function esperanza(d: Distribucion, valor: (indice: number) => number): number {
  let total = 0;
  for (const [indice, numerador] of d.numeradores) {
    total += numerador * valor(indice);
  }
  return total / d.denominador;
}
