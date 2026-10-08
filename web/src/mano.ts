/**
 * Estado de la mano que se está jugando y cómo cambia con cada acción.
 *
 * Es una función pura (un *reducer* de React), así que las reglas se pueden
 * probar sin pintar nada. Hay dos delicadas:
 *
 * - **El giro de la posición.** En la mesa del usuario la mano pasa al jugador
 *   de la derecha en cada mano, así que con "Nueva mano" la posición cambia
 *   mano → postre, segundo → mano, tercero → segundo y postre → tercero. Solo
 *   gira con "Nueva mano", y el giro se anuncia para poder corregirlo con un toque.
 * - **Las pestañas**, una por momento de la mano: «¿Mus o corto?» y «Se ha
 *   cortado» usan las cartas del reparto; «Ha habido mus», las de después del
 *   mus. Al pasar a «Ha habido mus», la mano repartida (con las señas) se guarda
 *   y se restaura si se vuelve a otra pestaña, por si fue un toque equivocado.
 */

export type Pestana = "decidir" | "cortado" | "mus";

export interface Giro {
  /** Posición antes del primer giro sin corregir. */
  readonly desde: number;
  /** "Nueva mano" seguidas sin completar una mano ni tocar la posición. */
  readonly veces: number;
}

export interface EstadoMano {
  readonly pestana: Pestana;
  /** Cartas del reparto (rangos, en el orden en que se han metido). */
  readonly reparto: readonly number[];
  /** Señas del compañero. Son sobre el reparto: no se usan tras el mus. */
  readonly senas: readonly string[];
  /** Cartas después del mus: solo en «Ha habido mus», que empieza siempre vacía. */
  readonly trasMus: readonly number[];
  /** 1 = mano … 4 = postre; `null` hasta que el jugador la elige. */
  readonly posicion: number | null;
  /** Último giro automático, mientras no se haya confirmado o corregido. */
  readonly giro: Giro | null;
}

export type Accion =
  | { readonly tipo: "poner"; readonly rango: number }
  | { readonly tipo: "quitar"; readonly rango: number }
  | { readonly tipo: "borrar" }
  | { readonly tipo: "nueva-mano" }
  | { readonly tipo: "posicion"; readonly posicion: number }
  | { readonly tipo: "pestana"; readonly pestana: Pestana }
  | { readonly tipo: "senas"; readonly ids: readonly string[] };

export const ESTADO_INICIAL: EstadoMano = {
  pestana: "decidir",
  reparto: [],
  senas: [],
  trasMus: [],
  posicion: null,
  giro: null,
};

/** La mano pasa al de la derecha: mano → postre, segundo → mano, tercero → segundo, postre → tercero. */
export function siguientePosicion(posicion: number): number {
  return posicion === 1 ? 4 : posicion - 1;
}

/** Las cartas que se ven y se editan en la pestaña abierta. */
export function cartasDe(estado: EstadoMano): readonly number[] {
  return estado.pestana === "mus" ? estado.trasMus : estado.reparto;
}

function conCartas(estado: EstadoMano, cartas: readonly number[]): EstadoMano {
  return estado.pestana === "mus" ? { ...estado, trasMus: cartas } : { ...estado, reparto: cartas };
}

export function reducirMano(estado: EstadoMano, accion: Accion): EstadoMano {
  const cartas = cartasDe(estado);
  switch (accion.tipo) {
    case "poner": {
      if (cartas.length >= 4) return estado;
      const nuevas = [...cartas, accion.rango];
      // Con la mano completa, el giro se da por visto (la posición sale en los resultados).
      // Completar la mano nunca cambia de pestaña.
      return { ...conCartas(estado, nuevas), giro: nuevas.length === 4 ? null : estado.giro };
    }
    case "quitar": {
      const i = cartas.lastIndexOf(accion.rango);
      if (i < 0) return estado;
      return conCartas(estado, [...cartas.slice(0, i), ...cartas.slice(i + 1)]);
    }
    case "borrar":
      return cartas.length === 0 ? estado : conCartas(estado, cartas.slice(0, -1));
    case "nueva-mano": {
      const { posicion } = estado;
      const giro = posicion === null
        ? null
        : { desde: estado.giro?.desde ?? posicion, veces: (estado.giro?.veces ?? 0) + 1 };
      return {
        pestana: "decidir",
        reparto: [],
        senas: [],
        trasMus: [],
        posicion: posicion === null ? null : siguientePosicion(posicion),
        giro,
      };
    }
    case "posicion":
      return { ...estado, posicion: accion.posicion, giro: null };
    case "pestana":
      // «Ha habido mus» empieza siempre vacía: tras el mus la mano es otra (hay que
      // tirar al menos una carta). El reparto y sus señas no se tocan: siguen ahí al
      // volver. La posición no cambia.
      if (accion.pestana === estado.pestana) return estado;
      return { ...estado, pestana: accion.pestana, trasMus: [] };
    case "senas":
      return { ...estado, senas: [...accion.ids] };
  }
}
