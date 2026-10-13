/**
 * Lo que dice el entrenador, en lenguaje de jugador: la situación, la
 * valoración de la respuesta, el porqué lance a lance y el resumen de la serie.
 *
 * Funciones puras, como las de `vista.ts`: se prueban con los datos reales.
 */

import { type Resumen, tantosCadaCienManos } from "../entrenador/progreso";
import { type Modo } from "../entrenador/situaciones";
import { MILESIMAS, type RespuestaCorte, type ValoracionCorte } from "../entrenador/valoracion";
import { type DecisionMus } from "../nucleo/datos";
import { type Lance } from "../nucleo/evaluacion";
import { conSigno, decimal, tantosPorMano } from "./lenguaje";
import { type Intensidad, MATIZ_AJUSTADA, vistaDecision } from "./vista";

// --- La situación -----------------------------------------------------------------------

/** Qué ha pasado antes de que te toque hablar, por posición (mano, segundo, tercero y postre). */
export const HABLAN_ANTES = [
  "Eres mano: hablas el primero.",
  "La mano ha dado mus.",
  "Los dos anteriores han dado mus.",
  "Los tres anteriores han dado mus.",
] as const;

const NOMBRE_POSICION = ["mano", "segundo", "tercero", "postre"] as const;

/** "Eres postre. Los tres anteriores han dado mus." */
export function fraseSituacion(posicion: number): string {
  const antes = HABLAN_ANTES[posicion - 1] ?? "";
  return posicion === 1 ? antes : `Eres ${NOMBRE_POSICION[posicion - 1] ?? "?"}. ${antes}`;
}

/**
 * Contra qué se compara cada respuesta. No es "la jugada perfecta": es la
 * mejor contra un tipo de mesa, y con lo que el modelo no cuenta dicho.
 */
export function contexto(nombreMesa: string): string {
  return `La mejor jugada contra una mesa «${nombreMesa}», sin contar envites, señas ni las cartas que piden los demás.`;
}

export const NOMBRE_MODO: Readonly<Record<Modo, { readonly corto: string; readonly descripcion: string }>> = {
  mesa: {
    corto: "Como en la mesa",
    descripcion: "Las manos salen con la frecuencia con que te toca hablar con ellas en una partida: de mano más veces que de postre.",
  },
  ajustadas: {
    corto: "Ajustadas",
    descripcion: "Solo decisiones en que una opción es mejor, pero por poco: menos de 2 tantos cada 10 manos.",
  },
};

// --- La valoración de una respuesta ---------------------------------------------------------

export type Resultado = "bien" | "igual" | "fallo";

export interface VistaRespuesta {
  readonly resultado: Resultado;
  /** "Bien", "Daba igual", "Era mejor cortar" o "Era mejor dar mus". */
  readonly titulo: string;
  /** "Claro", "Por poco" o "" (cuando da igual). */
  readonly etiqueta: string;
  /** Lo que se pierde, o por qué estaba bien. */
  readonly detalle: string;
  /** En las decisiones ajustadas, que con envites podría cambiar. */
  readonly matiz: string;
  /** Milésimas de tanto perdidas. */
  readonly perdidos: number;
}

const ETIQUETA: Readonly<Record<Intensidad, string>> = { clara: "Claro", "por-poco": "Por poco", igual: "" };

export function vistaRespuesta(d: DecisionMus, valoracion: ValoracionCorte, respuesta: RespuestaCorte): VistaRespuesta {
  const { explicacion } = vistaDecision(d);
  const perdidos = valoracion.perdidos[respuesta];
  const comun = {
    etiqueta: ETIQUETA[valoracion.intensidad],
    matiz: valoracion.intensidad === "clara" ? "" : MATIZ_AJUSTADA,
    perdidos,
  };
  if (valoracion.veredicto === "igual") {
    return { ...comun, resultado: "igual", titulo: "Daba igual", detalle: explicacion };
  }
  if (perdidos === 0) {
    return { ...comun, resultado: "bien", titulo: "Bien", detalle: explicacion };
  }
  return {
    ...comun,
    resultado: "fallo",
    titulo: valoracion.veredicto === "mus" ? "Era mejor dar mus" : "Era mejor cortar",
    detalle: `Pierdes ${tantosPorMano(perdidos / MILESIMAS)}. ${explicacion}`,
  };
}

// --- El porqué, lance a lance -----------------------------------------------------------------

/** Por debajo de esto (tantos por mano), un lance "apenas cambia". */
export const UMBRAL_LANCE = 0.02;

const LANCE_EN_PALABRAS: Readonly<Record<Lance, { readonly nombre: string; readonly pesa: string }>> = {
  grande: { nombre: "Grande", pesa: "es la grande" },
  chica: { nombre: "Chica", pesa: "es la chica" },
  pares: { nombre: "Pares", pesa: "son los pares" },
  juego: { nombre: "Juego", pesa: "es el juego" },
  punto: { nombre: "Punto", pesa: "es el punto" },
};

