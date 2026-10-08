/**
 * Estado de la mano que se está jugando y cómo cambia con cada acción.
 *
 * Es una función pura (un *reducer* de React), así que las reglas se pueden
 * probar sin pintar nada. La más delicada es el giro de la posición: en la
 * mesa del usuario la mano pasa al jugador de la derecha en cada mano, así que
 * con "Nueva mano" la posición cambia mano → postre, segundo → mano,
 * tercero → segundo y postre → tercero. Solo gira con "Nueva mano", y el giro
 * se anuncia para poder corregirlo con un toque.
 */

export interface Giro {
  /** Posición antes del primer giro sin corregir. */
  readonly desde: number;
  /** "Nueva mano" seguidas sin completar una mano ni tocar la posición. */
  readonly veces: number;
}

export interface EstadoMano {
  /** Rangos de las cartas, en el orden en que se han metido. */
  readonly cartas: readonly number[];
  /** 1 = mano … 4 = postre; `null` hasta que el jugador la elige. */
  readonly posicion: number | null;
  readonly huboMus: boolean;
  readonly senas: readonly string[];
  /** Último giro automático, mientras no se haya confirmado o corregido. */
  readonly giro: Giro | null;
}

export type Accion =
  | { readonly tipo: "poner"; readonly rango: number }
  | { readonly tipo: "quitar"; readonly rango: number }
  | { readonly tipo: "borrar" }
  | { readonly tipo: "nueva-mano" }
  | { readonly tipo: "posicion"; readonly posicion: number }
  | { readonly tipo: "mus"; readonly si: boolean }
  | { readonly tipo: "senas"; readonly ids: readonly string[] };

export const ESTADO_INICIAL: EstadoMano = { cartas: [], posicion: null, huboMus: false, senas: [], giro: null };

/** La mano pasa al de la derecha: mano → postre, segundo → mano, tercero → segundo, postre → tercero. */
export function siguientePosicion(posicion: number): number {
  return posicion === 1 ? 4 : posicion - 1;
}

export function reducirMano(estado: EstadoMano, accion: Accion): EstadoMano {
  switch (accion.tipo) {
    case "poner": {
      if (estado.cartas.length >= 4) return estado;
      const cartas = [...estado.cartas, accion.rango];
      // Con la mano completa, el giro se da por visto (la posición sale en los resultados).
      return { ...estado, cartas, giro: cartas.length === 4 ? null : estado.giro };
    }
    case "quitar": {
      const i = estado.cartas.lastIndexOf(accion.rango);
      if (i < 0) return estado;
      return { ...estado, cartas: [...estado.cartas.slice(0, i), ...estado.cartas.slice(i + 1)] };
    }
    case "borrar":
      return { ...estado, cartas: estado.cartas.slice(0, -1) };
    case "nueva-mano": {
      const { posicion } = estado;
      const giro = posicion === null
        ? null
        : { desde: estado.giro?.desde ?? posicion, veces: (estado.giro?.veces ?? 0) + 1 };
      return {
        cartas: [],
        senas: [],
        huboMus: false,
        posicion: posicion === null ? null : siguientePosicion(posicion),
        giro,
      };
    }
    case "posicion":
      return { ...estado, posicion: accion.posicion, giro: null };
    case "mus":
      // Tras el mus la mano siempre es otra (hay que tirar al menos una carta): se
      // vacía. Las señas no se usan tras el mus. La posición no cambia.
      if (accion.si === estado.huboMus) return estado;
      return { ...estado, huboMus: accion.si, cartas: [], senas: accion.si ? [] : estado.senas };
    case "senas":
      return { ...estado, senas: [...accion.ids] };
  }
}
