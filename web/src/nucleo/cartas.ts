/**
 * Baraja de 8 reyes, lectura de manos y representación canónica.
 *
 * Es la traducción de `mus.cartas` (Python), que es la referencia: los tests
 * comparan este módulo con los ficheros que exporta `python -m mus exportar-web`.
 *
 * Como el palo no importa, una mano es el número de cartas de cada rango
 * (sus *conteos*). Los rangos van de 0 (el As, el más bajo) a 7 (el Rey). En
 * 8 reyes, el 3 es un Rey y el 2 es un As a todos los efectos.
 */

export const SIMBOLOS = ["A", "4", "5", "6", "7", "S", "C", "R"] as const;
/** Cartas de cada rango en la baraja (8 reyes y 8 ases, contando treses y doses). */
export const COPIAS: readonly number[] = [8, 4, 4, 4, 4, 4, 4, 8];
/** Valor de cada rango para el juego y el punto. */
export const VALORES: readonly number[] = [1, 4, 5, 6, 7, 10, 10, 10];
export const N_RANGOS = SIMBOLOS.length;
export const CARTAS_POR_MANO = 4;
export const TOTAL_CARTAS = COPIAS.reduce((a, b) => a + b, 0);
/** Base del código de una mano: cada conteo está entre 0 y 4. */
const BASE_CODIGO = CARTAS_POR_MANO + 1;

/** Otros símbolos que se aceptan al leer una mano y el rango al que equivalen. */
const ALIAS: Readonly<Record<string, string>> = {
  "1": "A",
  "10": "S",
  "11": "C",
  "12": "R",
  "2": "A",
  "3": "R",
};

/** Conteos por rango de una mano (8 números que suman 4). */
export type Conteos = readonly number[];

export class ErrorLectura extends Error {
  override name = "ErrorLectura";
}

/** Rango de un símbolo, admitiendo alias y minúsculas. */
export function indiceRango(token: string): number {
  const t = token.trim().toUpperCase();
  const simbolo = ALIAS[t] ?? t;
  const indice = (SIMBOLOS as readonly string[]).indexOf(simbolo);
  if (indice < 0) {
    const validos = [...SIMBOLOS, ...Object.keys(ALIAS)].join(", ");
    throw new ErrorLectura(`Carta desconocida: «${token}». Válidas: ${validos}`);
  }
  return indice;
}

/** Conteos de una lista de rangos en cualquier orden. */
export function desdeRangos(rangos: readonly number[]): Conteos {
  const conteos = new Array<number>(N_RANGOS).fill(0);
  for (const r of rangos) {
    conteos[r] = (conteos[r] ?? 0) + 1;
  }
  return conteos;
}

/** True si la baraja tiene cartas suficientes para formar la mano. */
export function cabeEnLaBaraja(conteos: Conteos): boolean {
  return conteos.length === N_RANGOS && conteos.every((k, r) => k >= 0 && k <= (COPIAS[r] ?? 0));
}

/**
 * Lee una mano escrita como "R R C 5", "R,R,C,5" o "RRC5".
 *
 * Acepta los símbolos de la baraja, los alias numéricos (1, 10, 11, 12) y, en
 * 8 reyes, 3 como Rey y 2 como As.
 *
 * @throws ErrorLectura si hay cartas desconocidas o no son 4.
 */
export function leerMano(texto: string): Conteos {
  let tokens = texto
    .trim()
    .split(/[\s,;]+/)
    .filter((t) => t.length > 0);
  const unico = tokens[0];
  if (tokens.length === 1 && unico !== undefined && Array.from(unico).length === CARTAS_POR_MANO) {
    tokens = Array.from(unico);
  }
  if (tokens.length !== CARTAS_POR_MANO) {
    throw new ErrorLectura(
      `Se esperaban ${CARTAS_POR_MANO} cartas y hay ${tokens.length}: «${texto}»`,
    );
  }
  const conteos = desdeRangos(tokens.map(indiceRango));
  if (!cabeEnLaBaraja(conteos)) {
    throw new ErrorLectura(`La baraja no tiene cartas suficientes para «${texto}»`);
  }
  return conteos;
}

/** Rangos de las 4 cartas, de mayor a menor. */
export function rangos(conteos: Conteos): number[] {
  const resultado: number[] = [];
  for (let r = N_RANGOS - 1; r >= 0; r--) {
    for (let i = 0; i < (conteos[r] ?? 0); i++) {
      resultado.push(r);
    }
  }
  return resultado;
}

/**
 * Entero único de una mano: los conteos leídos como número en base 5.
 * Es la suma de 5^rango de cada carta, igual que en Python.
 */
export function codigo(conteos: Conteos): number {
  return conteos.reduce((total, k, r) => total + k * BASE_CODIGO ** r, 0);
}

/** Conteos a partir del código (la operación inversa de {@link codigo}). */
export function desdeCodigo(valor: number): Conteos {
  const conteos: number[] = [];
  let resto = valor;
  for (let r = 0; r < N_RANGOS; r++) {
    conteos.push(resto % BASE_CODIGO);
    resto = Math.floor(resto / BASE_CODIGO);
  }
  return conteos;
}

/** Texto de una mano, de mayor a menor (p. ej. "R R C 5"); "-" si no tiene cartas. */
export function texto(conteos: Conteos): string {
  return rangos(conteos)
    .map((r) => SIMBOLOS[r] ?? "?")
    .join(" ") || "-";
}

/** C(n, k) exacto para los tamaños de la baraja (resultado < 2^53). */
export function combinaciones(n: number, k: number): number {
  if (k < 0 || k > n) {
    return 0;
  }
  let resultado = 1;
  for (let i = 1; i <= k; i++) {
    resultado = (resultado * (n - k + i)) / i;
  }
  return Math.round(resultado);
}

/** Todos los multiconjuntos de `n` cartas como conteos, en orden lexicográfico. */
export function multiconjuntos(n: number): Conteos[] {
  const resultado: Conteos[] = [];
  const actual = new Array<number>(N_RANGOS).fill(0);
  const recorrer = (rango: number, restantes: number): void => {
    if (rango === N_RANGOS - 1) {
      actual[rango] = restantes;
      resultado.push([...actual]);
      return;
    }
    for (let k = restantes; k >= 0; k--) {
      actual[rango] = k;
      recorrer(rango + 1, restantes - k);
    }
  };
  recorrer(0, n);
  return resultado;
}

/**
 * Las 330 manos distintas, ordenadas por código (el mismo orden que en
 * Python y en todos los ficheros de datos).
 */
export function enumerarManos(): Conteos[] {
  return multiconjuntos(CARTAS_POR_MANO)
    .filter(cabeEnLaBaraja)
    .sort((a, b) => codigo(a) - codigo(b));
}
