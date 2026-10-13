/** El registro de respuestas del entrenador: guardar, exportar, importar y resumir. */

import { describe, expect, it } from "vitest";

import {
  ALMACEN_LOCAL,
  type Almacen,
  type Anotacion,
  CLAVE_PROGRESO,
  FORMATO_PROGRESO,
  almacenEnMemoria,
  anotar,
  esAnotacion,
  exportar,
  guardarProgreso,
  importar,
  leerProgreso,
  pedirPersistencia,
  resumir,
  tantosCadaCienManos,
  tantosPorDecision,
} from "../src/entrenador/progreso";

/** 12 de octubre de 2026, 20:00 UTC. */
const BASE = Date.UTC(2026, 9, 12, 20, 0, 0);

function anotacion(cambios: Partial<Anotacion> = {}): Anotacion {
  return {
    fecha: BASE,
    ejercicio: "corte",
    modo: "mesa",
    mesa: "normal",
    mano: "R C 5 4",
    posicion: 1,
    respuesta: "mus",
    mejor: "mus",
    intensidad: "clara",
    perdidos: 0,
    datos: "2026-10-12",
    web: "0.2.0",
    ...cambios,
  };
}

const FALLO = anotacion({ fecha: BASE + 60_000, mano: "7 7 4 4", respuesta: "mus", mejor: "corta", perdidos: 1069 });
const POR_POCO = anotacion({ fecha: BASE + 120_000, mano: "R R 5 4", posicion: 4, respuesta: "corta", intensidad: "por-poco", perdidos: 80 });

describe("qué es una anotación", () => {
  it("acepta las de los dos ejercicios", () => {
    expect(esAnotacion(anotacion())).toBe(true);
    expect(esAnotacion(anotacion({ ejercicio: "descarte", respuesta: "R C", mejor: "R" }))).toBe(true);
    expect(esAnotacion(anotacion({ ejercicio: "descarte", respuesta: "", mejor: "R" }))).toBe(true);
    expect(esAnotacion(anotacion({ modo: "repaso", mejor: "igual", intensidad: "igual" }))).toBe(true);
  });

  it("rechaza lo que no cuadra, campo a campo", () => {
    const mal: Record<string, unknown>[] = [
      { fecha: "ayer" }, { fecha: -1 }, { fecha: 1.5 }, { ejercicio: "envite" }, { modo: "torneo" },
      { mesa: "" }, { mesa: 3 }, { mano: "R C 5" }, { mano: "R C 5 8" }, { mano: "RC54" },
      { posicion: 0 }, { posicion: 5 }, { posicion: 1.5 }, { respuesta: 7 }, { mejor: null },
      { intensidad: "dudosa" }, { perdidos: -1 }, { perdidos: 0.5 }, { datos: 2026 }, { web: undefined },
    ];
    for (const cambio of mal) {
      expect(esAnotacion({ ...anotacion(), ...cambio }), JSON.stringify(cambio)).toBe(false);
    }
    expect(esAnotacion(null)).toBe(false);
    expect(esAnotacion([anotacion()])).toBe(false);
    expect(esAnotacion("R C 5 4")).toBe(false);
  });
});

describe("guardar en el móvil", () => {
  it("lo anotado se vuelve a leer igual", () => {
    const almacen = almacenEnMemoria();
    expect(leerProgreso(almacen)).toEqual([]);
    const uno = anotar(almacen, [], anotacion());
    expect(uno.guardado).toBe(true);
    const dos = anotar(almacen, uno.anotaciones, FALLO);
    expect(dos.anotaciones).toEqual([anotacion(), FALLO]);
    expect(leerProgreso(almacen)).toEqual([anotacion(), FALLO]);
  });

  it("solo se guardan los campos de la anotación", () => {
    const almacen = almacenEnMemoria();
    anotar(almacen, [], { ...anotacion(), nombre: "Alonso" } as Anotacion);
    expect(almacen.leer(CLAVE_PROGRESO)).not.toContain("Alonso");
    expect(Object.keys(leerProgreso(almacen)[0] ?? {})).toEqual(Object.keys(anotacion()));
  });

  it("si el móvil no deja guardar, la respuesta no se pierde y se avisa", () => {
    const lleno: Almacen = { leer: () => null, guardar: () => false };
    const r = anotar(lleno, [anotacion()], FALLO);
    expect(r.guardado).toBe(false);
    expect(r.anotaciones).toEqual([anotacion(), FALLO]);
  });

  it("sin almacenamiento del navegador no falla: no hay nada guardado", () => {
    // En este entorno (node) no existe localStorage, como en algunos modos privados.
    expect(ALMACEN_LOCAL.leer(CLAVE_PROGRESO)).toBeNull();
    expect(ALMACEN_LOCAL.guardar(CLAVE_PROGRESO, "{}")).toBe(false);
    expect(leerProgreso(ALMACEN_LOCAL)).toEqual([]);
  });

  it.each([
    ["dañado", "{no es json"],
    ["de otra versión", JSON.stringify({ formato: FORMATO_PROGRESO + 1, anotaciones: [] })],
    ["con una respuesta rara", JSON.stringify({ formato: FORMATO_PROGRESO, anotaciones: [{ mano: "R" }] })],
  ])("un registro %s no se pisa: se aparta y se empieza uno nuevo", (_, guardado) => {
    const almacen = almacenEnMemoria({ [CLAVE_PROGRESO]: guardado });
    expect(leerProgreso(almacen)).toEqual([]);
    expect(almacen.leer(`${CLAVE_PROGRESO}.ilegible`)).toBe(guardado);
    anotar(almacen, [], anotacion());
    expect(leerProgreso(almacen)).toEqual([anotacion()]);
    expect(almacen.leer(`${CLAVE_PROGRESO}.ilegible`)).toBe(guardado);
  });
});

