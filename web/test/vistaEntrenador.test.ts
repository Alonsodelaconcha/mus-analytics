/** Lo que dice el entrenador: la situación, la valoración, el porqué y el resumen. */

import { describe, expect, it } from "vitest";

import { valorarCorte } from "../src/entrenador/valoracion";
import { leerMano } from "../src/nucleo/cartas";
import { type DecisionMus, Datos, decisionDe } from "../src/nucleo/datos";
import { LANCES } from "../src/nucleo/evaluacion";
import { indiceMano } from "../src/nucleo/tablas";
import {
  HABLAN_ANTES,
  NOMBRE_MODO,
  UMBRAL_LANCE,
  contexto,
  fraseDecisionesPorMano,
  fraseSituacion,
  vistaPorLance,
  vistaRespuesta,
  vistaResumen,
} from "../src/vista/entrenador";
import { type ReferenciaEntrenador, leerDato, leerReferencia } from "./ayuda";

const ref = leerReferencia("entrenador.json") as ReferenciaEntrenador;
const datos = await Datos.cargar((ruta) => Promise.resolve(leerDato(ruta)));
const { escalas } = datos.manifiesto;

async function decision(mano: string, posicion: number, mesa = "normal"): Promise<DecisionMus> {
  const d = decisionDe(await datos.mesa(mesa), escalas, indiceMano(leerMano(mano)), posicion);
  if (d === null) throw new Error("falta la decisión");
  return d;
}

/** Una decisión de mentira, con la ventaja repartida entre los lances que se digan. */
function inventada(porLance: [number, number][], codigo: DecisionMus["decision"] = "mus"): DecisionMus {
  const ventaja = porLance.reduce((t, [v]) => t + v, 0);
  return {
    decision: codigo,
    ventaja,
    radio: 0.02,
    cortar: 0,
    mus: ventaja,
    pMusDespues: 0.5,
    nEfectivo: 50_000,
    repartos: 100_000,
    pHabla: 1,
    porLance: LANCES.map((lance, i) => ({ lance, ventaja: porLance[i]?.[0] ?? 0, radio: porLance[i]?.[1] ?? 0.01 })),
  };
}

describe("la situación", () => {
  it("las frases son las mismas que escribe Python", () => {
    expect([...HABLAN_ANTES]).toEqual(ref.hablan_antes);
    expect(contexto("{mesa}")).toBe(ref.contexto);
  });

  it("dice quién eres y qué han hecho los anteriores", () => {
    expect(fraseSituacion(1)).toBe("Eres mano: hablas el primero.");
    expect(fraseSituacion(2)).toBe("Eres segundo. La mano ha dado mus.");
    expect(fraseSituacion(3)).toBe("Eres tercero. Los dos anteriores han dado mus.");
    expect(fraseSituacion(4)).toBe("Eres postre. Los tres anteriores han dado mus.");
  });

  it("dice contra qué mesa se compara y qué no se cuenta, sin hablar de jugada perfecta", () => {
    expect(contexto("Normal")).toBe(
      "La mejor jugada contra una mesa «Normal», sin contar envites, señas ni las cartas que piden los demás.");
    const todo = [contexto("Normal"), ...Object.values(NOMBRE_MODO).flatMap((m) => [m.corto, m.descripcion])].join(" ");
    expect(todo).not.toMatch(/GTO|equilibrio|óptim/i);
  });
});

describe("la valoración de una respuesta", () => {
  it("R C 5 4 de mano en una mesa normal: dar mus está bien; cortar pierde lo que dice la calculadora", async () => {
    const d = await decision("R C 5 4", 1);
    const valoracion = valorarCorte(d);
    expect(vistaRespuesta(d, valoracion, "mus")).toMatchObject({ resultado: "bien", titulo: "Bien", perdidos: 0 });
    const fallo = vistaRespuesta(d, valoracion, "corta");
    expect(fallo).toMatchObject({ resultado: "fallo", titulo: "Era mejor dar mus" });
    expect(fallo.perdidos).toBe(Math.round(d.ventaja * 1000));
    expect(fallo.detalle).toMatch(/^Pierdes unos \d+ tantos cada 10 manos\. Si das mus, tu pareja saca de media/);
  });

  it("7 7 4 4 de mano: era mejor cortar, y es una decisión clara (sin el aviso de los envites)", async () => {
    const d = await decision("7 7 4 4", 1);
    const v = vistaRespuesta(d, valorarCorte(d), "mus");
    expect(v).toMatchObject({ resultado: "fallo", titulo: "Era mejor cortar", etiqueta: "Claro", matiz: "" });
    expect(v.detalle).toMatch(/^Pierdes unos 1,\d tantos por mano\./);
  });

  it("si da igual, ninguna respuesta pierde, y avisa de que con envites podría cambiar", () => {
    const d = inventada([[0.01, 0.01]], "indiferente");
    for (const respuesta of ["mus", "corta"] as const) {
      expect(vistaRespuesta(d, valorarCorte(d), respuesta)).toMatchObject({
        resultado: "igual", titulo: "Daba igual", perdidos: 0, etiqueta: "",
        matiz: "Con envites o según el marcador, podría cambiar.",
      });
    }
  });

  it("por poco: se puntúa, con el aviso", () => {
    const d = inventada([[0.08, 0.01]]);
    expect(vistaRespuesta(d, valorarCorte(d), "corta")).toMatchObject({
      resultado: "fallo", etiqueta: "Por poco", perdidos: 80,
      matiz: "Con envites o según el marcador, podría cambiar.",
    });
  });
});

