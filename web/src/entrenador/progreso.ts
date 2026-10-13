/**
 * El progreso del entrenador: un registro de respuestas guardado en el móvil.
 *
 * No hay servidor. Cada respuesta se anota completa, sin depender de nada de
 * fuera: con qué datos y qué versión se valoró, la mesa, la mano escrita, la
 * posición, lo que se respondió, lo que era mejor y los tantos perdidos. No
 * lleva ningún dato de quién responde. Las cifras del progreso se calculan a
 * partir del registro; no se guarda ninguna aparte que pueda desajustarse.
 *
 * Como vive solo en este móvil, se puede sacar a un fichero («Exportar») y
 * volver a meter («Importar»), que une los dos registros sin repetir nada.
 * Si el navegador ofrece almacenamiento persistente, se pide: así no borra el
 * progreso por su cuenta cuando le falta espacio.
 */

import { type Intensidad } from "../vista/vista";
import { type Ejercicio, EJERCICIOS, MODOS } from "./situaciones";
import { MILESIMAS } from "./valoracion";

export const FORMATO_PROGRESO = 1;
export const CLAVE_PROGRESO = "mus-analytics.progreso";

/** Modos con que se puede haber planteado una situación (el repaso llega con el paso 4). */
export const MODOS_ANOTADOS = [...MODOS, "repaso"] as const;
export type ModoAnotado = (typeof MODOS_ANOTADOS)[number];

const INTENSIDADES: readonly Intensidad[] = ["clara", "por-poco", "igual"];

/** Una respuesta a una situación del entrenador. */
export interface Anotacion {
  /** Cuándo se respondió: milisegundos desde 1970 (UTC). */
  readonly fecha: number;
  readonly ejercicio: Ejercicio;
  readonly modo: ModoAnotado;
  /** Id del tipo de mesa. */
  readonly mesa: string;
  /** La mano, escrita de mayor a menor: "R C 5 4". */
  readonly mano: string;
  /** 1 = mano … 4 = postre. */
  readonly posicion: number;
  /** «¿Mus o corto?»: "mus" o "corta". «¿Qué tiras?»: las cartas con que se queda ("" = ninguna). */
  readonly respuesta: string;
  /** La mejor respuesta, escrita igual; "igual" si daba igual cortar que dar mus. */
  readonly mejor: string;
  /** Cómo de clara era la decisión. */
  readonly intensidad: Intensidad;
  /** Milésimas de tanto perdidas frente a la mejor opción (0 si se acertó o daba igual). */
  readonly perdidos: number;
  /** Fecha de los datos con que se valoró (`manifiesto.generado`). */
  readonly datos: string;
  /** Versión de la web con que se valoró. */
  readonly web: string;
}

