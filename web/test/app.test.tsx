// @vitest-environment jsdom
/**
 * La web entera, como la usaría un jugador: pulsar cartas, elegir posición,
 * marcar señas, decir que ha habido mus... con los datos reales.
 */

import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import { leerDato } from "./ayuda";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});

const cargador = (ruta: string) => Promise.resolve(leerDato(ruta));

async function empezar() {
  const usuario = userEvent.setup();
  render(<App cargador={cargador} />);
  await screen.findByText("Mete tus 4 cartas con el teclado de abajo.");
  return usuario;
}

async function meterCartas(usuario: ReturnType<typeof userEvent.setup>, nombres: string[]) {
  for (const n of nombres) {
    await usuario.click(screen.getByRole("button", { name: `Añadir ${n}` }));
  }
}

describe("la calculadora", () => {
  it("R C 5 4 de mano en una mesa normal: da mus y quédate con R C", async () => {
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    expect(screen.getByText("Sin pares · Sin juego: 29 al punto")).toBeDefined();
    expect(screen.getByText("¿En qué posición estás? Elígela arriba.")).toBeDefined();
    // Con las 4 cartas, el teclado deja sitio a la barra de abajo.
    expect(screen.queryByRole("group", { name: "Teclado de cartas" })).toBeNull();

    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    const decision = await screen.findByRole("region", { name: /¿Mus o corto\? Siendo mano/ });
    expect(within(decision).getByText("Da mus")).toBeDefined();
    expect(within(decision).getByText(/^Si das mus, tu pareja saca de media/)).toBeDefined();
    const descartes = screen.getByRole("region", { name: "Si hay mus, ¿qué tiro?" });
    expect(within(descartes).getAllByText("Quédate con R C").length).toBeGreaterThan(0);
    expect(await screen.findByRole("region", { name: "Si se juega con estas cartas" })).toBeDefined();
  });

  it("cambiar el tipo de mesa cambia la recomendación y se recuerda", async () => {
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    await screen.findByText("Da mus");
    await usuario.click(screen.getByRole("button", { name: "Se corta mucho" }));
    expect(await screen.findByText("Corta")).toBeDefined();
    expect(localStorage.getItem("mus-analytics.mesa")).toBe("se-corta");
  });

  it("las señas cambian las probabilidades y avisan si son imposibles", async () => {
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    await screen.findByRole("region", { name: "Si se juega con estas cartas" });
    await usuario.click(screen.getByRole("button", { name: /¿Qué te ha dicho tu compañero\?/ }));
    await usuario.click(screen.getByRole("button", { name: "Dos reyes" }));
    expect(await screen.findByText(/Sabiendo que tu compañero tiene: dos reyes\./)).toBeDefined();
    await usuario.click(screen.getByRole("button", { name: "Tres reyes" }));
    expect(screen.getByText("Esas señas no pueden ir juntas: ninguna mano las cumple todas.")).toBeDefined();
    expect(screen.getByText("Corrige las señas para ver las probabilidades de ganar.")).toBeDefined();
  });

  it("la chuleta de señas se abre y se cierra", async () => {
    const usuario = await empezar();
    await usuario.click(screen.getByRole("button", { name: /¿Qué te ha dicho tu compañero\?/ }));
    await usuario.click(screen.getByRole("button", { name: "Ver la chuleta de señas" }));
    const chuleta = screen.getByRole("dialog", { name: "Chuleta de señas" });
    expect(within(chuleta).getByText("Guiñar un ojo")).toBeDefined();
    await usuario.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("tras el mus: se meten las cartas nuevas y salen las probabilidades sin señas", async () => {
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await usuario.click(screen.getByRole("button", { name: "Postre" }));
    await screen.findByRole("region", { name: /¿Mus o corto\?/ });
    await usuario.click(screen.getByRole("button", { name: "Ha habido mus" }));
    expect(screen.getByText("Tu mano después del mus")).toBeDefined();
    expect(screen.getByText("Mete las 4 cartas que tienes después del mus.")).toBeDefined();
    await meterCartas(usuario, ["rey", "rey", "caballo", "sota"]);
    const tras = await screen.findByRole("region", { name: "Tras el mus" });
    expect(within(tras).getByText(/Ganáis la grande/)).toBeDefined();
    expect(screen.queryByRole("region", { name: /¿Mus o corto\?/ })).toBeNull();
    expect(screen.getByText("No se usan tras el mus")).toBeDefined();

    await usuario.click(screen.getByRole("button", { name: "Nueva mano" }));
    expect(screen.getByText("Tu mano")).toBeDefined();
    expect(screen.getByText("Mete tus 4 cartas con el teclado de abajo.")).toBeDefined();
  });

  it("dos toques en el mismo instante no pierden ninguna carta, y no entran más de 4", async () => {
    await empezar();
    const rey = screen.getByRole("button", { name: "Añadir rey" });
    const as = screen.getByRole("button", { name: "Añadir as" });
    act(() => {
      // Sin esperar a que React vuelva a pintar entre un toque y otro.
      rey.click();
      as.click();
    });
    expect(screen.getByText("2/4")).toBeDefined();
    act(() => {
      for (let i = 0; i < 5; i++) rey.click();
    });
    expect(screen.getAllByRole("img", { name: "rey" })).toHaveLength(3);
  });

  it("quitar una carta tocándola y borrar la última", async () => {
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "rey", "caballo"]);
    await usuario.click(screen.getByRole("button", { name: "Quitar carta 1" }));
    expect(screen.getByText("2/4")).toBeDefined();
    await usuario.click(screen.getByRole("button", { name: "⌫ Borrar" }));
    expect(screen.getByText("1/4")).toBeDefined();
  });

  it("funciona igual sin crypto.subtle (abierta por la red local, sin HTTPS)", async () => {
    vi.stubGlobal("crypto", {});
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    expect(await screen.findByText("Da mus")).toBeDefined();
    expect(await screen.findByRole("region", { name: "Si se juega con estas cartas" })).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("si falla el fichero de la mesa, el mensaje concuerda: «No se ha podido cargar la recomendación»", async () => {
    const usuario = userEvent.setup();
    render(<App cargador={(ruta) => (ruta.startsWith("mesa-")
      ? Promise.reject(new Error("no hay conexión con el servidor de la web"))
      : cargador(ruta))} />);
    await screen.findByText("Mete tus 4 cartas con el teclado de abajo.");
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    expect(await screen.findByText(/^No se ha podido cargar la recomendación: no hay conexión/)).toBeDefined();
    expect(screen.getByText(/^No se han podido cargar los descartes/)).toBeDefined();
  });

  it("si los datos no cargan, lo dice y deja reintentar", async () => {
    let falla = true;
    const usuario = userEvent.setup();
    render(<App cargador={(ruta) => (falla ? Promise.reject(new Error("sin conexión")) : cargador(ruta))} />);
    expect(await screen.findByText(/No se han podido cargar los datos: sin conexión/)).toBeDefined();
    falla = false;
    await usuario.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Mete tus 4 cartas con el teclado de abajo.")).toBeDefined();
  });
});
