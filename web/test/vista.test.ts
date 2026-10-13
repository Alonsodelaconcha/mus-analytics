import { describe, expect, it } from "vitest";

import { leerMano } from "../src/nucleo/cartas";
import { type DecisionMus, Datos, decisionDe, equityDe, opcionesDe } from "../src/nucleo/datos";
import { LANCES } from "../src/nucleo/evaluacion";
import { tablaParaSenas } from "../src/nucleo/senas";
import { indiceMano } from "../src/nucleo/tablas";
import {
  UMBRAL_CLARA,
  UMBRAL_IGUAL,
  probabilidadesTrasDescarte,
  vistaDecision,
  vistaDescartes,
  vistaProbabilidades,
} from "../src/vista/vista";
import { leerDato } from "./ayuda";

const datos = await Datos.cargar((ruta) => Promise.resolve(leerDato(ruta)));
const { manifiesto } = datos;
const { escalas } = manifiesto;

function decision(ventaja: number, radio = 0.01, codigo?: DecisionMus["decision"]): DecisionMus {
  const calculada = ventaja - radio > 0 ? "mus" : ventaja + radio < 0 ? "cortar" : "indiferente";
  return {
    decision: codigo ?? calculada,
    ventaja,
    radio,
    cortar: 0,
    mus: ventaja,
    pMusDespues: 0.4,
    nEfectivo: 50_000,
    repartos: 100_000,
    pHabla: 1,
    porLance: [],
  };
}

describe("¿mus o corto?", () => {
  it("clara, por poco o da igual según la diferencia", () => {
    expect(vistaDecision(decision(-0.4))).toMatchObject({ veredicto: "corta", intensidad: "clara", titulo: "Corta", etiqueta: "Claro" });
    expect(vistaDecision(decision(UMBRAL_CLARA - 0.01))).toMatchObject({ veredicto: "mus", intensidad: "por-poco", etiqueta: "Por poco" });
    expect(vistaDecision(decision(UMBRAL_IGUAL - 0.005))).toMatchObject({ veredicto: "igual", titulo: "Da igual" });
    // Indiferente para la simulación aunque la media no sea pequeña: da igual.
    expect(vistaDecision(decision(0.05, 0.08)).veredicto).toBe("igual");
  });

  it("en las ajustadas (por poco o da igual) avisa de que con envites podría cambiar", () => {
    expect(vistaDecision(decision(-0.4)).matiz).toBe("");
    expect(vistaDecision(decision(-0.1)).matiz).toBe("Con envites o según el marcador, podría cambiar.");
    expect(vistaDecision(decision(0.01, 0.02)).matiz).toBe("Con envites o según el marcador, podría cambiar.");
  });

  it("A A 4 5 de postre en una mesa normal: corta (el ejemplo de las limitaciones)", async () => {
    const d = decisionDe(await datos.mesa("normal"), escalas, indiceMano(leerMano("A A 4 5")), 4);
    // Sin señas, «Corta» claro: python -m mus cortar da ≈ −0,52 (tres semillas de 300 000
    // repartos) y la web, −0,56 ± 0,04 con 100 000. Con el compañero ciego, +0,42: da mus.
    expect(d?.decision).toBe("cortar");
    expect(d && vistaDecision(d).intensidad).toBe("clara");
  });

  it("la explicación dice cuánto se gana, en tantos cada 10 manos", () => {
    expect(vistaDecision(decision(-0.27)).explicacion)
      .toBe("Si cortas, tu pareja saca de media unos 3 tantos más cada 10 manos que si das mus.");
    expect(vistaDecision(decision(0.02, 0.005)).explicacion).toContain("Si acaso, da mus.");
  });

  it("con los datos: R C 5 4 de mano", async () => {
    const i = indiceMano(leerMano("R C 5 4"));
    const normal = decisionDe(await datos.mesa("normal"), escalas, i, 1);
    const seCorta = decisionDe(await datos.mesa("se-corta"), escalas, i, 1);
    expect(normal && vistaDecision(normal)).toMatchObject({ titulo: "Da mus", etiqueta: "Claro" });
    expect(seCorta && vistaDecision(seCorta)).toMatchObject({ titulo: "Corta", etiqueta: "Por poco" });
  });
});

describe("descartes", async () => {
  const mano = leerMano("R C 5 4");
  const i = indiceMano(mano);
  const mesa = await datos.mesa("normal");
  const opciones = vistaDescartes(opcionesDe(mesa, manifiesto, mano, i, 1), mano);

  it("la mejor primero, con su texto y lo que se espera tener", () => {
    const [mejor] = opciones;
    expect(mejor).toMatchObject({ titulo: "Quédate con R C", mejor: true, comparacion: "La mejor" });
    expect(mejor?.detalle).toBe("Pides 2: tiras el cinco y el cuatro");
    expect(mejor?.resumen.juego).toBeGreaterThan(0.7);
    expect(opciones.slice(1).every((o) => o.comparacion.startsWith("Peor") || o.casiIgual)).toBe(true);
  });

  it("probabilidad de ganar tras el mus con un descarte: entre 0 y 1, coherente con la tabla", () => {
    const [mejor] = opciones;
    if (mejor === undefined) throw new Error("sin opciones");
    const ganar = probabilidadesTrasDescarte(mejor.distribucion, mesa.tras_mus.datos, escalas, 1);
    expect(ganar).not.toBeNull();
    for (const l of LANCES) {
      expect(ganar?.[l]).toBeGreaterThanOrEqual(0);
      expect(ganar?.[l]).toBeLessThanOrEqual(1);
    }
    // Media ponderada a mano para una mano final cualquiera de la distribución.
    let esperado = 0;
    for (const [k, n] of mejor.distribucion.numeradores) {
      esperado += n * (equityDe(mesa.tras_mus.datos, escalas, k, 1)?.grande.ganaPareja ?? 0);
    }
    expect(ganar?.grande).toBeCloseTo(esperado / mejor.distribucion.denominador, 12);
  });
});

describe("probabilidades de ganar", async () => {
  const sinSenas = tablaParaSenas(manifiesto, []);
  if (sinSenas.tipo !== "sin-senas") throw new Error("falta la tabla sin señas");
  const reparto = await datos.equity(sinSenas.tabla);

  it("frases y notas", () => {
    const mano = leerMano("R C 5 4");
    const e = equityDe(reparto.datos, escalas, indiceMano(mano), 1);
    if (e === null) throw new Error("sin datos");
    const v = vistaProbabilidades(e, mano);
    expect(v.lances.map((l) => l.nombre)).toEqual(["Grande", "Chica", "Pares", "Juego", "Punto"]);
    expect(v.lances[0]?.frase).toBe("Ganáis la grande unas 6 de cada 10 veces.");
    expect(v.lances[0]).toMatchObject({ frecuenciaCorta: "6 de 10", sinJugar: false });
    expect(v.lances[4]?.nota).toMatch(/^Solo se juega si nadie tiene juego/);
    expect(v.fraseTantos).toMatch(/^La otra pareja saca de media unos 1,1 tantos más/);
  });

  it("con juego no hay punto", () => {
    const mano = leerMano("R C S A");
    const e = equityDe(reparto.datos, escalas, indiceMano(mano), 1);
    if (e === null) throw new Error("sin datos");
    const punto = vistaProbabilidades(e, mano).lances[4];
    expect(punto).toMatchObject({
      frase: "No hay punto: tienes juego.", nota: "", seJuega: 0, sinJugar: true, frecuenciaCorta: "no se juega",
    });
  });
});
