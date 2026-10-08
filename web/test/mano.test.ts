import { describe, expect, it } from "vitest";

import {
  type Accion,
  ESTADO_INICIAL,
  type EstadoMano,
  type Pestana,
  cartasDe,
  reducirMano,
  siguientePosicion,
} from "../src/mano";

const aplicar = (estado: EstadoMano, ...acciones: Accion[]) => acciones.reduce(reducirMano, estado);
const enPosicion = (posicion: number) => aplicar(ESTADO_INICIAL, { tipo: "posicion", posicion });
const nueva: Accion = { tipo: "nueva-mano" };
const pestana = (p: Pestana): Accion => ({ tipo: "pestana", pestana: p });
const poner = (...rangos: number[]): Accion[] => rangos.map((rango) => ({ tipo: "poner", rango }));
const PESTANAS: Pestana[] = ["decidir", "cortado", "mus"];

describe("giro de la posición con «Nueva mano»", () => {
  it("mano → postre, segundo → mano, tercero → segundo, postre → tercero", () => {
    expect([1, 2, 3, 4].map(siguientePosicion)).toEqual([4, 1, 2, 3]);
  });

  it.each([1, 2, 3, 4])("cuatro «Nueva mano» seguidas vuelven a la posición inicial (%i)", (p) => {
    const estados = [1, 2, 3, 4].map((n) => aplicar(enPosicion(p), ...Array<Accion>(n).fill(nueva)));
    expect(estados.map((e) => e.posicion)).toEqual([1, 2, 3, 4].map((n) => {
      let q = p;
      for (let i = 0; i < n; i++) q = siguientePosicion(q);
      return q;
    }));
    expect(estados[3]?.posicion).toBe(p);
  });

  it("el giro se anuncia, y se avisa si se pulsa varias veces seguidas", () => {
    const una = aplicar(enPosicion(1), nueva);
    expect(una).toMatchObject({ posicion: 4, giro: { desde: 1, veces: 1 } });
    const dos = aplicar(una, nueva);
    expect(dos).toMatchObject({ posicion: 3, giro: { desde: 1, veces: 2 } });
  });

  it("corregir la posición o completar la mano retira el aviso", () => {
    const girada = aplicar(enPosicion(2), nueva);
    expect(aplicar(girada, { tipo: "posicion", posicion: 2 })).toMatchObject({ posicion: 2, giro: null });
    const jugada = aplicar(girada, ...poner(7, 6, 5, 4));
    expect(jugada.giro).toBeNull();
    // La siguiente "Nueva mano" vuelve a contar desde una.
    expect(aplicar(jugada, nueva).giro).toEqual({ desde: 1, veces: 1 });
  });

  it("sin posición elegida no gira ni avisa", () => {
    expect(aplicar(ESTADO_INICIAL, nueva)).toMatchObject({ posicion: null, giro: null });
  });

  it("los demás controles no giran la posición", () => {
    const inicio = aplicar(enPosicion(3), ...poner(7, 7));
    const acciones: Accion[] = [
      { tipo: "poner", rango: 5 },
      { tipo: "quitar", rango: 7 },
      { tipo: "borrar" },
      pestana("cortado"),
      pestana("mus"),
      pestana("decidir"),
      { tipo: "senas", ids: ["dos-reyes"] },
      { tipo: "senas", ids: [] },
    ];
    for (const accion of acciones) {
      expect(reducirMano(inicio, accion).posicion, accion.tipo).toBe(3);
    }
    expect(aplicar(inicio, ...acciones).posicion).toBe(3);
  });
});