describe("el porqué, lance a lance", () => {
  it("7 7 4 4 de mano: lo que más pesa son los pares, que se pierden al romper los duples", async () => {
    const v = vistaPorLance(await decision("7 7 4 4", 1));
    expect(v.lances.map((l) => l.nombre)).toEqual(["Grande", "Chica", "Pares", "Juego", "Punto"]);
    const pares = v.lances.find((l) => l.lance === "pares");
    expect(pares).toMatchObject({ efecto: "pierde", ancho: 1 });
    expect(pares?.cifra).toMatch(/^−1,\d\d$/);
    expect(v.frase).toMatch(/^Lo que más pesa son los pares: dando mus pierdes ahí unos 1,\d tantos por mano\.$/);
  });

  it("cada lance: gana, pierde o apenas cambia (dentro del margen o muy poco)", () => {
    const v = vistaPorLance(inventada([[0.3, 0.01], [-0.15, 0.01], [0.05, 0.06], [UMBRAL_LANCE - 0.005, 0.001], [0, 0]]));
    expect(v.lances.map((l) => l.efecto)).toEqual(["gana", "pierde", "igual", "igual", "igual"]);
    expect(v.lances.map((l) => l.cifra)).toEqual(["+0,30", "−0,15", "≈ 0", "≈ 0", "≈ 0"]);
    expect(v.lances.map((l) => l.ancho)).toEqual([1, 0.5, 0, 0, 0]);
    expect(v.frase).toBe("Lo que más pesa es la grande: dando mus ganas ahí unos 3 tantos cada 10 manos.");
  });

  it("si ningún lance cambia, lo dice", () => {
    expect(vistaPorLance(inventada([[0.01, 0.02]])).frase).toBe("Ningún lance cambia apenas por dar mus.");
  });

  it("con los datos reales, las barras nunca se salen y hay una frase para cada situación", async () => {
    for (const { id } of datos.manifiesto.mesas) {
      const mesa = await datos.mesa(id);
      for (let h = 0; h < 330; h++) {
        for (const p of [1, 2, 3, 4]) {
          const d = decisionDe(mesa, escalas, h, p);
          if (d === null) throw new Error("falta una decisión");
          const v = vistaPorLance(d);
          expect(v.lances).toHaveLength(5);
          expect(v.lances.every((l) => l.ancho >= 0 && l.ancho <= 1)).toBe(true);
          expect(v.frase.length).toBeGreaterThan(20);
        }
      }
    }
  });
});

describe("el resumen", () => {
  it("tantos perdidos, desglose y ritmo por cada 100 manos de partida", () => {
    const v = vistaResumen({ n: 10, perdidos: 620, bien: 7, fallosClaros: 1, fallosPorPoco: 2 }, 0.6);
    expect(v.total).toBe("Has perdido 0,62 tantos en 10 decisiones.");
    expect(v.desglose).toBe("7 bien · 1 fallo claro · 2 por poco");
    // 0,062 tantos por decisión × 0,6 decisiones por mano × 100 manos.
    expect(v.ritmo).toBe("A ese ritmo, unos 3,7 tantos cada 100 manos de partida.");
    // A partir de 10, sin decimales: no es una cifra tan fina.
    expect(vistaResumen({ n: 10, perdidos: 4950, bien: 5, fallosClaros: 5, fallosPorPoco: 0 }, 0.69).ritmo)
      .toBe("A ese ritmo, unos 34 tantos cada 100 manos de partida.");
  });

  it("sin fallos", () => {
    const v = vistaResumen({ n: 10, perdidos: 0, bien: 10, fallosClaros: 0, fallosPorPoco: 0 }, 0.6);
    expect(v.total).toBe("No has perdido nada en 10 decisiones.");
    expect(v.desglose).toBe("10 bien");
    expect(v.ritmo).toBe("A ese ritmo, no pierdes tantos en esta decisión.");
  });

  it("en «Ajustadas» no se da el ritmo: las manos no salen como en una partida", () => {
    const v = vistaResumen({ n: 1, perdidos: 150, bien: 0, fallosClaros: 0, fallosPorPoco: 1 }, null);
    expect(v.total).toBe("Has perdido 0,15 tantos en 1 decisión.");
    expect(v.desglose).toBe("0 bien · 1 por poco");
    expect(v.ritmo).toBe("");
  });

  it("cuántas manos de cada 100 se decide en esa mesa", () => {
    expect(fraseDecisionesPorMano("Normal", 0.5512))
      .toBe("En una mesa «Normal» te toca decidir mus o corto en unas 55 de cada 100 manos.");
  });
});
