/**
 * Qué enseña cada bloque de la pantalla, calculado a partir de los datos.
 *
 * Son funciones puras, sin React, para poder probarlas con los datos reales.
 * Los umbrales con que una decisión se llama "clara", "por poco" o "da
 * igual" son de presentación y están aquí, documentados.
 */

import { type Conteos } from "../nucleo/cartas";
import {
  type DecisionMus,
  type Entero,
  type EquityMano,
  type Manifiesto,
  type ValorOpcion,
  equityDe,
  tantosTotales,
} from "../nucleo/datos";
import {
  type Distribucion,
  type ResumenDistribucion,
  distribucionTrasDescarte,
  esperanza,
  resumenDistribucion,
} from "../nucleo/descarte";
import { LANCES, type Lance, suma } from "../nucleo/evaluacion";
import { frecuencia, frecuenciaCorta, porcentaje, tantosPorMano, textoOpcion } from "./lenguaje";

const HASTA_UN_DECIMAL = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });

/**
 * Por debajo de esta diferencia (tantos por mano), cortar y dar mus "dan
 * igual": menos de un tanto cada 30 manos, muy por debajo de lo que mueve
 * cualquier envite.
 */
export const UMBRAL_IGUAL = 0.03;
/** A partir de esta diferencia la decisión es "clara" (más de 1,5 tantos cada 10 manos). */
export const UMBRAL_CLARA = 0.15;
/** Dos descartes se consideran "casi iguales" si difieren menos que esto o que su margen de error. */
export const UMBRAL_DESCARTE = 0.02;

export type Veredicto = "corta" | "mus" | "igual";
export type Intensidad = "clara" | "por-poco" | "igual";

export interface VistaDecision {
  readonly veredicto: Veredicto;
  readonly intensidad: Intensidad;
  /** "Corta", "Da mus" o "Da igual". */
  readonly titulo: string;
  /** "Claro", "Por poco" o "" (cuando da igual). */
  readonly etiqueta: string;
  /** Una frase con cuánto se gana. */
  readonly explicacion: string;
  /** En las decisiones ajustadas, que con envites podría cambiar ("" si es clara). */
  readonly matiz: string;
  readonly ventaja: number;
  readonly radio: number;
  readonly pMusDespues: number;
  readonly repartos: number;
}

/** Las cifras son en paso: en las decisiones ajustadas, los envites pueden darles la vuelta. */
export const MATIZ_AJUSTADA = "Con envites o según el marcador, podría cambiar.";

export function vistaDecision(d: DecisionMus): VistaDecision {
  const v = d.ventaja;
  const comun = { ventaja: v, radio: d.radio, pMusDespues: d.pMusDespues, repartos: d.repartos };
  if (d.decision === "indiferente" || Math.abs(v) < UMBRAL_IGUAL) {
    const siAcaso = d.decision === "indiferente" ? "" : ` Si acaso, ${v > 0 ? "da mus" : "corta"}.`;
    return {
      ...comun,
      veredicto: "igual",
      intensidad: "igual",
      titulo: "Da igual",
      etiqueta: "",
      matiz: MATIZ_AJUSTADA,
      explicacion: `Cortar y dar mus valen prácticamente lo mismo: la diferencia es de ${tantosPorMano(v)}.${siAcaso}`,
    };
  }
  const mus = v > 0;
  const intensidad: Intensidad = Math.abs(v) >= UMBRAL_CLARA ? "clara" : "por-poco";
  return {
    ...comun,
    veredicto: mus ? "mus" : "corta",
    intensidad,
    titulo: mus ? "Da mus" : "Corta",
    etiqueta: intensidad === "clara" ? "Claro" : "Por poco",
    matiz: intensidad === "clara" ? "" : MATIZ_AJUSTADA,
    explicacion: `${mus ? "Si das mus" : "Si cortas"}, tu pareja saca de media ${tantosPorMano(v, true)} que ${mus ? "si cortas" : "si das mus"}.`,
  };
}

// --- Descartes ---------------------------------------------------------------------------

export interface VistaOpcion {
  readonly valor: ValorOpcion;
  readonly titulo: string;
  readonly detalle: string;
  /** La mejor opción o prácticamente igual de buena. */
  readonly mejor: boolean;
  readonly casiIgual: boolean;
  /** "0,05 tantos peor por mano", "casi igual"... */
  readonly comparacion: string;
  readonly distribucion: Distribucion;
  /** Probabilidades de cada jugada con la mano final. */
  readonly resumen: ResumenDistribucion;
}

export function vistaDescartes(valores: readonly ValorOpcion[], mano: Conteos): VistaOpcion[] {
  return valores.map((valor, i) => {
    const texto = textoOpcion(valor.opcion);
    const distribucion = distribucionTrasDescarte(mano, valor.opcion);
    const casiIgual = i > 0 &&
      (Math.abs(valor.diferencia) <= valor.radio || Math.abs(valor.diferencia) < UMBRAL_DESCARTE);
    const comparacion = i === 0
      ? "La mejor"
      : casiIgual
        ? "Casi igual que la mejor"
        : `Peor: pierdes ${tantosPorMano(valor.diferencia)}`;
    return {
      valor,
      titulo: texto.titulo,
      detalle: texto.detalle,
      mejor: i === 0,
      casiIgual,
      comparacion,
      distribucion,
      resumen: resumenDistribucion(distribucion),
    };
  });
}