function esObjeto(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

const esTexto = (v: unknown, maximo: number): v is string => typeof v === "string" && v.length <= maximo;
const esEntero = (v: unknown, minimo: number, maximo: number): v is number =>
  typeof v === "number" && Number.isInteger(v) && v >= minimo && v <= maximo;

/** Comprueba, campo a campo, que algo leído de fuera es una anotación. */
export function esAnotacion(v: unknown): v is Anotacion {
  return esObjeto(v) &&
    esEntero(v.fecha, 0, Number.MAX_SAFE_INTEGER) &&
    (EJERCICIOS as readonly unknown[]).includes(v.ejercicio) &&
    (MODOS_ANOTADOS as readonly unknown[]).includes(v.modo) &&
    esTexto(v.mesa, 40) && v.mesa !== "" &&
    esTexto(v.mano, 7) && /^[RCS7654A]( [RCS7654A]){3}$/.test(v.mano) &&
    esEntero(v.posicion, 1, 4) &&
    esTexto(v.respuesta, 7) &&
    esTexto(v.mejor, 7) &&
    (INTENSIDADES as readonly unknown[]).includes(v.intensidad) &&
    esEntero(v.perdidos, 0, 100 * MILESIMAS) &&
    esTexto(v.datos, 20) &&
    esTexto(v.web, 20);
}

/** Deja solo los campos de una anotación, en un orden fijo. */
function limpia(a: Anotacion): Anotacion {
  return {
    fecha: a.fecha,
    ejercicio: a.ejercicio,
    modo: a.modo,
    mesa: a.mesa,
    mano: a.mano,
    posicion: a.posicion,
    respuesta: a.respuesta,
    mejor: a.mejor,
    intensidad: a.intensidad,
    perdidos: a.perdidos,
    datos: a.datos,
    web: a.web,
  };
}

// --- Dónde se guarda -------------------------------------------------------------------

/** Un sitio donde guardar un texto: `localStorage` en la web, la memoria en los tests. */
export interface Almacen {
  leer(clave: string): string | null;
  /** `false` si no se ha podido guardar (sin sitio, modo privado...). */
  guardar(clave: string, texto: string): boolean;
}

/** El almacenamiento del navegador. Si no deja leer o escribir, no falla: lo dice. */
export const ALMACEN_LOCAL: Almacen = {
  leer(clave) {
    try {
      return localStorage.getItem(clave);
    } catch {
      return null;
    }
  },
  guardar(clave, texto) {
    try {
      localStorage.setItem(clave, texto);
      return true;
    } catch {
      return false;
    }
  },
};

export function almacenEnMemoria(inicial: Readonly<Record<string, string>> = {}): Almacen {
  const datos = new Map(Object.entries(inicial));
  return {
    leer: (clave) => datos.get(clave) ?? null,
    guardar: (clave, texto) => {
      datos.set(clave, texto);
      return true;
    },
  };
}

type Lectura =
  | { readonly ok: true; readonly anotaciones: Anotacion[] }
  | { readonly ok: false; readonly error: string };

function leerRegistro(texto: string): Lectura {
  let v: unknown;
  try {
    v = JSON.parse(texto);
  } catch {
    return { ok: false, error: "No es un fichero de progreso de Mus Analytics." };
  }
  if (!esObjeto(v) || !Array.isArray(v.anotaciones)) {
    return { ok: false, error: "No es un fichero de progreso de Mus Analytics." };
  }
  if (v.formato !== FORMATO_PROGRESO) {
    return { ok: false, error: "El fichero es de otra versión de Mus Analytics y aquí no se puede leer." };
  }
  const anotaciones = v.anotaciones as unknown[];
  if (!anotaciones.every(esAnotacion)) {
    return { ok: false, error: "El fichero de progreso está dañado: alguna respuesta no se entiende." };
  }
  return { ok: true, anotaciones: anotaciones.map(limpia) };
}

function escribirRegistro(anotaciones: readonly Anotacion[], extra: Readonly<Record<string, unknown>> = {}): string {
  return JSON.stringify({ formato: FORMATO_PROGRESO, ...extra, anotaciones });
}

/**
 * El registro guardado en este móvil (vacío si no hay ninguno).
 *
 * Si lo guardado no se entiende (está dañado o es de una versión posterior),
 * se aparta con otra clave antes de empezar uno nuevo, para no pisarlo.
 */
export function leerProgreso(almacen: Almacen, clave = CLAVE_PROGRESO): Anotacion[] {
  const texto = almacen.leer(clave);
  if (texto === null) return [];
  const lectura = leerRegistro(texto);
  if (lectura.ok) return lectura.anotaciones;
  almacen.guardar(`${clave}.ilegible`, texto);
  return [];
}

/** Añade una respuesta al registro y lo guarda. `guardado` dice si ha quedado en el móvil. */
export function anotar(
  almacen: Almacen,
  anotaciones: readonly Anotacion[],
  nueva: Anotacion,
  clave = CLAVE_PROGRESO,
): { anotaciones: Anotacion[]; guardado: boolean } {
  const todas = [...anotaciones, limpia(nueva)];
  return { anotaciones: todas, guardado: almacen.guardar(clave, escribirRegistro(todas)) };
}

// --- Exportar e importar ----------------------------------------------------------------

/** El registro como texto para guardarlo en un fichero. */
export function exportar(anotaciones: readonly Anotacion[], ahora: number): string {
  return escribirRegistro(anotaciones, {
    aplicacion: "Mus Analytics",
    exportado: new Date(ahora).toISOString(),
  });
}

function identidad(a: Anotacion): string {
  return [a.fecha, a.ejercicio, a.mesa, a.mano, a.posicion, a.respuesta].join("|");
}

export type Importacion =
  | { readonly ok: true; readonly anotaciones: Anotacion[]; readonly nuevas: number; readonly repetidas: number }
  | { readonly ok: false; readonly error: string };

/**
 * Une un registro exportado con el de este móvil. Las respuestas que ya están
 * no se repiten: importar dos veces el mismo fichero no cambia nada. Si el
 * fichero no se entiende, no se toca nada.
 */
export function importar(texto: string, actuales: readonly Anotacion[]): Importacion {
  const lectura = leerRegistro(texto);
  if (!lectura.ok) return lectura;
  const vistas = new Set(actuales.map(identidad));
  const nuevas = lectura.anotaciones.filter((a) => {
    const id = identidad(a);
    if (vistas.has(id)) return false;
    vistas.add(id);
    return true;
  });
  return {
    ok: true,
    anotaciones: [...actuales, ...nuevas].sort((a, b) => a.fecha - b.fecha),
    nuevas: nuevas.length,
    repetidas: lectura.anotaciones.length - nuevas.length,
  };
}

/** Guarda el registro entero (después de importar). */
export function guardarProgreso(almacen: Almacen, anotaciones: readonly Anotacion[], clave = CLAVE_PROGRESO): boolean {
  return almacen.guardar(clave, escribirRegistro(anotaciones));
}

// --- Cifras ---------------------------------------------------------------------------

export interface Resumen {
  /** Respuestas. */
  readonly n: number;
  /** Milésimas de tanto perdidas en total. */
  readonly perdidos: number;
  /** Respuestas sin pérdida: la mejor, o daba igual. */
  readonly bien: number;
  /** Fallos en decisiones claras. */
  readonly fallosClaros: number;
  /** Fallos en decisiones «por poco», que con envites podrían cambiar. */
  readonly fallosPorPoco: number;
}

/** Las cifras de unas respuestas: las de una serie o las de todo el registro. */
export function resumir(anotaciones: readonly Pick<Anotacion, "perdidos" | "intensidad">[]): Resumen {
  let perdidos = 0;
  let bien = 0;
  let fallosClaros = 0;
  let fallosPorPoco = 0;
  for (const a of anotaciones) {
    perdidos += a.perdidos;
    if (a.perdidos === 0) bien++;
    else if (a.intensidad === "clara") fallosClaros++;
    else fallosPorPoco++;
  }
  return { n: anotaciones.length, perdidos, bien, fallosClaros, fallosPorPoco };
}

/** Tantos perdidos de media en cada decisión (0 si no hay ninguna). */
export function tantosPorDecision(r: Resumen): number {
  return r.n === 0 ? 0 : r.perdidos / MILESIMAS / r.n;
}

/**
 * Tantos perdidos por cada 100 manos de partida: lo perdido por decisión, por
 * la fracción de las manos en que se llega a decidir (`decisionesPorMano`).
 * Solo tiene sentido con las situaciones sorteadas «como en la mesa».
 */
export function tantosCadaCienManos(r: Resumen, decisionesPorMano: number): number {
  return 100 * decisionesPorMano * tantosPorDecision(r);
}

// --- Almacenamiento persistente -----------------------------------------------------------

export type Persistencia = "concedida" | "denegada" | "no-disponible";

/** Lo que se usa del gestor de almacenamiento del navegador. */
export interface GestorAlmacenamiento {
  persisted?: () => Promise<boolean>;
  persist?: () => Promise<boolean>;
}

/**
 * El gestor de almacenamiento del navegador, si lo hay. Solo existe en
 * contextos seguros (HTTPS o localhost): por la red local no está.
 */
export function gestorDelNavegador(): GestorAlmacenamiento | undefined {
  if (typeof navigator === "undefined" || !("storage" in navigator)) return undefined;
  // eslint-disable-next-line no-restricted-properties -- se acaba de comprobar que existe
  return navigator.storage;
}

/**
 * Pide al navegador que no borre por su cuenta lo guardado. Si no lo ofrece, o
 * lo deniega, el progreso se guarda igual: solo queda menos protegido.
 */
export async function pedirPersistencia(
  gestor: GestorAlmacenamiento | undefined = gestorDelNavegador(),
): Promise<Persistencia> {
  if (gestor === undefined || typeof gestor.persist !== "function") return "no-disponible";
  try {
    if (typeof gestor.persisted === "function" && await gestor.persisted()) return "concedida";
    return (await gestor.persist()) ? "concedida" : "denegada";
  } catch {
    return "no-disponible";
  }
}