export interface VistaLanceVentaja {
  readonly lance: Lance;
  readonly nombre: string;
  /** Dar mus − cortar en ese lance, en tantos por mano. */
  readonly ventaja: number;
  /** Con dar mus se gana, se pierde, o apenas cambia (dentro del margen o muy poco). */
  readonly efecto: "gana" | "pierde" | "igual";
  /** "+0,12", "−1,30" o "≈ 0". */
  readonly cifra: string;
  /** Tamaño de la barra, de 0 a 1 respecto al lance que más cambia. */
  readonly ancho: number;
}

export interface VistaPorLance {
  readonly lances: readonly VistaLanceVentaja[];
  /** "Lo que más pesa son los pares: dando mus pierdes ahí unos 1,3 tantos por mano." */
  readonly frase: string;
}

/** Qué cambia en cada lance por dar mus en vez de cortar: el porqué de la decisión. */
export function vistaPorLance(d: DecisionMus): VistaPorLance {
  const maximo = Math.max(...d.porLance.map((x) => Math.abs(x.ventaja)), UMBRAL_LANCE);
  const lances = d.porLance.map((x): VistaLanceVentaja => {
    const apenas = Math.abs(x.ventaja) <= x.radio || Math.abs(x.ventaja) < UMBRAL_LANCE;
    return {
      lance: x.lance,
      nombre: LANCE_EN_PALABRAS[x.lance].nombre,
      ventaja: x.ventaja,
      efecto: apenas ? "igual" : x.ventaja > 0 ? "gana" : "pierde",
      cifra: apenas ? "≈ 0" : conSigno(x.ventaja),
      ancho: apenas ? 0 : Math.abs(x.ventaja) / maximo,
    };
  });
  const principal = lances
    .filter((x) => x.efecto !== "igual")
    .reduce<VistaLanceVentaja | null>((a, b) => (a === null || Math.abs(b.ventaja) > Math.abs(a.ventaja) ? b : a), null);
  const frase = principal === null
    ? "Ningún lance cambia apenas por dar mus."
    : `Lo que más pesa ${LANCE_EN_PALABRAS[principal.lance].pesa}: dando mus ${principal.efecto === "gana" ? "ganas" : "pierdes"} ahí ${tantosPorMano(principal.ventaja)}.`;
  return { lances, frase };
}

// --- El resumen de una serie ------------------------------------------------------------------

export interface VistaResumen {
  /** "Has perdido 0,62 tantos en 10 decisiones." */
  readonly total: string;
  /** "7 bien · 1 fallo claro · 2 por poco". */
  readonly desglose: string;
  /** Solo «como en la mesa»: "A ese ritmo, unos 4 tantos cada 100 manos de partida." */
  readonly ritmo: string;
}

const plural = (n: number, uno: string, varios: string): string => `${String(n)} ${n === 1 ? uno : varios}`;

/**
 * Las cifras de una serie (o de todo lo anotado). `decisionesPorMano` es la
 * fracción de las manos de una partida en que te toca decidir en esa mesa: se
 * pasa solo si las situaciones se sortearon «como en la mesa».
 */
export function vistaResumen(r: Resumen, decisionesPorMano: number | null): VistaResumen {
  const total = r.perdidos === 0
    ? `No has perdido nada en ${plural(r.n, "decisión", "decisiones")}.`
    : `Has perdido ${decimal(r.perdidos / MILESIMAS)} tantos en ${plural(r.n, "decisión", "decisiones")}.`;
  const desglose = [
    `${String(r.bien)} bien`,
    ...(r.fallosClaros > 0 ? [plural(r.fallosClaros, "fallo claro", "fallos claros")] : []),
    ...(r.fallosPorPoco > 0 ? [`${String(r.fallosPorPoco)} por poco`] : []),
  ].join(" · ");
  let ritmo = "";
  if (decisionesPorMano !== null && r.n > 0) {
    const cadaCien = tantosCadaCienManos(r, decisionesPorMano);
    ritmo = r.perdidos === 0
      ? "A ese ritmo, no pierdes tantos en esta decisión."
      : `A ese ritmo, unos ${cadaCien >= 10 ? String(Math.round(cadaCien)) : decimal(cadaCien, 1)} tantos cada 100 manos de partida.`;
  }
  return { total, desglose, ritmo };
}

/** "En una mesa «Normal» te toca decidir mus o corto en unas 55 de cada 100 manos." */
export function fraseDecisionesPorMano(nombreMesa: string, decisionesPorMano: number): string {
  return `En una mesa «${nombreMesa}» te toca decidir mus o corto en unas ${String(Math.round(100 * decisionesPorMano))} de cada 100 manos.`;
}
