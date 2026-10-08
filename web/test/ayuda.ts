/** Utilidades de los tests: leer los ficheros de referencia y los datos publicados. */

import { readFileSync } from "node:fs";
import { join } from "node:path";

// Las rutas se resuelven desde la carpeta web/ (donde se ejecutan los tests), y no
// con import.meta.url, que en el entorno jsdom no apunta al fichero.
const WEB = process.cwd();

export function leerReferencia(nombre: string): unknown {
  return JSON.parse(readFileSync(join(WEB, "test", "referencia", nombre), "utf8"));
}

/** Bytes de un fichero de `public/datos`, como los recibiría la web. */
export function leerDato(ruta: string): ArrayBuffer {
  const contenido = readFileSync(join(WEB, "public", "datos", ruta));
  return contenido.buffer.slice(contenido.byteOffset, contenido.byteOffset + contenido.byteLength);
}

export type FilaMano = [string, number[], number, number, number, number, number, number, number[]];

export interface ReferenciaEvaluacion {
  readonly manos: FilaMano[];
  readonly lectura: ({ entrada: string; mano: string } | { entrada: string; error: true })[];
}

export interface ReferenciaLances {
  /** [manos en orden de juego, por lance [ganador (0 = no se juega), tantos]]. */
  readonly repartos: [string[], [number, number][]][];
}

export interface ReferenciaDescartes {
  readonly pesos_huella: number[][];
  /** Por opción: [conservadas, pedidas, denominador, pares, medias, duples, juego, 31, huella 1, huella 2]. */
  readonly manos: { texto: string; opciones: number[][] }[];
  readonly distribuciones: { mano: string; conservadas: number; numeradores: [number, number][] }[];
}
