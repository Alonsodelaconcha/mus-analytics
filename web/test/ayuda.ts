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

/** Valoración y pesos del entrenador calculados por Python (`mus.entrenador.referencia`). */
export interface ReferenciaEntrenador {
  readonly umbrales: { igual: number; clara: number; descarte: number; ajustada: number };
  readonly veredictos: Record<string, string>;
  readonly intensidades: Record<string, string>;
  readonly modos: string[];
  readonly hablan_antes: string[];
  /** Con `{mesa}` donde va el nombre del tipo de mesa. */
  readonly contexto: string;
  readonly mesas: Record<string, {
    /** Arrays en orden (mano, posición). */
    readonly corte: {
      veredicto: number[];
      intensidad: number[];
      perdidos_mus: number[];
      perdidos_corto: number[];
      pesos: Record<string, number[]>;
      decisiones_por_mano: [number, number];
    };
    /** `perdidos` y `vale`, en orden (posición, opción); `mejor` y los pesos, (mano, posición). */
    readonly descarte: {
      perdidos: number[];
      vale: number[];
      mejor: number[];
      pesos: Record<string, number[]>;
      decisiones_por_mano: [number, number];
    };
  }>;
}

/**
 * Generador de números al azar con semilla (mulberry32), para que los tests
 * del sorteo se puedan repetir. En la web se usa `Math.random`.
 */
export function azarConSemilla(semilla: number): () => number {
  let a = semilla >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
