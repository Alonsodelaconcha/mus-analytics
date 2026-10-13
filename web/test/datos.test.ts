import { describe, expect, it } from "vitest";

import { leerMano } from "../src/nucleo/cartas";
import {
  Datos,
  ErrorDatos,
  type FicheroMesa,
  LANCES,
  decisionDe,
  equityDe,
  errorTrasMusDe,
  opcionesDe,
  tablaParaSenas,
  tantosTotales,
  texto,
  validarFicheroMesa,
  validarManifiesto,
} from "../src/nucleo";
import { indiceMano } from "../src/nucleo/tablas";
import { leerDato } from "./ayuda";

const cargador = (ruta: string) => Promise.resolve(leerDato(ruta));
const datos = await Datos.cargar(cargador);
const { manifiesto } = datos;
const { escalas } = manifiesto;

function manifiestoModificado(cambio: (m: Record<string, unknown>) => void): unknown {
  const m = JSON.parse(new TextDecoder().decode(leerDato("manifiesto.json"))) as Record<string, unknown>;
  cambio(m);
  return m;
}

describe("validación del manifiesto", () => {
  it("los datos publicados encajan con el núcleo", () => {
    expect(manifiesto.manos).toHaveLength(330);
    expect(manifiesto.descartes.conservadas).toHaveLength(3546);
    expect(manifiesto.mesas.map((m) => m.id)).toEqual(["mucho-mus", "normal", "se-corta"]);
  });

  it("rechaza otro formato, otras reglas, otro orden de manos o un manifiesto roto", () => {
    // El formato 1 es el de la web 0.1: no traía el desglose por lance.
    expect(() => validarManifiesto(manifiestoModificado((m) => { m.formato = 1; })))
      .toThrow(/Formato/);
    expect(() => validarManifiesto(manifiestoModificado((m) => {
      (m.reglas as Record<string, unknown>).treinta_y_una_real = true;
    }))).toThrow(/otras reglas/);
    expect(() => validarManifiesto(manifiestoModificado((m) => {
      (m.manos as string[]).reverse();
    }))).toThrow(/mismo orden/);
    expect(() => validarManifiesto(manifiestoModificado((m) => { delete m.reglas; })))
      .toThrow(ErrorDatos);
    expect(() => validarManifiesto("no soy un manifiesto")).toThrow(ErrorDatos);
  });
});

describe("carga de ficheros", () => {
  it("comprueba la huella: un fichero alterado se rechaza", async () => {
    const alterado = await Datos.cargar(async (ruta) => {
      const bytes = new Uint8Array(await cargador(ruta));
      if (ruta === "mesa-normal.json") {
        bytes[bytes.length - 2] = 0x20; // un byte distinto
      }
      return bytes.buffer;
    });
    await expect(alterado.mesa("normal")).rejects.toThrow(/huella/);
    await expect(alterado.mesa("se-corta")).resolves.toBeDefined();
  });

  it("guarda los ficheros y permite reintentar si falla la descarga", async () => {
    let fallos = 1;
    let descargas = 0;
    const conCorte = await Datos.cargar((ruta) => {
      if (ruta !== "manifiesto.json") {
        descargas++;
        if (fallos-- > 0) return Promise.reject(new Error("sin conexión"));
      }
      return cargador(ruta);
    });
    await expect(conCorte.mesa()).rejects.toThrow("sin conexión");
    const mesa = await conCorte.mesa();
    expect(await conCorte.mesa()).toBe(mesa);
    expect(descargas).toBe(2);
  });

  it("tipo de mesa desconocido", () => {
    expect(() => datos.mesa("sin-cortes")).toThrow(ErrorDatos);
  });
});

