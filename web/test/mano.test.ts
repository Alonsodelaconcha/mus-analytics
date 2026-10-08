import { describe, expect, it } from "vitest";

import { type Accion, ESTADO_INICIAL, type EstadoMano, reducirMano, siguientePosicion } from "../src/mano";

const aplicar = (estado: EstadoMano, ...acciones: Accion[]) => acciones.reduce(reducirMano, estado);
const enPosicion = (posicion: number) => aplicar(ESTADO_INICIAL, { tipo: "posicion", posicion });
const nueva: Accion = { tipo: "nueva-mano" };

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
    const jugada = aplicar(girada, ...[7, 6, 5, 4].map((rango): Accion => ({ tipo: "poner", rango })));
    expect(jugada.giro).toBeNull();
    // La siguiente "Nueva mano" vuelve a contar desde una.
    expect(aplicar(jugada, nueva).giro).toEqual({ desde: 1, veces: 1 });
  });

  it("sin posición elegida no gira ni avisa", () => {
    expect(aplicar(ESTADO_INICIAL, nueva)).toMatchObject({ posicion: null, giro: null });
  });

  it("los demás controles no giran la posición", () => {
    const inicio = aplicar(enPosicion(3), { tipo: "poner", rango: 7 }, { tipo: "poner", rango: 7 });
    const acciones: Accion[] = [
      { tipo: "poner", rango: 5 },
      { tipo: "quitar", rango: 7 },
      { tipo: "borrar" },
      { tipo: "mus", si: true },
      { tipo: "mus", si: false },
      { tipo: "senas", ids: ["dos-reyes"] },
      { tipo: "senas", ids: [] },
    ];
    for (const accion of acciones) {
      expect(reducirMano(inicio, accion).posicion, accion.tipo).toBe(3);
    }
    expect(aplicar(inicio, ...acciones).posicion).toBe(3);
  });
});

describe("resto de la mano", () => {
  it("«Nueva mano» vacía cartas, señas y «¿Ha habido mus?»", () => {
    const e = aplicar(enPosicion(1), { tipo: "poner", rango: 7 }, { tipo: "senas", ids: ["31"] },
      { tipo: "mus", si: true }, { tipo: "poner", rango: 6 }, nueva);
    expect(e).toMatchObject({ cartas: [], senas: [], huboMus: false });
  });

  it("cambiar «¿Ha habido mus?» vacía las cartas; al decir que sí, también las señas", () => {
    const e = aplicar(enPosicion(1), { tipo: "poner", rango: 7 }, { tipo: "senas", ids: ["31"] });
    expect(aplicar(e, { tipo: "mus", si: true })).toMatchObject({ cartas: [], senas: [], huboMus: true });
    expect(aplicar(e, { tipo: "mus", si: false })).toBe(e); // sin cambio, el mismo estado
  });

  it("no entran más de 4 cartas, y quitar borra una de ese rango", () => {
    const e = aplicar(ESTADO_INICIAL, ...[7, 7, 6, 5, 4].map((rango): Accion => ({ tipo: "poner", rango })));
    expect(e.cartas).toEqual([7, 7, 6, 5]);
    expect(aplicar(e, { tipo: "quitar", rango: 7 }).cartas).toEqual([7, 6, 5]);
    expect(aplicar(e, { tipo: "quitar", rango: 0 })).toBe(e);
  });
});
