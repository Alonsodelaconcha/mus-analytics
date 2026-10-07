/**
 * Carga, validación y lectura de los datos que genera `python -m mus exportar-web`.
 *
 * Al cargar se comprueba que los datos son los que espera este núcleo:
 * - el formato y las reglas del manifiesto;
 * - que las 330 manos y las 3 546 opciones de descarte van en el mismo orden
 *   que las calcula el núcleo (los arrays se indexan por posición, así que un
 *   desajuste daría cifras de otra mano sin ningún error visible);
 * - la huella SHA-256 de cada fichero, que detecta ficheros a medio descargar
 *   o de otra versión guardados en la caché del navegador.
 *
 * Los números vienen como enteros escalados (ver `escalas`) en arrays planos;
 * las funciones `...De` los traducen a valores reales para una mano y posición.
 */

import { type Conteos } from "./cartas";
import { type OpcionDescarte, opcionesDescarte } from "./descarte";
import { LANCES, type Lance, REGLAS_POR_DEFECTO } from "./evaluacion";
import { tabla } from "./tablas";

export const FORMATO = 1;
export const POSICIONES = [1, 2, 3, 4] as const;
export type Posicion = (typeof POSICIONES)[number];
export const METRICAS_EQUITY = ["se_juega", "gana_individual", "gana_pareja", "tantos"] as const;
const N_MANOS = 330;

export class ErrorDatos extends Error {
  override name = "ErrorDatos";
}

// --- Tipos de los ficheros -------------------------------------------------------------

export type Entero = number | null;

export interface SenaDatos {
  readonly id: string;
  readonly nombre: string;
  readonly cartas: string;
  readonly gesto: string;
  /** Manos del compañero compatibles con la seña. */
  readonly manos: readonly number[];
}

export interface TablaEquityDatos {
  readonly id: string;
  /** Combinación canónica de señas; vacía en la tabla sin información. */
  readonly senas: readonly string[];
  readonly manos?: readonly number[];
  readonly fichero: string;
}

export interface MesaDatos {
  readonly id: string;
  readonly nombre: string;
  readonly descripcion: string;
  readonly factor_corte: number;
  readonly p_hay_mus: number;
  readonly por_defecto: boolean;
  readonly fichero: string;
}

export interface Manifiesto {
  readonly formato: number;
  readonly nombre: string;
  readonly generado: string;
  readonly versiones: Readonly<Record<string, string>>;
  readonly reglas: {
    readonly variante: string;
    readonly orden_juego: readonly number[];
    readonly treinta_y_una_real: boolean;
    readonly puntuacion: Readonly<Record<string, number>>;
    readonly descarte: { readonly minimo: number; readonly maximo: number };
  };
  readonly calculo: { readonly repartos_decision: number; readonly repartos_refinado: number };
  readonly posiciones: readonly { readonly numero: number; readonly nombre: string }[];
  readonly lances: readonly string[];
  readonly metricas_equity: readonly string[];
  readonly escalas: { readonly probabilidad: number; readonly tantos: number };
  readonly manos: readonly string[];
  readonly descartes: { readonly inicio: readonly number[]; readonly conservadas: readonly number[] };
  readonly senas: readonly SenaDatos[];
  readonly tablas_equity: readonly TablaEquityDatos[];
  readonly mesas: readonly MesaDatos[];
  readonly ficheros: Readonly<Record<string, { readonly bytes: number; readonly sha256: string }>>;
}

export interface FicheroEquity {
  readonly formato: number;
  readonly condicion: { readonly senas: readonly string[]; readonly manos: readonly number[] } | null;
  /** Orden (mano, posición, lance, métrica). */
  readonly datos: readonly Entero[];
}

export interface FicheroMesa {
  readonly formato: number;
  readonly mesa: { readonly id: string; readonly factor_corte: number; readonly p_hay_mus: number };
  /** Arrays en orden (mano, posición). */
  readonly decision: {
    readonly decision: readonly Entero[];
    readonly ventaja: readonly Entero[];
    readonly radio: readonly Entero[];
    readonly cortar: readonly Entero[];
    readonly mus: readonly Entero[];
    readonly p_mus_despues: readonly Entero[];
    readonly n_efectivo: readonly Entero[];
    readonly repartos: readonly Entero[];
  };
  /** Arrays en orden (posición, opción), con las opciones en el orden de `manifiesto.descartes`. */
  readonly opciones: {
    readonly si_hay_mus: readonly Entero[];
    readonly diferencia: readonly Entero[];
    readonly radio: readonly Entero[];
  };
  readonly tras_mus: { readonly datos: readonly Entero[]; readonly error_tantos: readonly Entero[] };
}