/** Frases sobre la mano que se tendrá tras pedir cartas. */
export function frasesResumen(r: ResumenDistribucion): string[] {
  return [
    `Pares: ${porcentaje(r.pares)} (${frecuencia(r.pares)})`,
    `Juego: ${porcentaje(r.juego)} (${frecuencia(r.juego)})`,
    `31: ${porcentaje(r.juego31)}`,
  ];
}

// --- Probabilidades de ganar ---------------------------------------------------------------

const NOMBRES_LANCE: Readonly<Record<Lance, { nombre: string; con: string }>> = {
  grande: { nombre: "Grande", con: "la grande" },
  chica: { nombre: "Chica", con: "la chica" },
  pares: { nombre: "Pares", con: "los pares" },
  juego: { nombre: "Juego", con: "el juego" },
  punto: { nombre: "Punto", con: "el punto" },
};

export interface VistaLance {
  readonly lance: Lance;
  readonly nombre: string;
  /** Probabilidad de que gane mi pareja (yo o mi compañero). */
  readonly pareja: number;
  /** Probabilidad de ganarlo yo. */
  readonly yo: number;
  readonly seJuega: number;
  /** No se juega seguro (el punto, si tienes juego). */
  readonly sinJugar: boolean;
  /** "Ganáis la grande unas 7 de cada 10 veces". */
  readonly frase: string;
  /** La frecuencia de ganarlo la pareja en corto: "7 de 10". */
  readonly frecuenciaCorta: string;
  /** Aclaración para el punto o los lances que pueden no jugarse. */
  readonly nota: string;
  readonly tantos: number;
}

export interface VistaProbabilidades {
  readonly lances: readonly VistaLance[];
  readonly tantos: number;
  /** "Tu pareja saca de media 1,2 tantos más que la otra en esta mano (sin envites)". */
  readonly fraseTantos: string;
}

export function vistaProbabilidades(e: EquityMano, mano: Conteos): VistaProbabilidades {
  const tengoJuego = suma(mano) >= 31;
  const lances = LANCES.map((lance): VistaLance => {
    const x = e[lance];
    const { nombre, con } = NOMBRES_LANCE[lance];
    let nota = "";
    if (lance === "punto") {
      nota = tengoJuego ? "" : `Solo se juega si nadie tiene juego (${frecuencia(x.seJuega)}).`;
    } else if ((lance === "pares" || lance === "juego") && x.seJuega < 0.995) {
      nota = `Nadie lleva ${lance === "pares" ? "pares" : "juego"} ${frecuencia(1 - x.seJuega)}.`;
    }
    const frase = lance === "punto" && tengoJuego
      ? "No hay punto: tienes juego."
      : `Ganáis ${con} ${frecuencia(x.ganaPareja)}.`;
    const sinJugar = x.seJuega === 0;
    return {
      lance,
      nombre,
      pareja: x.ganaPareja,
      yo: x.ganaIndividual,
      seJuega: x.seJuega,
      sinJugar,
      frase,
      frecuenciaCorta: sinJugar ? "no se juega" : frecuenciaCorta(x.ganaPareja),
      nota,
      tantos: x.tantos,
    };
  });
  const tantos = tantosTotales(e);
  const fraseTantos = Math.abs(tantos) < 0.05
    ? "En tantos, esta mano está equilibrada entre las dos parejas (sin envites)."
    : `${tantos > 0 ? "Tu pareja" : "La otra pareja"} saca de media unos ${HASTA_UN_DECIMAL.format(Math.abs(tantos))} tantos más en esta mano (sin envites).`;
  return { lances, tantos, fraseTantos };
}

/**
 * Probabilidad de ganar cada lance tras el mus si me descarto así: se
 * pondera la tabla de la mesa tras el mus por la probabilidad exacta de cada
 * mano final.
 */
export function probabilidadesTrasDescarte(
  distribucion: Distribucion,
  trasMus: readonly Entero[],
  escalas: Manifiesto["escalas"],
  posicion: number,
): Readonly<Record<Lance, number>> | null {
  const porMano = new Map<number, EquityMano | null>();
  for (const indice of distribucion.numeradores.keys()) {
    porMano.set(indice, equityDe(trasMus, escalas, indice, posicion));
  }
  if ([...porMano.values()].some((e) => e === null)) return null;
  const resultado: Partial<Record<Lance, number>> = {};
  for (const lance of LANCES) {
    resultado[lance] = esperanza(distribucion, (i) => porMano.get(i)?.[lance].ganaPareja ?? 0);
  }
  return resultado as Record<Lance, number>;
}
