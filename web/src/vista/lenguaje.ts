/**
 * Cifras y frases en lenguaje de jugador.
 *
 * La web no habla de "equity", "λ" ni "Monte Carlo": habla de probabilidad
 * de ganar, de tantos y de veces de cada diez. Todo lo que se enseña al
 * usuario pasa por aquí, para que el tono sea el mismo en toda la web.
 */

import { type Conteos, N_RANGOS, SIMBOLOS, rangos } from "../nucleo/cartas";
import { type OpcionDescarte } from "../nucleo/descarte";
import { Pares, clavePares, suma } from "../nucleo/evaluacion";

const ENTERO = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 });
const UN_DECIMAL = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const DOS_DECIMALES = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Espacio que no se parte: "62 %" nunca queda con el "%" en otra línea. */
const NBSP = String.fromCharCode(0xa0);

/** Porcentaje redondeado al entero ("62 %"); "<1 %" y ">99 %" en los extremos. */
export function porcentaje(p: number): string {
  if (p > 0 && p < 0.005) return `<1${NBSP}%`;
  if (p < 1 && p > 0.995) return `>99${NBSP}%`;
  return `${ENTERO.format(p * 100)}${NBSP}%`;
}

/**
 * Frecuencia en palabras: "unas 7 de cada 10 veces", "1 de cada 14 veces",
 * "casi siempre"... Se redondea a propósito: es una ayuda para la mesa, no
 * un dato de precisión.
 */
export function frecuencia(p: number): string {
  if (p <= 0) return "nunca";
  if (p >= 1) return "siempre";
  if (p < 0.01) return "casi nunca";
  if (p < 0.095) return `1 de cada ${ENTERO.format(Math.round(1 / p))} veces`;
  if (p >= 0.95) return "casi siempre";
  const deDiez = Math.min(9, Math.max(1, Math.round(p * 10)));
  return deDiez === 1 ? "1 de cada 10 veces" : `unas ${deDiez} de cada 10 veces`;
}

/** Número con signo y decimales fijos ("+1,24", "−0,07"). */
export function conSigno(x: number, decimales: 1 | 2 = 2): string {
  const formato = decimales === 1 ? UN_DECIMAL : DOS_DECIMALES;
  const texto = formato.format(Math.abs(x));
  if (texto === formato.format(0)) return texto;
  return `${x < 0 ? "−" : "+"}${texto}`;
}

export function decimal(x: number, decimales: 1 | 2 = 2): string {
  return (decimales === 1 ? UN_DECIMAL : DOS_DECIMALES).format(x);
}

/** Decimal sin ceros sobrantes: "2", "1,1". */
const HASTA_UN_DECIMAL = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });

/**
 * Una diferencia de tantos por mano, dicha como la notaría un jugador:
 * "unos 3 tantos cada 10 manos", "unos 2,7 tantos por mano"... Con `mas`,
 * la palabra va en su sitio: "unos 3 tantos más cada 10 manos".
 */
export function tantosPorMano(diferencia: number, mas = false): string {
  const d = Math.abs(diferencia);
  const extra = mas ? " más" : "";
  const tantos = (n: number, texto: string): string =>
    n === 1 ? `1 tanto${extra}` : `unos ${texto} tantos${extra}`;
  if (d >= 0.95) return `${tantos(d, HASTA_UN_DECIMAL.format(d))} por mano`;
  const cadaDiez = Math.round(d * 10);
  if (d * 10 >= 0.95) return `${tantos(cadaDiez, ENTERO.format(cadaDiez))} cada 10 manos`;
  const cadaCien = Math.round(d * 100);
  if (cadaCien >= 1) return `${tantos(cadaCien, ENTERO.format(cadaCien))} cada 100 manos`;
  return `menos de 1 tanto${extra} cada 100 manos`;
}

// --- Cartas y jugadas ------------------------------------------------------------------

const SINGULAR = ["as", "cuatro", "cinco", "seis", "siete", "sota", "caballo", "rey"] as const;
const PLURAL = ["ases", "cuatros", "cincos", "seises", "sietes", "sotas", "caballos", "reyes"] as const;
/** Nombre de cada carta en las teclas (el 3 es rey y el 2 es as). */
export const NOMBRES_TECLA = ["As · 2", "Cuatro", "Cinco", "Seis", "Siete", "Sota", "Caballo", "Rey · 3"] as const;

export function nombrePlural(rango: number): string {
  return PLURAL[rango] ?? "?";
}

export function nombreSingular(rango: number): string {
  return SINGULAR[rango] ?? "?";
}

/** Cartas de una mano en texto, de mayor a menor ("R C 5 4"). */
export function cartas(conteos: Conteos): string {
  return rangos(conteos)
    .map((r) => SIMBOLOS[r] ?? "?")
    .join(" ");
}

/** "Par de reyes", "Medias de sotas", "Duples de reyes y ases", "Sin pares". */
export function describirPares(mano: Conteos): string {
  const clave = clavePares(mano);
  if (clave === null) return "Sin pares";
  const [categoria, alto = 0, bajo = 0] = clave;
  switch (categoria) {
    case Pares.PAR:
      return `Par de ${nombrePlural(alto)}`;
    case Pares.MEDIAS:
      return `Medias de ${nombrePlural(alto)}`;
    default:
      return alto === bajo ? `Duples de cuatro ${nombrePlural(alto)}` : `Duples de ${nombrePlural(alto)} y ${nombrePlural(bajo)}`;
  }
}

/** "31 de juego", "Sin juego: 28 al punto". */
export function describirJuego(mano: Conteos): string {
  const s = suma(mano);
  return s >= 31 ? `${s} de juego` : `Sin juego: ${s} al punto`;
}

/** Cartas que se conservan y se tiran en una opción de descarte, y cuántas se piden. */
export interface TextoOpcion {
  /** "Quédate con R C" o "Tíralas todas". */
  readonly titulo: string;
  /** "Pides 2: tiras el 5 y el 4". */
  readonly detalle: string;
  readonly quedo: string;
  readonly tiro: string;
}

const CUANTAS = ["", "", "dos", "tres", "cuatro"] as const;

/** "el cinco y el cuatro", "los dos cuatros", "la sota": cartas iguales agrupadas. */
function lista(descartadas: Conteos): string {
  const grupos: string[] = [];
  for (let r = N_RANGOS - 1; r >= 0; r--) {
    const k = descartadas[r] ?? 0;
    const femenino = SIMBOLOS[r] === "S";
    if (k === 1) {
      grupos.push(`${femenino ? "la" : "el"} ${nombreSingular(r)}`);
    } else if (k > 1) {
      grupos.push(`${femenino ? "las" : "los"} ${CUANTAS[k] ?? String(k)} ${nombrePlural(r)}`);
    }
  }
  if (grupos.length <= 1) return grupos.join("");
  return `${grupos.slice(0, -1).join(", ")} y ${grupos.at(-1) ?? ""}`;
}

export function textoOpcion(opcion: OpcionDescarte): TextoOpcion {
  const quedo = cartas(opcion.conservadas);
  const tiro = cartas(opcion.descartadas);
  const n = opcion.nDescartes;
  const titulo = quedo === "" ? "Tíralas todas" : `Quédate con ${quedo}`;
  const pides = `Pides ${n}`;
  const detalle = n === 4 ? `${pides}: tiras las cuatro` : `${pides}: tiras ${lista(opcion.descartadas)}`;
  return { titulo, detalle, quedo, tiro };
}

/** Conteos vacíos (sin cartas), útiles para empezar una mano. */
export const SIN_CARTAS: Conteos = new Array<number>(N_RANGOS).fill(0);
