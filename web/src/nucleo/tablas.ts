/**
 * Tabla de las 330 manos con sus evaluaciones precalculadas.
 *
 * Traducción de `mus.tablas`. Se evalúa cada mano una vez y se guarda todo
 * indexado por número de mano, en el orden canónico (por código), que es el
 * de todos los ficheros de datos. La *fuerza* de cada lance es un entero
 * denso que conserva el orden de las claves (0 = no participa).
 */

import {
  COPIAS,
  type Conteos,
  combinaciones as comb,
  codigo,
  enumerarManos,
  texto,
} from "./cartas";
import {
  type Clave,
  LANCES,
  type Lance,
  type Pares,
  REGLAS_POR_DEFECTO,
  type Reglas,
  clave,
  compararClaves,
  jugadaPares,
  puntosJuego,
  puntosPares,
  suma,
} from "./evaluacion";

export interface TablaManos {
  readonly reglas: Reglas;
  readonly manos: readonly Conteos[];
  readonly textos: readonly string[];
  readonly codigos: readonly number[];
  /** Manos físicas (con palo) que dan cada mano: ∏ C(copias_r, k_r). */
  readonly combinaciones: readonly number[];
  readonly probabilidad: readonly number[];
  readonly suma: readonly number[];
  readonly jugadaPares: readonly Pares[];
  readonly puntosPares: readonly number[];
  readonly puntosJuego: readonly number[];
  readonly fuerza: Readonly<Record<Lance, readonly number[]>>;
  /** Número de mano a partir de su código. */
  readonly indicePorCodigo: ReadonlyMap<number, number>;
}

/** Enteros densos que conservan el orden de las claves; `null` → 0. */
export function fuerzasDensas(claves: readonly (Clave | null)[]): number[] {
  const distintas = new Map<string, Clave>();
  for (const c of claves) {
    if (c !== null) {
      distintas.set(c.join(","), c);
    }
  }
  const ordenadas = [...distintas.values()].sort(compararClaves);
  const posicion = new Map(ordenadas.map((c, i) => [c.join(","), i + 1]));
  return claves.map((c) => (c === null ? 0 : (posicion.get(c.join(",")) ?? 0)));
}

export function construirTabla(reglas: Reglas = REGLAS_POR_DEFECTO): TablaManos {
  const manos = enumerarManos();
  const combinaciones = manos.map((m) => m.reduce((p, k, r) => p * comb(COPIAS[r] ?? 0, k), 1));
  const total = combinaciones.reduce((a, b) => a + b, 0);
  const fuerza = Object.fromEntries(
    LANCES.map((lance) => [lance, fuerzasDensas(manos.map((m) => clave(lance, m, reglas)))]),
  ) as Record<Lance, number[]>;
  return {
    reglas,
    manos,
    textos: manos.map(texto),
    codigos: manos.map(codigo),
    combinaciones,
    probabilidad: combinaciones.map((c) => c / total),
    suma: manos.map(suma),
    jugadaPares: manos.map(jugadaPares),
    puntosPares: manos.map((m) => puntosPares(m, reglas)),
    puntosJuego: manos.map((m) => puntosJuego(m, reglas)),
    fuerza,
    indicePorCodigo: new Map(manos.map((m, i) => [codigo(m), i])),
  };
}

let tablaPorDefecto: TablaManos | undefined;

/** La tabla con las reglas por defecto, construida una sola vez. */
export function tabla(): TablaManos {
  tablaPorDefecto ??= construirTabla();
  return tablaPorDefecto;
}

/** Número de mano (posición en el orden canónico). */
export function indiceMano(mano: Conteos, t: TablaManos = tabla()): number {
  const indice = t.indicePorCodigo.get(codigo(mano));
  if (indice === undefined) {
    throw new Error(`No es una mano válida: ${mano.join(",")}`);
  }
  return indice;
}