describe("pestañas", () => {
  const repartida = aplicar(enPosicion(2), ...poner(7, 6, 5), { tipo: "senas", ids: ["31"] }, { tipo: "poner", rango: 4 });

  it("se empieza en «¿Mus o corto?», y «Nueva mano» vuelve a ella desde cualquier pestaña", () => {
    expect(ESTADO_INICIAL.pestana).toBe("decidir");
    for (const p of PESTANAS) {
      const e = aplicar(repartida, pestana(p), ...poner(7, 7, 7, 7), nueva);
      expect(e, p).toMatchObject({ pestana: "decidir", reparto: [], senas: [], trasMus: [], posicion: 1 });
    }
  });

  it.each(PESTANAS)("completar las 4 cartas no cambia de pestaña (%s)", (p) => {
    const e = aplicar(enPosicion(1), pestana(p), ...poner(7, 6, 5, 4));
    expect(e.pestana).toBe(p);
    expect(cartasDe(e)).toEqual([7, 6, 5, 4]);
  });

  it("pasar a «Se ha cortado» conserva las cartas y las señas, y volver también", () => {
    const cortado = aplicar(repartida, pestana("cortado"));
    expect(cortado).toMatchObject({ pestana: "cortado", reparto: [7, 6, 5, 4], senas: ["31"] });
    expect(aplicar(cortado, pestana("decidir"))).toMatchObject({ reparto: [7, 6, 5, 4], senas: ["31"] });
  });

  it("pasar a «Ha habido mus» empieza con la mano vacía", () => {
    for (const desde of ["decidir", "cortado"] as const) {
      const mus = aplicar(repartida, pestana(desde), pestana("mus"));
      expect(mus.pestana).toBe("mus");
      expect(cartasDe(mus)).toEqual([]);
    }
  });

  it.each(["decidir", "cortado"] as const)(
    "volver de «Ha habido mus» a «%s» restaura la mano repartida con sus señas",
    (destino) => {
      const mus = aplicar(repartida, pestana("mus"), ...poner(7, 7, 6));
      expect(cartasDe(mus)).toEqual([7, 7, 6]);
      const vuelta = aplicar(mus, pestana(destino));
      expect(vuelta).toMatchObject({ pestana: destino, senas: ["31"], posicion: 2 });
      expect(cartasDe(vuelta)).toEqual([7, 6, 5, 4]);
    },
  );

  it("volver a «Ha habido mus» empieza otra vez vacía", () => {
    const e = aplicar(repartida, pestana("mus"), ...poner(7, 7, 6, 6), pestana("cortado"), pestana("mus"));
    expect(cartasDe(e)).toEqual([]);
  });

  it("en «Ha habido mus», las cartas se meten, quitan y borran sin tocar el reparto", () => {
    const e = aplicar(repartida, pestana("mus"), ...poner(7, 7, 6), { tipo: "quitar", rango: 7 }, { tipo: "borrar" });
    expect(e).toMatchObject({ trasMus: [7], reparto: [7, 6, 5, 4] });
  });

  it("la posición no cambia al cambiar de pestaña", () => {
    let e = repartida;
    for (const p of ["cortado", "mus", "decidir", "mus", "cortado"] as const) {
      e = reducirMano(e, pestana(p));
      expect(e.posicion).toBe(2);
    }
  });

  it("tocar la pestaña abierta no cambia nada", () => {
    const mus = aplicar(repartida, pestana("mus"), ...poner(7));
    expect(reducirMano(mus, pestana("mus"))).toBe(mus);
    expect(reducirMano(repartida, pestana("decidir"))).toBe(repartida);
  });
});

describe("cartas", () => {
  it("no entran más de 4, y quitar borra una de ese rango", () => {
    const e = aplicar(ESTADO_INICIAL, ...poner(7, 7, 6, 5, 4));
    expect(e.reparto).toEqual([7, 7, 6, 5]);
    expect(aplicar(e, { tipo: "quitar", rango: 7 }).reparto).toEqual([7, 6, 5]);
    expect(aplicar(e, { tipo: "quitar", rango: 0 })).toBe(e);
  });

  it("borrar sin cartas no cambia nada", () => {
    expect(reducirMano(ESTADO_INICIAL, { tipo: "borrar" })).toBe(ESTADO_INICIAL);
  });
});