describe("exportar e importar", () => {
  const registro = [anotacion(), FALLO, POR_POCO];

  it("lo exportado se importa igual en un móvil vacío", () => {
    const fichero = exportar(registro, Date.UTC(2026, 9, 13, 8, 30, 0));
    expect(JSON.parse(fichero)).toMatchObject({
      formato: FORMATO_PROGRESO, aplicacion: "Mus Analytics", exportado: "2026-10-13T08:30:00.000Z",
    });
    expect(importar(fichero, [])).toEqual({ ok: true, anotaciones: registro, nuevas: 3, repetidas: 0 });
  });

  it("importar dos veces no repite nada, y lo nuevo se une por fecha", () => {
    const fichero = exportar([FALLO, anotacion()], 0);
    const otra = anotacion({ fecha: BASE + 30_000, mano: "A A 4 5" });
    const r = importar(fichero, [otra, FALLO]);
    expect(r).toMatchObject({ ok: true, nuevas: 1, repetidas: 1 });
    if (!r.ok) throw new Error(r.error);
    expect(r.anotaciones).toEqual([anotacion(), otra, FALLO]);
    expect(importar(fichero, r.anotaciones)).toMatchObject({ ok: true, nuevas: 0, repetidas: 2 });
    // Un fichero con la misma respuesta dos veces tampoco la duplica.
    expect(importar(exportar([FALLO, FALLO], 0), [])).toMatchObject({ nuevas: 1, repetidas: 1 });
  });

  it("un fichero que no se entiende no cambia nada y dice por qué", () => {
    expect(importar("hola", registro)).toEqual({ ok: false, error: "No es un fichero de progreso de Mus Analytics." });
    expect(importar("[1, 2]", registro)).toMatchObject({ ok: false, error: /No es un fichero de progreso/ });
    expect(importar(JSON.stringify({ formato: 99, anotaciones: [] }), registro))
      .toMatchObject({ ok: false, error: /otra versión/ });
    expect(importar(JSON.stringify({ formato: FORMATO_PROGRESO, anotaciones: [anotacion(), { mano: "R" }] }), registro))
      .toMatchObject({ ok: false, error: /dañado/ });
  });

  it("guardar el registro importado", () => {
    const almacen = almacenEnMemoria();
    expect(guardarProgreso(almacen, registro)).toBe(true);
    expect(leerProgreso(almacen)).toEqual(registro);
  });
});

describe("las cifras del progreso", () => {
  it("respuestas, tantos perdidos y fallos claros o por poco", () => {
    const r = resumir([anotacion(), FALLO, POR_POCO, anotacion({ mejor: "igual", intensidad: "igual" })]);
    expect(r).toEqual({ n: 4, perdidos: 1149, bien: 2, fallosClaros: 1, fallosPorPoco: 1 });
    expect(tantosPorDecision(r)).toBeCloseTo(0.28725, 10);
    // En una mesa en que se decide en 6 de cada 10 manos: 100 × 0,6 × 0,28725.
    expect(tantosCadaCienManos(r, 0.6)).toBeCloseTo(17.235, 10);
  });

  it("sin respuestas no hay nada que dividir", () => {
    const r = resumir([]);
    expect(r).toEqual({ n: 0, perdidos: 0, bien: 0, fallosClaros: 0, fallosPorPoco: 0 });
    expect(tantosPorDecision(r)).toBe(0);
    expect(tantosCadaCienManos(r, 0.6)).toBe(0);
  });
});

describe("almacenamiento persistente", () => {
  it("si el navegador no lo ofrece, no pasa nada", async () => {
    expect(await pedirPersistencia(undefined)).toBe("no-disponible");
    expect(await pedirPersistencia({})).toBe("no-disponible");
  });

  it("si ya lo es, no se vuelve a pedir", async () => {
    let pedidas = 0;
    const gestor = { persisted: () => Promise.resolve(true), persist: () => { pedidas++; return Promise.resolve(true); } };
    expect(await pedirPersistencia(gestor)).toBe("concedida");
    expect(pedidas).toBe(0);
  });

  it("se pide, y el navegador lo concede o no", async () => {
    const no = Promise.resolve(false);
    expect(await pedirPersistencia({ persisted: () => no, persist: () => Promise.resolve(true) })).toBe("concedida");
    expect(await pedirPersistencia({ persisted: () => no, persist: () => no })).toBe("denegada");
    expect(await pedirPersistencia({ persist: () => Promise.resolve(true) })).toBe("concedida");
  });

  it("si la petición falla, el progreso se sigue guardando sin ella", async () => {
    const falla = () => Promise.reject(new Error("no permitido"));
    expect(await pedirPersistencia({ persisted: falla, persist: falla })).toBe("no-disponible");
  });
});
