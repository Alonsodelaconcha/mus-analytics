// @vitest-environment jsdom
/**
 * El entrenador entero, como lo usaría un jugador: abrirlo, empezar una serie,
 * responder a cada mano y ver el resumen. Con los datos reales; lo que enseña
 * la pantalla se compara con lo que dicen los datos para esa mano.
 */

import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import {
  type Almacen,
  type Anotacion,
  CLAVE_PROGRESO,
  almacenEnMemoria,
  anotar,
  leerProgreso,
} from "../src/entrenador/progreso";
import { type ValoracionCorte, valorarCorte } from "../src/entrenador/valoracion";
import { leerMano } from "../src/nucleo/cartas";
import { Datos, decisionDe } from "../src/nucleo/datos";
import { indiceMano } from "../src/nucleo/tablas";
import { type EstadoSinConexion, type SinConexion } from "../src/sinConexion";
import { azarConSemilla, leerDato } from "./ayuda";

afterEach(() => {
  cleanup();
  localStorage.clear();
});

const cargador = (ruta: string) => Promise.resolve(leerDato(ruta));
const datos = await Datos.cargar(cargador);
const { escalas } = datos.manifiesto;
type Usuario = ReturnType<typeof userEvent.setup>;

const SIMBOLO: Readonly<Record<string, string>> = {
  rey: "R", caballo: "C", sota: "S", siete: "7", seis: "6", cinco: "5", cuatro: "4", as: "A",
};
const POSICION: Readonly<Record<string, number>> = { mano: 1, segundo: 2, tercero: 3, postre: 4 };
const BASE = Date.UTC(2026, 9, 12, 20, 0, 0);

interface Opciones {
  almacen?: Almacen;
  semilla?: number;
  sinConexion?: SinConexion;
  persistir?: () => Promise<"concedida" | "denegada" | "no-disponible">;
}

function pintar(opciones: Opciones = {}) {
  let reloj = BASE;
  const almacen = opciones.almacen ?? almacenEnMemoria();
  render(<App cargador={cargador} almacen={almacen} azar={azarConSemilla(opciones.semilla ?? 7)}
    ahora={() => (reloj += 1000)}
    {...(opciones.sinConexion === undefined ? {} : { sinConexion: opciones.sinConexion })}
    {...(opciones.persistir === undefined ? {} : { persistir: opciones.persistir })} />);
  return almacen;
}

/** Una serie entera son muchos toques: margen de sobra para una máquina lenta o cargada. */
const SERIE_ENTERA = 30_000;

async function abrirEntrenador(opciones: Opciones = {}) {
  // Sin la pausa que userEvent mete entre toque y toque: aquí no hace falta.
  const usuario = userEvent.setup({ delay: null });
  const almacen = pintar(opciones);
  await screen.findByText("Mete tus 4 cartas con el teclado de abajo.");
  await usuario.click(screen.getByRole("button", { name: "Entrenador" }));
  await screen.findByRole("region", { name: "Entrenador: ¿mus o corto?" });
  return { usuario, almacen };
}

async function empezarSerie(usuario: Usuario) {
  await usuario.click(screen.getByRole("button", { name: "Empezar: 10 manos" }));
}

/** La mano y la posición que se están preguntando, leídas de la pantalla. */
function situacionEnPantalla(numero: number) {
  const bloque = screen.getByRole("region", { name: `¿Mus o corto? Mano ${String(numero)} de 10` });
  const mano = within(bloque).getAllByRole("img").map((c) => SIMBOLO[c.getAttribute("aria-label") ?? ""] ?? "?").join(" ");
  const quien = /Eres (mano|segundo|tercero|postre)/.exec(bloque.textContent)?.[1] ?? "";
  return { bloque, mano, posicion: POSICION[quien] ?? 0 };
}

/** Lo que dicen los datos de esa mano: la valoración que tiene que salir en pantalla. */
async function segunLosDatos(mano: string, posicion: number, mesa = "normal"): Promise<ValoracionCorte> {
  const d = decisionDe(await datos.mesa(mesa), escalas, indiceMano(leerMano(mano)), posicion);
  if (d === null) throw new Error("falta la decisión");
  return valorarCorte(d);
}