describe("lectura de los datos", () => {
  const equityCon = async (ids: string[], mano: string, posicion: number) => {
    const r = tablaParaSenas(manifiesto, ids);
    if (r.tipo === "imposible") throw new Error("imposible");
    const f = await datos.equity(r.tabla);
    return equityDe(f.datos, escalas, indiceMano(leerMano(mano)), posicion);
  };

  it("equity con señas: A A 4 5 de mano, compañero con dos reyes y 31 (igual que mus equity)", async () => {
    const e = await equityCon(["dos-reyes", "31"], "A A 4 5", 1);
    expect(e?.grande.ganaPareja).toBeCloseTo(0.8535, 4);
    expect(e?.chica.ganaIndividual).toBeCloseTo(0.9782, 4);
    expect(e?.pares.ganaPareja).toBeCloseTo(0.7549, 4);
    expect(e?.juego.tantos).toBeCloseTo(2.349, 3);
    expect(e?.punto.seJuega).toBe(0);
    expect(e && tantosTotales(e)).toBeCloseTo(4.951, 2);
  });

  it("equity imposible con la mano del héroe: null", async () => {
    // Con los cuatro 7 en mi mano, el compañero no puede tener 7 7 7 S, 7 7 7 C ni 7 7 7 R.
    // Sí podría tener S S S A o C C C A, así que medias + 31 sigue siendo posible.
    expect(await equityCon(["medias", "31"], "7 7 7 7", 1)).not.toBeNull();
    const sinPareja = await equityCon(["solomillo"], "R R R R", 1);
    expect(sinPareja).not.toBeNull(); // quedan 4 reyes y 8 ases
  });

  it("la tabla del reparto cumple la identidad de la grande: tantos = 2·P(pareja) − 1", async () => {
    const r = tablaParaSenas(manifiesto, []);
    if (r.tipo !== "sin-senas") throw new Error("se esperaba la tabla sin señas");
    const f = await datos.equity(r.tabla);
    for (let mano = 0; mano < 330; mano++) {
      for (const posicion of [1, 2, 3, 4]) {
        const e = equityDe(f.datos, escalas, mano, posicion);
        expect(e).not.toBeNull();
        if (e === null) continue;
        expect(Math.abs(e.grande.tantos - (2 * e.grande.ganaPareja - 1))).toBeLessThan(0.0011);
        for (const lance of LANCES) {
          expect(e[lance].ganaIndividual).toBeLessThanOrEqual(e[lance].ganaPareja);
          expect(e[lance].ganaPareja).toBeLessThanOrEqual(e[lance].seJuega);
        }
      }
    }
  });

  it("¿mus o corto?: R C 5 4 de mano depende del tipo de mesa (igual que mus cortar)", async () => {
    const i = indiceMano(leerMano("R C 5 4"));
    const decision = async (id: string) => decisionDe(await datos.mesa(id), escalas, i, 1);
    expect(await decision("se-corta")).toMatchObject({ decision: "cortar", ventaja: -0.07, radio: 0.013 });
    expect(await decision("mucho-mus")).toMatchObject({ decision: "mus", ventaja: 0.823 });
    const normal = await decision("normal");
    expect(normal?.decision).toBe("mus");
    expect(normal?.repartos).toBe(100_000);
  });

  it("el desglose por lance suma la ventaja, y la mano habla siempre", async () => {
    for (const { id } of manifiesto.mesas) {
      const mesa = await datos.mesa(id);
      for (let i = 0; i < 330; i++) {
        for (const posicion of [1, 2, 3, 4]) {
          const d = decisionDe(mesa, escalas, i, posicion);
          if (d === null) throw new Error("falta una decisión");
          expect(d.porLance.map((x) => x.lance)).toEqual([...LANCES]);
          // Cada cifra se redondea a la milésima por separado.
          const suma = d.porLance.reduce((t, x) => t + x.ventaja, 0);
          expect(Math.abs(suma - d.ventaja)).toBeLessThan(0.0031);
          expect(d.porLance.every((x) => x.radio >= 0)).toBe(true);
          expect(d.pHabla).toBeGreaterThan(0);
          expect(d.pHabla).toBeLessThanOrEqual(posicion === 1 ? 1 : 0.9999);
          if (posicion === 1) expect(d.pHabla).toBe(1);
        }
      }
    }
  });

  it("7 7 4 4 de mano: dando mus se pierde en pares, porque se rompen los duples", async () => {
    const d = decisionDe(await datos.mesa("normal"), escalas, indiceMano(leerMano("7 7 4 4")), 1);
    expect(d?.decision).toBe("cortar");
    expect(d?.porLance.find((x) => x.lance === "pares")?.ventaja).toBeLessThan(-1);
  });

  it("un fichero de mesa sin el desglose por lance se rechaza", () => {
    const f = JSON.parse(new TextDecoder().decode(leerDato("mesa-normal.json"))) as Record<string, unknown>;
    expect(() => validarFicheroMesa(f, "mesa-normal.json", manifiesto)).not.toThrow();
    delete f.por_lance;
    expect(() => validarFicheroMesa(f, "mesa-normal.json", manifiesto)).toThrow(/por_lance/);
  });

  it("descartes si hay mus: ordenados, el mejor con diferencia 0", async () => {
    const mano = leerMano("R C 5 4");
    const opciones = opcionesDe(await datos.mesa("se-corta"), manifiesto, mano, indiceMano(mano), 1);
    expect(opciones).toHaveLength(15);
    expect(texto(opciones[0]?.opcion.conservadas ?? [])).toBe("R C");
    expect(opciones[0]?.diferencia).toBe(0);
    const valores = opciones.map((o) => o.siHayMus);
    expect(valores).toEqual([...valores].sort((a, b) => b - a));
    expect(opciones.every((o) => o.diferencia <= 0 && o.radio >= 0)).toBe(true);
  });

  it("todas las manos y posiciones tienen decisión y descartes en las tres mesas", async () => {
    for (const { id } of manifiesto.mesas) {
      const mesa: FicheroMesa = await datos.mesa(id);
      for (let i = 0; i < 330; i++) {
        for (const posicion of [1, 2, 3, 4]) {
          const d = decisionDe(mesa, escalas, i, posicion);
          expect(d).not.toBeNull();
          if (d === null) continue;
          const bajo = d.ventaja - d.radio;
          const alto = d.ventaja + d.radio;
          // El código de decisión es el de Python; con el redondeo, el intervalo puede rozar el 0.
          if (d.decision === "mus") expect(bajo).toBeGreaterThanOrEqual(-0.001);
          if (d.decision === "cortar") expect(alto).toBeLessThanOrEqual(0.001);
          expect(errorTrasMusDe(mesa, escalas, i, posicion)).not.toBeNull();
          expect(equityDe(mesa.tras_mus.datos, escalas, i, posicion)).not.toBeNull();
        }
      }
    }
  });

  it("posición fuera de rango", async () => {
    expect(() => equityDe([], escalas, 0, 5)).toThrow(RangeError);
    expect(() => decisionDe({} as FicheroMesa, escalas, 0, 0)).toThrow(RangeError);
    await Promise.resolve();
  });
});
