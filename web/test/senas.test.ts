import { describe, expect, it } from "vitest";

import { leerMano } from "../src/nucleo/cartas";
import { Datos, ErrorDatos } from "../src/nucleo/datos";
import { manosCompatibles, senasDeMano, tablaParaSenas } from "../src/nucleo/senas";
import { indiceMano } from "../src/nucleo/tablas";
import { leerDato } from "./ayuda";

const { manifiesto } = await Datos.cargar((ruta) => Promise.resolve(leerDato(ruta)));
const IDS = manifiesto.senas.map((s) => s.id);

function* combinaciones(k: number, desde = 0, actual: string[] = []): Generator<string[]> {
  if (actual.length === k) {
    yield [...actual];
    return;
  }
  for (let i = desde; i < IDS.length; i++) {
    yield* combinaciones(k, i + 1, [...actual, IDS[i] ?? ""]);
  }
}

describe("tabla para las señas marcadas", () => {
  it("sin señas, la del reparto sin información", () => {
    const r = tablaParaSenas(manifiesto, []);
    expect(r.tipo).toBe("sin-senas");
    if (r.tipo === "sin-senas") expect(r.tabla.fichero).toBe("equity/reparto.json");
  });

  it("cada seña suelta tiene su tabla, con sus mismas manos", () => {
    for (const sena of manifiesto.senas) {
      const r = tablaParaSenas(manifiesto, [sena.id]);
      expect(r.tipo).toBe("tabla");
      if (r.tipo === "tabla") expect(r.manos).toEqual(sena.manos);
    }
  });

  it("hay 30 combinaciones posibles y caen en 16 tablas, como en Python", () => {
    const posibles: string[] = [];
    const tablas = new Set<string>();
    for (let k = 1; k <= 5; k++) {
      for (const ids of combinaciones(k)) {
        const r = tablaParaSenas(manifiesto, ids);
        if (r.tipo === "tabla") {
          posibles.push(ids.join("+"));
          tablas.add(r.tabla.id);
        }
      }
    }
    expect(posibles).toHaveLength(30);
    expect(tablas.size).toBe(16);
    expect(manifiesto.tablas_equity).toHaveLength(17);
  });

  it("dos reyes + 31 son cuatro manos; dos reyes + tres reyes es imposible", () => {
    const r = tablaParaSenas(manifiesto, ["dos-reyes", "31"]);
    expect(r.tipo === "tabla" && r.manos.map((i) => manifiesto.manos[i]).sort()).toEqual(
      ["R R 6 5", "R R 7 4", "R R C A", "R R S A"],
    );
    expect(tablaParaSenas(manifiesto, ["dos-reyes", "tres-reyes"]).tipo).toBe("imposible");
    expect(tablaParaSenas(manifiesto, ["tres-reyes", "medias"])).toMatchObject({
      tabla: { id: "tres-reyes" },
    });
  });

  it("señas desconocidas", () => {
    expect(() => manosCompatibles(manifiesto.senas, ["cuatro-reyes"])).toThrow(ErrorDatos);
  });

  it("señas que puede hacer una mano", () => {
    const ids = (m: string) => senasDeMano(manifiesto, indiceMano(leerMano(m))).map((s) => s.id);
    expect(ids("R R R A")).toEqual(["tres-reyes", "medias", "31", "solomillo"]);
    expect(ids("C C 5 4")).toEqual([]);
  });
});