const tituloEsperado = (v: ValoracionCorte, respuesta: "mus" | "corta"): string =>
  v.veredicto === "igual" ? "Daba igual"
    : v.perdidos[respuesta] === 0 ? "Bien"
      : v.veredicto === "mus" ? "Era mejor dar mus" : "Era mejor cortar";

describe("calculadora y entrenador", () => {
  it("la web abre en la calculadora; el modo elegido se recuerda", async () => {
    const { usuario } = await abrirEntrenador();
    expect(screen.getByRole("button", { name: "Entrenador" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByRole("tablist")).toBeNull();          // sin las pestañas de la calculadora
    expect(localStorage.getItem("mus-analytics.modo")).toBe("entrenador");
    await usuario.click(screen.getByRole("button", { name: "Calculadora" }));
    expect(screen.getByRole("tablist", { name: "Momento de la mano" })).toBeDefined();
    cleanup();
    localStorage.setItem("mus-analytics.modo", "entrenador");
    pintar();
    expect(await screen.findByRole("region", { name: "Entrenador: ¿mus o corto?" })).toBeDefined();
  });

  it("al ir al entrenador y volver, la mano de la calculadora y la serie siguen como estaban", async () => {
    const usuario = userEvent.setup({ delay: null });
    pintar();
    await screen.findByText("Mete tus 4 cartas con el teclado de abajo.");
    for (const carta of ["rey", "caballo", "cinco"]) {
      await usuario.click(screen.getByRole("button", { name: `Añadir ${carta}` }));
    }
    await usuario.click(screen.getByRole("button", { name: "Entrenador" }));
    await screen.findByRole("region", { name: "Entrenador: ¿mus o corto?" });
    await empezarSerie(usuario);
    const antes = situacionEnPantalla(1);
    await usuario.click(screen.getByRole("button", { name: "Mus" }));
    await usuario.click(screen.getByRole("button", { name: "Siguiente" }));
    const segunda = situacionEnPantalla(2).mano;

    await usuario.click(screen.getByRole("button", { name: "Calculadora" }));
    expect(screen.getByText("3/4")).toBeDefined();
    await usuario.click(screen.getByRole("button", { name: "Entrenador" }));
    expect(situacionEnPantalla(2).mano).toBe(segunda);
    expect(segunda).not.toBe(antes.mano);
  });

  it("el tipo de mesa es el mismo en los dos, y sale en el contexto de cada situación", async () => {
    const { usuario } = await abrirEntrenador();
    expect(screen.getByText(
      "La mejor jugada contra una mesa «Normal», sin contar envites, señas ni las cartas que piden los demás.",
    )).toBeDefined();
    await usuario.click(screen.getByRole("button", { name: "Se corta mucho" }));
    expect(await screen.findByText(/^La mejor jugada contra una mesa «Se corta mucho», sin contar envites/)).toBeDefined();
    expect(localStorage.getItem("mus-analytics.mesa")).toBe("se-corta");
    await empezarSerie(usuario);
    const { bloque, mano, posicion } = situacionEnPantalla(1);
    expect(within(bloque).getByText(/^La mejor jugada contra una mesa «Se corta mucho»/)).toBeDefined();
    // Se valora con los datos de esa mesa.
    const esperada = await segunLosDatos(mano, posicion, "se-corta");
    await usuario.click(screen.getByRole("button", { name: "Corto" }));
    expect(screen.getByRole("region", { name: tituloEsperado(esperada, "corta") })).toBeDefined();
  });
});

describe("una serie de «¿Mus o corto?»", () => {
  it("diez manos: cada respuesta se valora con lo que dicen los datos, se anota, y al final sale el resumen", async () => {
    const persistir = vi.fn(() => Promise.resolve("no-disponible" as const));
    const { usuario, almacen } = await abrirEntrenador({ persistir });
    await empezarSerie(usuario);
    expect(screen.queryByRole("button", { name: "Empezar: 10 manos" })).toBeNull();

    let perdidos = 0;
    const vistas = new Set<string>();
    const esperadas: Partial<Anotacion>[] = [];
    for (let n = 1; n <= 10; n++) {
      const { bloque, mano, posicion } = situacionEnPantalla(n);
      expect(posicion).toBeGreaterThan(0);
      expect(within(bloque).getAllByRole("img")).toHaveLength(4);
      // La situación dice qué han hecho los anteriores y contra qué se compara.
      expect(bloque.textContent).toMatch(posicion === 1 ? /Eres mano: hablas el primero\./ : /han? dado mus\./);
      expect(within(bloque).getByText(/^La mejor jugada contra una mesa «Normal», sin contar envites, señas ni las cartas/)).toBeDefined();
      // Antes de responder no se ve nada de la valoración.
      expect(screen.queryByText(/^Por qué/)).toBeNull();
      vistas.add(`${mano}|${String(posicion)}`);

      const respuesta = n % 2 === 0 ? "corta" : "mus";
      const esperada = await segunLosDatos(mano, posicion);
      await usuario.click(screen.getByRole("button", { name: respuesta === "mus" ? "Mus" : "Corto" }));
      const valoracion = screen.getByRole("region", { name: tituloEsperado(esperada, respuesta) });
      expect(within(valoracion).getByText(`Has respondido: ${respuesta === "mus" ? "mus" : "corto"}`)).toBeDefined();
      expect(within(valoracion).getByText("Por qué, lance a lance")).toBeDefined();
      // El contra qué se compara sigue a la vista, ahora junto a la valoración.
      expect(within(valoracion).getByText(/^La mejor jugada contra una mesa «Normal», sin contar envites/)).toBeDefined();
      expect(within(bloque).queryByText(/^La mejor jugada/)).toBeNull();
      expect(within(valoracion).getAllByRole("listitem").slice(0, 5).map((li) => li.textContent.replace(/[+−≈ \d,]+$/, "")))
        .toEqual(["Grande", "Chica", "Pares", "Juego", "Punto"]);
      if (esperada.perdidos[respuesta] > 0) {
        expect(within(valoracion).getByText(/^Pierdes /)).toBeDefined();
      }
      // Ya no se puede responder otra vez: solo seguir.
      expect(screen.queryByRole("button", { name: "Mus" })).toBeNull();
      perdidos += esperada.perdidos[respuesta];
      esperadas.push({
        ejercicio: "corte", modo: "mesa", mesa: "normal", mano, posicion, respuesta,
        mejor: esperada.veredicto, intensidad: esperada.intensidad, perdidos: esperada.perdidos[respuesta],
      });
      await usuario.click(screen.getByRole("button", { name: n === 10 ? "Ver el resumen" : "Siguiente" }));
    }
    expect(vistas.size).toBe(10);                               // sin repetir situación en la serie

    const resumen = screen.getByRole("region", { name: "Serie terminada Mesa normal" });
    const total = perdidos === 0
      ? "No has perdido nada en 10 decisiones."
      : `Has perdido ${(perdidos / 1000).toFixed(2).replace(".", ",")} tantos en 10 decisiones.`;
    expect(within(resumen).getByText(total)).toBeDefined();
    expect(within(resumen).getByText(/^A ese ritmo, /)).toBeDefined();
    expect(within(resumen).getByText(/^En una mesa «Normal» te toca decidir mus o corto en unas \d+ de cada 100 manos\.$/)).toBeDefined();
    expect(within(resumen).getAllByRole("listitem")).toHaveLength(10);

    // Las diez respuestas están guardadas, completas y en orden.
    const anotadas = leerProgreso(almacen);
    expect(anotadas).toHaveLength(10);
    expect(anotadas).toMatchObject(esperadas);
    expect(anotadas.map((a) => a.fecha)).toEqual(anotadas.map((_, i) => BASE + 1000 * (i + 1)));
    expect(anotadas.every((a) => a.datos === datos.manifiesto.generado && /^\d+\.\d+\.\d+/.test(a.web))).toBe(true);
    expect(persistir).toHaveBeenCalledTimes(1);                 // se pide una vez, con la primera respuesta

    // El progreso acumulado sale con el resumen y al volver al inicio.
    expect(screen.getByRole("region", { name: "Tu progreso Mesa normal, como en la mesa" })).toBeDefined();
    // «Otra serie» empieza otra sin pasar por el inicio.
    await usuario.click(screen.getByRole("button", { name: "Otra serie" }));
    expect(situacionEnPantalla(1).posicion).toBeGreaterThan(0);
    await usuario.click(screen.getByRole("button", { name: "Dejar la serie" }));
    expect(screen.getByRole("region", { name: "Entrenador: ¿mus o corto?" })).toBeDefined();
    const progreso = screen.getByRole("region", { name: "Tu progreso Mesa normal, como en la mesa" });
    expect(within(progreso).getByText(total)).toBeDefined();
  }, SERIE_ENTERA);

  it("cada serie es distinta", async () => {
    const { usuario } = await abrirEntrenador();
    const primeras = new Set<string>();
    for (let s = 0; s < 6; s++) {
      await empezarSerie(usuario);
      const { mano, posicion } = situacionEnPantalla(1);
      primeras.add(`${mano}|${String(posicion)}`);
      await usuario.click(screen.getByRole("button", { name: "Dejar la serie" }));
    }
    // Seis series seguidas no empiezan todas por la misma mano.
    expect(primeras.size).toBeGreaterThan(3);
  });

  it("dos toques en el mismo instante cuentan como una sola respuesta", async () => {
    const { usuario, almacen } = await abrirEntrenador();
    await empezarSerie(usuario);
    const mus = screen.getByRole("button", { name: "Mus" });
    const corto = screen.getByRole("button", { name: "Corto" });
    act(() => {
      // Sin esperar a que React vuelva a pintar entre un toque y otro.
      mus.click();
      corto.click();
      mus.click();
    });
    expect(screen.getByText("Has respondido: mus")).toBeDefined();
    expect(leerProgreso(almacen)).toHaveLength(1);
    expect(leerProgreso(almacen)[0]?.respuesta).toBe("mus");
  });

  it("«Dejar la serie» vuelve al inicio; lo ya respondido queda anotado", async () => {
    const { usuario, almacen } = await abrirEntrenador();
    await empezarSerie(usuario);
    await usuario.click(screen.getByRole("button", { name: "Corto" }));
    await usuario.click(screen.getByRole("button", { name: "Siguiente" }));
    await usuario.click(screen.getByRole("button", { name: "Dejar la serie" }));
    expect(screen.getByRole("region", { name: "Entrenador: ¿mus o corto?" })).toBeDefined();
    expect(leerProgreso(almacen)).toHaveLength(1);
  });

  it("«Ajustadas»: solo salen decisiones en que una opción es mejor, pero por poco", async () => {
    const { usuario, almacen } = await abrirEntrenador();
    await usuario.click(screen.getByRole("button", { name: "Ajustadas" }));
    expect(screen.getByText(/^Solo decisiones en que una opción es mejor, pero por poco/)).toBeDefined();
    expect(localStorage.getItem("mus-analytics.entrenador.modo")).toBe("ajustadas");
    await empezarSerie(usuario);
    for (let n = 1; n <= 10; n++) {
      const { mano, posicion } = situacionEnPantalla(n);
      const { perdidos } = await segunLosDatos(mano, posicion);
      const coste = Math.max(perdidos.mus, perdidos.corta);
      expect(coste).toBeGreaterThan(0);
      expect(coste).toBeLessThan(200);
      await usuario.click(screen.getByRole("button", { name: "Corto" }));
      await usuario.click(screen.getByRole("button", { name: n === 10 ? "Ver el resumen" : "Siguiente" }));
    }
    // En este modo no se da el ritmo por cada 100 manos, ni cuenta para el progreso «como en la mesa».
    const resumen = screen.getByRole("region", { name: "Serie terminada Mesa normal" });
    expect(within(resumen).queryByText(/^A ese ritmo/)).toBeNull();
    expect(screen.queryByRole("region", { name: /^Tu progreso/ })).toBeNull();
    expect(leerProgreso(almacen).every((a) => a.modo === "ajustadas")).toBe(true);
    // «Inicio» vuelve a la pantalla en que se eligen la mesa y el modo.
    await usuario.click(screen.getByRole("button", { name: "Inicio" }));
    expect(screen.getByRole("region", { name: "Entrenador: ¿mus o corto?" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Ajustadas" }).getAttribute("aria-pressed")).toBe("true");
  }, SERIE_ENTERA);
});

describe("el progreso guardado", () => {
  const anterior: Anotacion = {
    fecha: BASE - 86_400_000, ejercicio: "corte", modo: "mesa", mesa: "normal", mano: "7 7 4 4", posicion: 1,
    respuesta: "mus", mejor: "corta", intensidad: "clara", perdidos: 1069, datos: "2026-10-12", web: "0.2.0",
  };

  it("lo anotado otro día se lee al abrir y se le suma lo nuevo", async () => {
    const almacen = almacenEnMemoria();
    anotar(almacen, [], anterior);
    const { usuario } = await abrirEntrenador({ almacen });
    const progreso = screen.getByRole("region", { name: "Tu progreso Mesa normal, como en la mesa" });
    expect(within(progreso).getByText("Has perdido 1,07 tantos en 1 decisión.")).toBeDefined();
    expect(within(progreso).getByText("0 bien · 1 fallo claro")).toBeDefined();
    await empezarSerie(usuario);
    await usuario.click(screen.getByRole("button", { name: "Mus" }));
    expect(leerProgreso(almacen)).toHaveLength(2);
    expect(leerProgreso(almacen)[0]).toEqual(anterior);
  });

  it("el progreso es de cada mesa: en otra no sale", async () => {
    const almacen = almacenEnMemoria();
    anotar(almacen, [], anterior);
    const { usuario } = await abrirEntrenador({ almacen });
    await usuario.click(screen.getByRole("button", { name: "Mucho mus" }));
    await screen.findByText(/^La mejor jugada contra una mesa «Se da mucho mus»/);
    expect(screen.queryByRole("region", { name: /^Tu progreso/ })).toBeNull();
  });

  it("si el móvil no deja guardar, lo dice y se puede seguir", async () => {
    const lleno: Almacen = { leer: () => null, guardar: () => false };
    const { usuario } = await abrirEntrenador({ almacen: lleno });
    await empezarSerie(usuario);
    await usuario.click(screen.getByRole("button", { name: "Mus" }));
    expect(screen.getByRole("status").textContent)
      .toBe("No se ha podido guardar el progreso en este móvil: se perderá al cerrar la web.");
    await usuario.click(screen.getByRole("button", { name: "Siguiente" }));
    expect(situacionEnPantalla(2).posicion).toBeGreaterThan(0);
  });

  it("un registro que no se entiende no impide entrenar, y no se pisa", async () => {
    const almacen = almacenEnMemoria({ [CLAVE_PROGRESO]: "{esto no es un registro" });
    const { usuario } = await abrirEntrenador({ almacen });
    await empezarSerie(usuario);
    await usuario.click(screen.getByRole("button", { name: "Mus" }));
    expect(leerProgreso(almacen)).toHaveLength(1);
    expect(almacen.leer(`${CLAVE_PROGRESO}.ilegible`)).toBe("{esto no es un registro");
  });
});

describe("carga y versión nueva", () => {
  it("si los datos no cargan, lo dice y deja reintentar también desde el entrenador", async () => {
    let falla = true;
    const usuario = userEvent.setup({ delay: null });
    localStorage.setItem("mus-analytics.modo", "entrenador");
    render(<App cargador={(ruta) => (falla ? Promise.reject(new Error("sin conexión")) : cargador(ruta))}
      almacen={almacenEnMemoria()} />);
    expect(await screen.findByText(/No se han podido cargar los datos: sin conexión/)).toBeDefined();
    falla = false;
    await usuario.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("region", { name: "Entrenador: ¿mus o corto?" })).toBeDefined();
  });

  it("versión nueva con una serie a medias: avisa de que se deja, y no la toca", async () => {
    let estado: EstadoSinConexion = { tipo: "lista", version: "abc1234def567890" };
    const oyentes = new Set<() => void>();
    const actualizar = vi.fn();
    const sinConexion: SinConexion = {
      estado: () => estado,
      suscribir: (f) => {
        oyentes.add(f);
        return () => { oyentes.delete(f); };
      },
      actualizar,
    };
    const { usuario } = await abrirEntrenador({ sinConexion });
    await empezarSerie(usuario);
    const { mano } = situacionEnPantalla(1);
    estado = { tipo: "nueva", version: "abc1234def567890" };
    act(() => { for (const f of oyentes) f(); });
    expect(screen.getByText(
      "Hay una versión nueva. Al actualizar se empieza una mano nueva y se deja la serie del entrenador.",
    )).toBeDefined();
    expect(situacionEnPantalla(1).mano).toBe(mano);
    expect(actualizar).not.toHaveBeenCalled();
  });
});
