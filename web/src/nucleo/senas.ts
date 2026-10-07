/**
 * Señas del compañero: qué tabla de equity corresponde a las señas marcadas.
 *
 * Regla de la mesa del usuario: las señas son libres y cada una significa
 * "tengo al menos esto". Si el compañero hace varias, cumple todas, así que
 * las manos compatibles son la **intersección** de las de cada seña. No hacer
 * una seña no informa de nada. Python exporta una tabla por cada conjunto de
 * manos distinto que pueden dejar las señas (16 en 8 reyes); aquí solo se
 * busca la que tiene exactamente esa intersección.
 */

import { type Manifiesto, type SenaDatos, type TablaEquityDatos, ErrorDatos } from "./datos";

export type ResultadoSenas =
  | { readonly tipo: "sin-senas"; readonly tabla: TablaEquityDatos }
  | { readonly tipo: "tabla"; readonly tabla: TablaEquityDatos; readonly manos: readonly number[] }
  /** Ninguna mano cumple a la vez todas las señas marcadas. */
  | { readonly tipo: "imposible" };

/** Manos del compañero que cumplen todas las señas, en orden creciente. */
export function manosCompatibles(senas: readonly SenaDatos[], ids: readonly string[]): number[] {
  const porId = new Map(senas.map((s) => [s.id, s]));
  let compatibles: Set<number> | undefined;
  for (const id of ids) {
    const sena = porId.get(id);
    if (sena === undefined) {
      throw new ErrorDatos(`Seña desconocida: «${id}»`);
    }
    const manos = new Set(sena.manos);
    compatibles = compatibles === undefined ? manos : new Set([...compatibles].filter((i) => manos.has(i)));
  }
  return [...(compatibles ?? [])].sort((a, b) => a - b);
}

/** Tabla de equity para las señas marcadas (ninguna = sin información). */
export function tablaParaSenas(manifiesto: Manifiesto, ids: readonly string[]): ResultadoSenas {
  const sinSenas = manifiesto.tablas_equity[0];
  if (sinSenas === undefined) {
    throw new ErrorDatos("El manifiesto no tiene tablas de equity");
  }
  if (ids.length === 0) {
    return { tipo: "sin-senas", tabla: sinSenas };
  }
  const manos = manosCompatibles(manifiesto.senas, ids);
  if (manos.length === 0) {
    return { tipo: "imposible" };
  }
  const clave = manos.join(",");
  const tabla = manifiesto.tablas_equity.find((t) => t.manos?.join(",") === clave);
  if (tabla === undefined) {
    // No debería pasar: Python exporta todos los conjuntos posibles.
    throw new ErrorDatos(`No hay tabla para las señas ${ids.join(" + ")}`);
  }
  return { tipo: "tabla", tabla, manos };
}

/** Señas que podría hacer quien tiene esta mano (útil para la chuleta). */
export function senasDeMano(manifiesto: Manifiesto, indiceMano: number): SenaDatos[] {
  return manifiesto.senas.filter((s) => s.manos.includes(indiceMano));
}
