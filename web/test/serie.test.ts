/** Las reglas de una serie del entrenador: preguntar, valorar, siguiente y resumen. */

import { describe, expect, it } from "vitest";

import {
  type EstadoSerie,
  SERIE_INICIAL,
  SITUACIONES_POR_SERIE,
  contestadaActual,
  reducirSerie,
  situacionActual,
} from "../src/entrenador/serie";
import { type Situacion } from "../src/entrenador/situaciones";
import { type ValoracionCorte } from "../src/entrenador/valoracion";

const situacion = (indice: number, posicion = 1): Situacion => ({ ejercicio: "corte", mesa: "normal", indice, posicion });
const TRES = [situacion(10), situacion(20, 3), situacion(30, 4)];
const DA_MUS: ValoracionCorte = { veredicto: "mus", intensidad: "clara", perdidos: { mus: 0, corta: 412 } };

function empezada(): EstadoSerie {
  return reducirSerie(SERIE_INICIAL, { tipo: "empezar", modo: "mesa", situaciones: TRES });
}

describe("una serie del entrenador", () => {
  it("son 10 manos", () => {
    expect(SITUACIONES_POR_SERIE).toBe(10);
  });

  it("empieza preguntando la primera situación", () => {
    const e = empezada();
    expect(e).toMatchObject({ fase: "serie", modo: "mesa", valorando: false, contestadas: [] });
    expect(situacionActual(e)).toEqual(TRES[0]);
    expect(contestadaActual(e)).toBeNull();
  });

  it("sin situaciones no empieza", () => {
    expect(reducirSerie(SERIE_INICIAL, { tipo: "empezar", modo: "ajustadas", situaciones: [] })).toBe(SERIE_INICIAL);
  });

  it("responder enseña la valoración de esa misma situación", () => {
    const e = reducirSerie(empezada(), { tipo: "responder", respuesta: "corta", valoracion: DA_MUS });
    expect(e).toMatchObject({ fase: "serie", valorando: true });
    expect(situacionActual(e)).toEqual(TRES[0]);
    expect(contestadaActual(e)).toEqual({ situacion: TRES[0], respuesta: "corta", valoracion: DA_MUS });
  });

  it("un segundo toque mientras se ve la valoración no cuenta", () => {
    const una = reducirSerie(empezada(), { tipo: "responder", respuesta: "corta", valoracion: DA_MUS });
    expect(reducirSerie(una, { tipo: "responder", respuesta: "mus", valoracion: DA_MUS })).toBe(una);
  });

  it("«Siguiente» pasa a la pregunta que toca y, tras la última, al resumen", () => {
    let e = empezada();
    // Sin responder, «Siguiente» no hace nada: no se puede saltar una mano.
    expect(reducirSerie(e, { tipo: "siguiente" })).toBe(e);
    for (const [i, s] of TRES.entries()) {
      expect(situacionActual(e)).toEqual(s);
      e = reducirSerie(e, { tipo: "responder", respuesta: i === 1 ? "corta" : "mus", valoracion: DA_MUS });
      e = reducirSerie(e, { tipo: "siguiente" });
    }
    expect(e.fase).toBe("resumen");
    if (e.fase !== "resumen") throw new Error("se esperaba el resumen");
    expect(e.modo).toBe("mesa");
    expect(e.contestadas.map((c) => c.respuesta)).toEqual(["mus", "corta", "mus"]);
    expect(e.contestadas.map((c) => c.situacion)).toEqual(TRES);
    expect(situacionActual(e)).toBeNull();
  });

  it("fuera de una serie no se puede responder ni pasar", () => {
    expect(reducirSerie(SERIE_INICIAL, { tipo: "responder", respuesta: "mus", valoracion: DA_MUS })).toBe(SERIE_INICIAL);
    expect(reducirSerie(SERIE_INICIAL, { tipo: "siguiente" })).toBe(SERIE_INICIAL);
  });

  it("salir vuelve al inicio desde cualquier momento, y desde el resumen se empieza otra", () => {
    const una = reducirSerie(empezada(), { tipo: "responder", respuesta: "mus", valoracion: DA_MUS });
    expect(reducirSerie(una, { tipo: "salir" })).toBe(SERIE_INICIAL);
    const resumen: EstadoSerie = { fase: "resumen", modo: "mesa", contestadas: [] };
    expect(reducirSerie(resumen, { tipo: "salir" })).toBe(SERIE_INICIAL);
    expect(reducirSerie(resumen, { tipo: "empezar", modo: "ajustadas", situaciones: TRES }))
      .toMatchObject({ fase: "serie", modo: "ajustadas", valorando: false });
  });
});
