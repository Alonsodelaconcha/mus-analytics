/**
 * Una serie del entrenador: unas cuantas situaciones seguidas y, al final, el
 * resumen. Como `mano.ts`, es un *reducer* puro: las reglas se prueban sin
 * pintar nada.
 *
 * Cada situación tiene dos momentos: la pregunta y, tras responder, la
 * valoración. Mientras se ve la valoración no se puede volver a responder (un
 * segundo toque no cuenta), y «Siguiente» pasa a la pregunta que toca o, tras
 * la última, al resumen.
 */

import { type Modo, type Situacion } from "./situaciones";
import { type RespuestaCorte, type ValoracionCorte } from "./valoracion";

/** Situaciones de una serie. */
export const SITUACIONES_POR_SERIE = 10;

/** Una situación ya respondida, con lo que valía cada respuesta. */
export interface Contestada {
  readonly situacion: Situacion;
  readonly respuesta: RespuestaCorte;
  readonly valoracion: ValoracionCorte;
}

export type EstadoSerie =
  | { readonly fase: "inicio" }
  | {
    readonly fase: "serie";
    readonly modo: Modo;
    readonly situaciones: readonly Situacion[];
    readonly contestadas: readonly Contestada[];
    /** Se está viendo la valoración de la última respuesta. */
    readonly valorando: boolean;
  }
  | { readonly fase: "resumen"; readonly modo: Modo; readonly contestadas: readonly Contestada[] };

export type AccionSerie =
  | { readonly tipo: "empezar"; readonly modo: Modo; readonly situaciones: readonly Situacion[] }
  | { readonly tipo: "responder"; readonly respuesta: RespuestaCorte; readonly valoracion: ValoracionCorte }
  | { readonly tipo: "siguiente" }
  | { readonly tipo: "salir" };

export const SERIE_INICIAL: EstadoSerie = { fase: "inicio" };

/** La situación que se está preguntando o valorando (`null` fuera de una serie). */
export function situacionActual(estado: EstadoSerie): Situacion | null {
  if (estado.fase !== "serie") return null;
  const numero = estado.valorando ? estado.contestadas.length - 1 : estado.contestadas.length;
  return estado.situaciones[numero] ?? null;
}

/** La respuesta que se está valorando (`null` si se está preguntando). */
export function contestadaActual(estado: EstadoSerie): Contestada | null {
  return estado.fase === "serie" && estado.valorando ? (estado.contestadas.at(-1) ?? null) : null;
}

export function reducirSerie(estado: EstadoSerie, accion: AccionSerie): EstadoSerie {
  switch (accion.tipo) {
    case "empezar":
      // Sin situaciones (un modo que no plantea ninguna) no hay serie que empezar.
      return accion.situaciones.length === 0
        ? estado
        : { fase: "serie", modo: accion.modo, situaciones: accion.situaciones, contestadas: [], valorando: false };
    case "responder": {
      const situacion = situacionActual(estado);
      if (estado.fase !== "serie" || estado.valorando || situacion === null) return estado;
      const contestada = { situacion, respuesta: accion.respuesta, valoracion: accion.valoracion };
      return { ...estado, contestadas: [...estado.contestadas, contestada], valorando: true };
    }
    case "siguiente":
      if (estado.fase !== "serie" || !estado.valorando) return estado;
      return estado.contestadas.length >= estado.situaciones.length
        ? { fase: "resumen", modo: estado.modo, contestadas: estado.contestadas }
        : { ...estado, valorando: false };
    case "salir":
      return SERIE_INICIAL;
  }
}