// --- Validación ------------------------------------------------------------------------

function esObjeto(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function campo(objeto: unknown, nombre: string, ruta: string): unknown {
  if (!esObjeto(objeto) || !(nombre in objeto)) {
    throw new ErrorDatos(`Falta «${nombre}» en ${ruta}`);
  }
  return objeto[nombre];
}

function enteros(v: unknown, ruta: string, longitud: number): readonly Entero[] {
  if (!Array.isArray(v) || v.length !== longitud) {
    throw new ErrorDatos(`${ruta} debe ser una lista de ${longitud} números`);
  }
  for (const x of v) {
    if (x !== null && !Number.isInteger(x)) {
      throw new ErrorDatos(`${ruta} contiene un valor que no es entero: ${String(x)}`);
    }
  }
  return v as Entero[];
}

function iguales(a: readonly unknown[], b: readonly unknown[]): boolean {
  return a.length === b.length && a.every((x, i) => x === b[i]);
}

const N_EQUITY = N_MANOS * POSICIONES.length * LANCES.length * METRICAS_EQUITY.length;

/**
 * Comprueba que el manifiesto corresponde a este núcleo y lo devuelve tipado.
 *
 * @throws ErrorDatos con el primer problema encontrado.
 */
export function validarManifiesto(v: unknown): Manifiesto {
  try {
    return comprobarManifiesto(v);
  } catch (error) {
    if (error instanceof ErrorDatos) {
      throw error;
    }
    // Un campo que falta o de otro tipo llega aquí como TypeError.
    throw new ErrorDatos(`El manifiesto está mal formado: ${String(error)}`);
  }
}

function comprobarManifiesto(v: unknown): Manifiesto {
  if (campo(v, "formato", "el manifiesto") !== FORMATO) {
    throw new ErrorDatos(`Formato de datos no compatible (se esperaba el ${FORMATO})`);
  }
  const m = v as Manifiesto;
  const reglas = m.reglas;
  if (
    reglas.variante !== "8reyes" ||
    reglas.treinta_y_una_real ||
    !iguales(reglas.orden_juego, REGLAS_POR_DEFECTO.ordenJuego) ||
    Object.entries(REGLAS_POR_DEFECTO.puntuacion).some(([k, x]) => reglas.puntuacion[k] !== x) ||
    reglas.descarte.minimo !== 1 ||
    reglas.descarte.maximo !== 4
  ) {
    throw new ErrorDatos("Los datos se generaron con otras reglas distintas de las de la web");
  }
  if (!iguales(m.lances, LANCES) || !iguales(m.metricas_equity, METRICAS_EQUITY)) {
    throw new ErrorDatos("Los lances o las métricas no van en el orden esperado");
  }
  if (!iguales(m.posiciones.map((p) => p.numero), POSICIONES)) {
    throw new ErrorDatos("Las posiciones no son 1, 2, 3 y 4");
  }
  if (!iguales(m.manos, tabla().textos)) {
    throw new ErrorDatos("Las manos de los datos no van en el mismo orden que las del núcleo");
  }
  const { inicio, conservadas } = descartesDelNucleo();
  if (!iguales(m.descartes.inicio, inicio) || !iguales(m.descartes.conservadas, conservadas)) {
    throw new ErrorDatos("Las opciones de descarte no coinciden con las del núcleo");
  }
  for (const s of m.senas) {
    if (s.manos.some((i) => !Number.isInteger(i) || i < 0 || i >= N_MANOS)) {
      throw new ErrorDatos(`La seña «${s.id}» tiene manos fuera de rango`);
    }
  }
  if (m.tablas_equity[0]?.senas.length !== 0) {
    throw new ErrorDatos("La primera tabla de equity debe ser la que no tiene señas");
  }
  if (m.mesas.filter((x) => x.por_defecto).length !== 1) {
    throw new ErrorDatos("Tiene que haber exactamente un tipo de mesa por defecto");
  }
  for (const nombre of [...m.tablas_equity.map((t) => t.fichero), ...m.mesas.map((x) => x.fichero)]) {
    if (!(nombre in m.ficheros)) {
      throw new ErrorDatos(`El fichero ${nombre} no tiene huella en el manifiesto`);
    }
  }
  return m;
}

/** Opciones de descarte de las 330 manos, como las escribe el manifiesto. */
function descartesDelNucleo(): { inicio: number[]; conservadas: number[] } {
  const inicio = [0];
  const conservadas: number[] = [];
  for (const mano of tabla().manos) {
    for (const o of opcionesDescarte(mano)) {
      conservadas.push(o.codigo);
    }
    inicio.push(conservadas.length);
  }
  return { inicio, conservadas };
}

export function validarFicheroEquity(v: unknown, ruta: string): FicheroEquity {
  if (campo(v, "formato", ruta) !== FORMATO) {
    throw new ErrorDatos(`Formato no compatible en ${ruta}`);
  }
  enteros(campo(v, "datos", ruta), `${ruta}: datos`, N_EQUITY);
  return v as FicheroEquity;
}

export function validarFicheroMesa(v: unknown, ruta: string, manifiesto: Manifiesto): FicheroMesa {
  if (campo(v, "formato", ruta) !== FORMATO) {
    throw new ErrorDatos(`Formato no compatible en ${ruta}`);
  }
  const casos = N_MANOS * POSICIONES.length;
  const nOpciones = POSICIONES.length * manifiesto.descartes.conservadas.length;
  const decision = campo(v, "decision", ruta);
  for (const k of ["decision", "ventaja", "radio", "cortar", "mus", "p_mus_despues", "n_efectivo",
    "repartos"]) {
    enteros(campo(decision, k, `${ruta}: decision`), `${ruta}: decision.${k}`, casos);
  }
  const opciones = campo(v, "opciones", ruta);
  for (const k of ["si_hay_mus", "diferencia", "radio"]) {
    enteros(campo(opciones, k, `${ruta}: opciones`), `${ruta}: opciones.${k}`, nOpciones);
  }
  const trasMus = campo(v, "tras_mus", ruta);
  enteros(campo(trasMus, "datos", `${ruta}: tras_mus`), `${ruta}: tras_mus.datos`, N_EQUITY);
  enteros(campo(trasMus, "error_tantos", `${ruta}: tras_mus`), `${ruta}: tras_mus.error_tantos`,
    casos);
  return v as FicheroMesa;
}

// --- Carga -----------------------------------------------------------------------------

/** Lee un fichero de datos por su ruta relativa (p. ej. con `fetch` en el navegador). */
export type Cargador = (ruta: string) => Promise<ArrayBuffer>;

export async function sha256(contenido: ArrayBuffer): Promise<string> {
  const resumen = await crypto.subtle.digest("SHA-256", contenido);
  return Array.from(new Uint8Array(resumen), (b) => b.toString(16).padStart(2, "0")).join("");
}

function leerJson(contenido: ArrayBuffer, ruta: string): unknown {
  try {
    return JSON.parse(new TextDecoder().decode(contenido));
  } catch {
    throw new ErrorDatos(`${ruta} no es un JSON válido`);
  }
}

/**
 * Los datos de la web: el manifiesto, cargado y validado al crearse, y los
 * demás ficheros, que se cargan la primera vez que se piden y se guardan.
 */
export class Datos {
  private readonly cache = new Map<string, Promise<unknown>>();

  private constructor(
    readonly manifiesto: Manifiesto,
    private readonly cargador: Cargador,
  ) {}

  static async cargar(cargador: Cargador): Promise<Datos> {
    const contenido = await cargador("manifiesto.json");
    return new Datos(validarManifiesto(leerJson(contenido, "manifiesto.json")), cargador);
  }

  /** Tabla de equity del reparto inicial (sin información o con unas señas). */
  equity(t: TablaEquityDatos): Promise<FicheroEquity> {
    return this.fichero(t.fichero, (v) => validarFicheroEquity(v, t.fichero));
  }

  /** Datos de un tipo de mesa por su id (por defecto, el marcado como tal). */
  mesa(id?: string): Promise<FicheroMesa> {
    const info = this.infoMesa(id);
    return this.fichero(info.fichero, (v) => validarFicheroMesa(v, info.fichero, this.manifiesto));
  }

  infoMesa(id?: string): MesaDatos {
    const info = this.manifiesto.mesas.find((x) => (id === undefined ? x.por_defecto : x.id === id));
    if (info === undefined) {
      throw new ErrorDatos(`No hay ningún tipo de mesa «${id ?? "por defecto"}»`);
    }
    return info;
  }

  private fichero<T>(ruta: string, validar: (v: unknown) => T): Promise<T> {
    let promesa = this.cache.get(ruta) as Promise<T> | undefined;
    if (promesa === undefined) {
      promesa = this.descargar(ruta, validar);
      // Si falla, se olvida para que se pueda reintentar (p. ej. al volver la conexión).
      promesa.catch(() => this.cache.delete(ruta));
      this.cache.set(ruta, promesa);
    }
    return promesa;
  }

  private async descargar<T>(ruta: string, validar: (v: unknown) => T): Promise<T> {
    const esperado = this.manifiesto.ficheros[ruta];
    if (esperado === undefined) {
      throw new ErrorDatos(`El fichero ${ruta} no está en el manifiesto`);
    }
    const contenido = await this.cargador(ruta);
    if ((await sha256(contenido)) !== esperado.sha256) {
      throw new ErrorDatos(`${ruta} no coincide con su huella: puede estar incompleto o ser de otra versión`);
    }
    return validar(leerJson(contenido, ruta));
  }
}

// --- Lectura de los arrays ---------------------------------------------------------------

export interface EquityLance {
  /** Probabilidad de que el lance se juegue. */
  readonly seJuega: number;
  /** Probabilidad de ganarlo yo. */
  readonly ganaIndividual: number;
  /** Probabilidad de que lo gane mi pareja (yo o mi compañero). */
  readonly ganaPareja: number;
  /** Tantos esperados en paso, a favor menos en contra. */
  readonly tantos: number;
}

export type EquityMano = Readonly<Record<Lance, EquityLance>>;

function comprobarPosicion(posicion: number): void {
  if (!(POSICIONES as readonly number[]).includes(posicion)) {
    throw new RangeError(`Posición no válida: ${posicion}`);
  }
}

/**
 * Equity de una mano en una posición a partir de un array plano en orden
 * (mano, posición, lance, métrica). `null` si no está disponible (señas
 * imposibles con esta mano).
 */
export function equityDe(
  datos: readonly Entero[],
  escalas: Manifiesto["escalas"],
  indiceMano: number,
  posicion: number,
): EquityMano | null {
  comprobarPosicion(posicion);
  const resultado: Partial<Record<Lance, EquityLance>> = {};
  for (const [l, lance] of LANCES.entries()) {
    const base = ((indiceMano * POSICIONES.length + posicion - 1) * LANCES.length + l) *
      METRICAS_EQUITY.length;
    const valores = datos.slice(base, base + METRICAS_EQUITY.length);
    if (valores.length !== METRICAS_EQUITY.length || valores.some((x) => x === null)) {
      return null;
    }
    const [seJuega, ganaIndividual, ganaPareja, tantos] = valores as number[];
    resultado[lance] = {
      seJuega: (seJuega ?? 0) / escalas.probabilidad,
      ganaIndividual: (ganaIndividual ?? 0) / escalas.probabilidad,
      ganaPareja: (ganaPareja ?? 0) / escalas.probabilidad,
      tantos: (tantos ?? 0) / escalas.tantos,
    };
  }
  return resultado as EquityMano;
}

/** Tantos netos esperados sumando los cinco lances. */
export function tantosTotales(e: EquityMano): number {
  return LANCES.reduce((t, l) => t + e[l].tantos, 0);
}

export type Decision = "mus" | "cortar" | "indiferente";
const DECISIONES: Readonly<Record<number, Decision>> = { 1: "mus", [-1]: "cortar", 0: "indiferente" };

export interface DecisionMus {
  /** "indiferente" si el intervalo de confianza de la ventaja contiene el 0. */
  readonly decision: Decision;
  /** Dar mus − cortar, en tantos por mano. */
  readonly ventaja: number;
  /** Semiamplitud del intervalo de confianza del 95 % de la ventaja. */
  readonly radio: number;
  readonly cortar: number;
  readonly mus: number;
  /** Probabilidad de que den mus todos los que hablan después. */
  readonly pMusDespues: number;
  readonly nEfectivo: number;
  readonly repartos: number;
}

/** ¿Mus o corto? para una mano y posición en un tipo de mesa (`null` si no está calculado). */
export function decisionDe(
  mesa: FicheroMesa,
  escalas: Manifiesto["escalas"],
  indiceMano: number,
  posicion: number,
): DecisionMus | null {
  comprobarPosicion(posicion);
  const k = indiceMano * POSICIONES.length + posicion - 1;
  const d = mesa.decision;
  const leer = (a: readonly Entero[]): number | null => a[k] ?? null;
  const codigo = leer(d.decision);
  const ventaja = leer(d.ventaja);
  if (codigo === null || ventaja === null) {
    return null;
  }
  const decision = DECISIONES[codigo];
  if (decision === undefined) {
    throw new ErrorDatos(`Código de decisión desconocido: ${codigo}`);
  }
  return {
    decision,
    ventaja: ventaja / escalas.tantos,
    radio: (leer(d.radio) ?? Number.NaN) / escalas.tantos,
    cortar: (leer(d.cortar) ?? Number.NaN) / escalas.tantos,
    mus: (leer(d.mus) ?? Number.NaN) / escalas.tantos,
    pMusDespues: (leer(d.p_mus_despues) ?? Number.NaN) / escalas.probabilidad,
    nEfectivo: leer(d.n_efectivo) ?? 0,
    repartos: leer(d.repartos) ?? 0,
  };
}

export interface ValorOpcion {
  readonly opcion: OpcionDescarte;
  /** Tantos esperados si hay mus y me descarto así. */
  readonly siHayMus: number;
  /** Esta opción menos la mejor (≤ 0; 0 en la mejor). */
  readonly diferencia: number;
  /** Semiamplitud del IC 95 % de la diferencia (con los mismos repartos para todas). */
  readonly radio: number;
}

/**
 * Valor de cada forma de descartarse si hay mus, de mejor a peor. Vacío si no
 * está calculado (o si con esa mano y posición nunca llega a haber mus).
 */
export function opcionesDe(
  mesa: FicheroMesa,
  manifiesto: Manifiesto,
  mano: Conteos,
  indiceMano: number,
  posicion: number,
): ValorOpcion[] {
  comprobarPosicion(posicion);
  const { inicio, conservadas } = manifiesto.descartes;
  const desde = inicio[indiceMano] ?? 0;
  const opciones = opcionesDescarte(mano);
  const base = (posicion - 1) * conservadas.length + desde;
  const resultado: ValorOpcion[] = [];
  for (const [i, opcion] of opciones.entries()) {
    if (conservadas[desde + i] !== opcion.codigo) {
      throw new ErrorDatos("Las opciones de descarte de los datos no coinciden con las del núcleo");
    }
    const valor = mesa.opciones.si_hay_mus[base + i] ?? null;
    const diferencia = mesa.opciones.diferencia[base + i] ?? null;
    const radio = mesa.opciones.radio[base + i] ?? null;
    if (valor === null || diferencia === null || radio === null) {
      continue;
    }
    resultado.push({
      opcion,
      siHayMus: valor / manifiesto.escalas.tantos,
      diferencia: diferencia / manifiesto.escalas.tantos,
      radio: radio / manifiesto.escalas.tantos,
    });
  }
  return resultado.sort((a, b) => b.siHayMus - a.siHayMus);
}

/** Error típico de los tantos totales tras el mus de una mano final (simulación). */
export function errorTrasMusDe(mesa: FicheroMesa, escalas: Manifiesto["escalas"], indiceMano: number,
  posicion: number): number | null {
  comprobarPosicion(posicion);
  const v = mesa.tras_mus.error_tantos[indiceMano * POSICIONES.length + posicion - 1] ?? null;
  return v === null ? null : v / escalas.tantos;
}
