/**
 * Valoración de las respuestas del entrenador: cuántos tantos se pierden
 * frente a la mejor opción.
 *
 * No hay ninguna regla nueva: el veredicto sale de las mismas funciones con
 * que la calculadora decide qué enseñar (`vistaDecision`, `esCasiIgual`), así
 * que el entrenador no puede decir otra cosa que ella. Si la calculadora dice
 * «Da igual» o «Casi igual que la mejor», aquí no se pierde nada.
 *
 * Los tantos perdidos van en milésimas (enteros), como en los ficheros de
 * datos: se suman sin errores de redondeo y se comparan sin tolerancia con la
 * referencia de Python (`mus.entrenador`).
 */

import { type DecisionMus, type ValorOpcion } from "../nucleo/datos";
import { type Intensidad, type Veredicto, esCasiIgual, vistaDecision } from "../vista/vista";

/** Milésimas por tanto: la escala de los tantos perdidos. */
export const MILESIMAS = 1000;

export type RespuestaCorte = "mus" | "corta";

export interface ValoracionCorte {
  /** Lo mejor: "mus", "corta" o "igual" (cualquiera de las dos vale). */
  readonly veredicto: Veredicto;
  readonly intensidad: Intensidad;
  /** Milésimas de tanto que pierde cada respuesta frente a la mejor. */
  readonly perdidos: Readonly<Record<RespuestaCorte, number>>;
}

/** Qué vale cada respuesta a «¿Mus o corto?». */
export function valorarCorte(d: DecisionMus): ValoracionCorte {
  const { veredicto, intensidad } = vistaDecision(d);
  const ventaja = Math.round(Math.abs(d.ventaja) * MILESIMAS);
  return {
    veredicto,
    intensidad,
    perdidos: {
      mus: veredicto === "corta" ? ventaja : 0,
      corta: veredicto === "mus" ? ventaja : 0,
    },
  };
}

export interface ValoracionOpcion {
  readonly valor: ValorOpcion;
  /** 0 = la mejor; 1 = la segunda... */
  readonly puesto: number;
  /** La mejor o casi igual que la mejor: no se pierde nada. */
  readonly vale: boolean;
  /** Milésimas de tanto que se pierden frente a la mejor. */
  readonly perdidos: number;
}

/**
 * Qué vale cada forma de descartarse. `valores` va de mejor a peor, como lo
 * devuelve `opcionesDe`.
 */
export function valorarDescartes(valores: readonly ValorOpcion[]): ValoracionOpcion[] {
  return valores.map((valor, puesto) => {
    const vale = puesto === 0 || esCasiIgual(valor);
    return {
      valor,
      puesto,
      vale,
      perdidos: vale ? 0 : Math.round(Math.abs(valor.diferencia) * MILESIMAS),
    };
  });
}
