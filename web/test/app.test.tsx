// @vitest-environment jsdom
/**
 * La web entera, como la usaría un jugador: pulsar cartas, elegir posición,
 * cambiar de pestaña, marcar señas... con los datos reales.
 */

import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import { type EstadoSinConexion, type SinConexion } from "../src/sinConexion";
import { leerDato } from "./ayuda";

beforeAll(() => {
  // jsdom no desplaza la página: basta con que exista.
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});

const cargador = (ruta: string) => Promise.resolve(leerDato(ruta));
type Usuario = ReturnType<typeof userEvent.setup>;

async function empezar() {
  const usuario = userEvent.setup();
  render(<App cargador={cargador} />);
  await screen.findByText("Mete tus 4 cartas con el teclado de abajo.");
  return usuario;
}

async function meterCartas(usuario: Usuario, nombres: string[]) {
  for (const n of nombres) {
    await usuario.click(screen.getByRole("button", { name: `Añadir ${n}` }));
  }
}

const PESTANA = { decidir: /^¿Mus o corto\?/, cortado: /^Se ha cortado/, mus: /^Ha habido mus/ } as const;

async function irA(usuario: Usuario, pestana: keyof typeof PESTANA) {
  await usuario.click(screen.getByRole("tab", { name: PESTANA[pestana] }));
}

function pestanaAbierta(): keyof typeof PESTANA {
  const abierta = screen.getByRole("tab", { selected: true }).textContent;
  const p = (Object.keys(PESTANA) as (keyof typeof PESTANA)[]).find((k) => PESTANA[k].test(abierta));
  if (p === undefined) throw new Error(`pestaña desconocida: ${abierta}`);
  return p;
}

/** Las cartas que se ven en la mano, de mayor a menor. */
function cartasEnMano(): (string | null)[] {
  const mano = screen.getByRole("region", { name: /^Tu mano/ });
  return within(mano).queryAllByRole("img").map((c) => c.getAttribute("aria-label"));
}

const pulsado = (nombre: string) => screen.getByRole("button", { name: nombre }).getAttribute("aria-pressed");

describe("la calculadora", () => {
  it("R C 5 4 de mano en una mesa normal: da mus y quédate con R C", async () => {
    const usuario = await empezar();
    expect(pestanaAbierta()).toBe("decidir");
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    expect(screen.getByText("Sin pares")).toBeDefined();
    expect(screen.getByText("29 al punto")).toBeDefined();
    expect(screen.getByText("¿En qué posición estás? Elígela arriba.")).toBeDefined();
    // Con las 4 cartas, el teclado deja sitio a «Nueva mano»; las pestañas siguen abajo.
    expect(screen.queryByRole("group", { name: "Teclado de cartas" })).toBeNull();
    expect(screen.getByRole("tablist", { name: "Momento de la mano" })).toBeDefined();

    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    const decision = await screen.findByRole("region", { name: /¿Mus o corto\? Siendo mano/ });
    expect(within(decision).getByText("Da mus")).toBeDefined();
    expect(within(decision).getByText(/^Si das mus, tu pareja saca de media/)).toBeDefined();
    const descartes = screen.getByRole("region", { name: "Si hay mus, ¿qué tiro?" });
    expect(within(descartes).getAllByText("Quédate con R C").length).toBeGreaterThan(0);
  });

  it("«¿Mus o corto?» no deja marcar señas y dice siempre que no las tiene en cuenta", async () => {
    const usuario = await empezar();
    await meterCartas(usuario, ["as", "as", "cuatro", "cinco"]);
    await usuario.click(screen.getByRole("button", { name: "Postre" }));
    const decision = await screen.findByRole("region", { name: /¿Mus o corto\?/ });
    expect(within(decision).getByText("No tiene en cuenta las señas de tu compañero.")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Ciego" })).toBeNull();
    // Con señas marcadas en «Se ha cortado», la recomendación es la misma.
    await irA(usuario, "cortado");
    await usuario.click(screen.getByRole("button", { name: "Ciego" }));
    await irA(usuario, "decidir");
    const otra = await screen.findByRole("region", { name: /¿Mus o corto\?/ });
    expect(within(otra).getByText("Corta")).toBeDefined();
    expect(within(otra).getByText("No tiene en cuenta las señas de tu compañero.")).toBeDefined();
  });

  it("cambiar el tipo de mesa cambia la recomendación y se recuerda", async () => {
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    await screen.findByText("Da mus");
    expect(screen.getByText("Mesa: normal")).toBeDefined();
    await usuario.click(screen.getByRole("button", { name: "Se corta mucho" }));
    expect(await screen.findByText("Corta")).toBeDefined();
    expect(screen.getByText("Mesa: se corta mucho")).toBeDefined();
    expect(localStorage.getItem("mus-analytics.mesa")).toBe("se-corta");
  });

  it("«Se ha cortado»: las cinco probabilidades en fila y, al tocar un lance, el detalle", async () => {
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    await irA(usuario, "cortado");
    const fila = await screen.findByRole("region", { name: "Si se juega con estas cartas, ganáis…" });
    expect(within(fila).getByText("Exacto, sin señas de tu compañero.")).toBeDefined();
    const lances = ["Grande", "Chica", "Pares", "Juego", "Punto"].map((l) =>
      within(fila).getByRole("button", { name: new RegExp(`^${l}`) }));
    // Cada lance: el porcentaje de la pareja y la frecuencia en corto.
    for (const lance of lances) expect(lance.textContent).toMatch(/\d+\s%(\d+ de \d+|casi \w+)$/);
    expect(within(fila).getByText(/^Toca un lance/)).toBeDefined();

    await usuario.click(within(fila).getByRole("button", { name: /^Grande/ }));
    expect(within(fila).getByText(/^Ganáis la grande/)).toBeDefined();
    expect(within(fila).getByText(/^Tú solo: \d+\s%\.$/)).toBeDefined();
    expect(within(fila).getByRole("button", { name: /^Grande/ }).getAttribute("aria-pressed")).toBe("true");
    // Otro toque en el mismo lance lo cierra.
    await usuario.click(within(fila).getByRole("button", { name: /^Grande/ }));
    expect(within(fila).queryByText(/^Ganáis la grande/)).toBeNull();
  });

  it("las señas cambian las probabilidades y avisan si son imposibles", async () => {
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    await irA(usuario, "cortado");
    const fila = await screen.findByRole("region", { name: "Si se juega con estas cartas, ganáis…" });
    const antes = within(fila).getByRole("button", { name: /^Grande/ }).textContent;
    await usuario.click(screen.getByRole("button", { name: "Dos reyes" }));
    expect(await screen.findByText("Exacto, con las señas marcadas.")).toBeDefined();
    const conSena = screen.getByRole("region", { name: "Si se juega con estas cartas, ganáis…" });
    expect(within(conSena).getByRole("button", { name: /^Grande/ }).textContent).not.toBe(antes);
    await usuario.click(screen.getByRole("button", { name: "Tres reyes" }));
    expect(screen.getByText("Esas señas no pueden ir juntas: ninguna mano las cumple todas.")).toBeDefined();
    expect(screen.getByText("Corrige las señas para ver las probabilidades de ganar.")).toBeDefined();
  });

  it("la chuleta de señas se abre y se cierra", async () => {
    const usuario = await empezar();
    await irA(usuario, "cortado");
    await usuario.click(screen.getByRole("button", { name: "Chuleta" }));
    const chuleta = screen.getByRole("dialog", { name: "Chuleta de señas" });
    expect(within(chuleta).getByText("Guiñar un ojo")).toBeDefined();
    await usuario.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("«Ha habido mus»: se meten las cartas nuevas y salen las probabilidades sin señas", async () => {
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await usuario.click(screen.getByRole("button", { name: "Postre" }));
    await screen.findByRole("region", { name: /¿Mus o corto\?/ });
    await irA(usuario, "mus");
    expect(screen.getByRole("region", { name: "Tu mano después del mus" })).toBeDefined();
    expect(screen.getByText("Mete las 4 cartas que tienes después del mus.")).toBeDefined();
    expect(screen.getByText("Cartas después del mus · eres postre")).toBeDefined();
    await meterCartas(usuario, ["rey", "rey", "caballo", "sota"]);
    const tras = await screen.findByRole("region", { name: "Tras el mus" });
    expect(within(tras).getByText(/Ganáis la grande/)).toBeDefined();
    expect(screen.queryByRole("region", { name: /¿Mus o corto\?/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Dos reyes" })).toBeNull();
  });
});

describe("pestañas", () => {
  it("completar las cartas no cambia de pestaña, en ninguna de las tres", async () => {
    const usuario = await empezar();
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    for (const p of ["decidir", "cortado", "mus"] as const) {
      await irA(usuario, p);
      if (cartasEnMano().length === 4) await usuario.click(screen.getByRole("button", { name: "Nueva mano" }));
      await irA(usuario, p);
      await meterCartas(usuario, ["rey", "caballo", "sota", "as"]);
      expect(cartasEnMano()).toHaveLength(4);
      expect(pestanaAbierta(), p).toBe(p);
    }
  });

  it("«Se ha cortado» conserva las cartas; «Ha habido mus» las vacía y quita las señas; " +
    "al volver se restaura la mano repartida", async () => {
    const usuario = await empezar();
    await usuario.click(screen.getByRole("button", { name: "Tercero" }));
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    const repartida = ["rey", "caballo", "cinco", "cuatro"];

    await irA(usuario, "cortado");
    expect(cartasEnMano()).toEqual(repartida);
    await usuario.click(screen.getByRole("button", { name: "Dos reyes" }));

    // Un toque equivocado en «Ha habido mus»: mano vacía, sin señas.
    await irA(usuario, "mus");
    expect(cartasEnMano()).toEqual([]);
    expect(screen.queryByRole("button", { name: "Dos reyes" })).toBeNull();
    await meterCartas(usuario, ["sota", "sota"]);
    expect(cartasEnMano()).toEqual(["sota", "sota"]);

    // De vuelta, la mano repartida y sus señas, como estaban.
    await irA(usuario, "cortado");
    expect(cartasEnMano()).toEqual(repartida);
    expect(pulsado("Dos reyes")).toBe("true");
    expect(await screen.findByText("Exacto, con las señas marcadas.")).toBeDefined();
    await irA(usuario, "mus");
    expect(cartasEnMano()).toEqual([]);
    await irA(usuario, "decidir");
    expect(cartasEnMano()).toEqual(repartida);
    expect(await screen.findByRole("region", { name: /¿Mus o corto\? Siendo tercero/ })).toBeDefined();

    // La posición no ha cambiado en ningún momento.
    expect(pulsado("Tercero")).toBe("true");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("«Nueva mano» abre «¿Mus o corto?», vacía todo y gira la posición", async () => {
    const usuario = await empezar();
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await irA(usuario, "cortado");
    await usuario.click(screen.getByRole("button", { name: "Dos reyes" }));
    await irA(usuario, "mus");
    await meterCartas(usuario, ["rey", "rey", "caballo", "sota"]);
    await usuario.click(screen.getByRole("button", { name: "Nueva mano" }));
    expect(pestanaAbierta()).toBe("decidir");
    expect(cartasEnMano()).toEqual([]);
    expect(pulsado("Postre")).toBe("true");
    // Las señas de la mano anterior tampoco vuelven.
    await irA(usuario, "cortado");
    expect(cartasEnMano()).toEqual([]);
    expect(pulsado("Dos reyes")).toBe("false");
  });

  it("las flechas del teclado cambian de pestaña", async () => {
    const usuario = await empezar();
    screen.getByRole("tab", { name: PESTANA.decidir }).focus();
    await usuario.keyboard("{ArrowRight}");
    expect(pestanaAbierta()).toBe("cortado");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: PESTANA.cortado }));
    await usuario.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(pestanaAbierta()).toBe("mus");
    expect(screen.getByRole("tabpanel").getAttribute("aria-labelledby")).toBe("pestana-mus");
  });
});

describe("posición y cartas", () => {
  it("«Nueva mano» gira la posición, lo anuncia y se corrige con un toque", async () => {
    const usuario = await empezar();
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    expect(screen.getByText("Tus cartas · eres mano")).toBeDefined();
    await usuario.click(screen.getByRole("button", { name: "Nueva mano" }));
    expect(screen.getByRole("status").textContent).toMatch(/Nueva mano: ahora eres postre \(antes, mano\)/);
    expect(pulsado("Postre")).toBe("true");
    expect(screen.getByText("Tus cartas · eres postre")).toBeDefined();
    // Pulsada otra vez por error: lo dice.
    await usuario.click(screen.getByRole("button", { name: "Nueva mano" }));
    expect(screen.getByRole("status").textContent).toMatch(/2 veces seguidas: ahora eres tercero \(antes, mano\)/);
    // Un toque en la posición buena lo corrige y retira el aviso.
    await usuario.click(screen.getByRole("button", { name: "Postre" }));
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText("Tus cartas · eres postre")).toBeDefined();
  });

  it("cambiar de pestaña o borrar cartas no gira la posición", async () => {
    const usuario = await empezar();
    await usuario.click(screen.getByRole("button", { name: "Segundo" }));
    await meterCartas(usuario, ["rey", "sota"]);
    await usuario.click(screen.getByRole("button", { name: "⌫ Borrar" }));
    for (const p of ["mus", "cortado", "decidir", "mus"] as const) await irA(usuario, p);
    expect(pulsado("Segundo")).toBe("true");
    expect(screen.queryByRole("status")).toBeNull();
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
    expect(cartasEnMano().filter((c) => c === "rey")).toHaveLength(3);
  });

  it("quitar una carta tocándola y borrar la última", async () => {
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "rey", "caballo"]);
    await usuario.click(screen.getByRole("button", { name: "Quitar carta 1" }));
    expect(screen.getByText("2/4")).toBeDefined();
    await usuario.click(screen.getByRole("button", { name: "⌫ Borrar" }));
    expect(screen.getByText("1/4")).toBeDefined();
  });
});

describe("carga de datos", () => {
  it("funciona igual sin crypto.subtle (abierta por la red local, sin HTTPS)", async () => {
    vi.stubGlobal("crypto", {});
    const usuario = await empezar();
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    expect(await screen.findByText("Da mus")).toBeDefined();
    await irA(usuario, "cortado");
    expect(await screen.findByRole("region", { name: "Si se juega con estas cartas, ganáis…" })).toBeDefined();
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

describe("versión y modo sin conexión", () => {
  /** Un modo sin conexión de mentira, al que se le puede cambiar el estado. */
  function sinConexionFalso(inicial: EstadoSinConexion) {
    let estado = inicial;
    const oyentes = new Set<() => void>();
    const actualizar = vi.fn();
    const sc: SinConexion = {
      estado: () => estado,
      suscribir: (f) => {
        oyentes.add(f);
        return () => { oyentes.delete(f); };
      },
      actualizar,
    };
    const poner = (nuevo: EstadoSinConexion) => {
      estado = nuevo;
      act(() => { for (const f of oyentes) f(); });
    };
    return { sc, poner, actualizar };
  }

  it("sin service worker (red local, desarrollo): lo dice en el pie, con la versión y el enlace al código", async () => {
    await empezar();
    const pie = screen.getByRole("contentinfo");
    expect(within(pie).getByText(/^Versión \d+\.\d+\.\d+ · datos del \d{4}-\d{2}-\d{2}$/)).toBeDefined();
    expect(within(pie).getByText("Aquí no se puede usar sin conexión.")).toBeDefined();
    expect(within(pie).getByRole("link", { name: "Código fuente" }).getAttribute("href"))
      .toBe("https://github.com/Alonsodelaconcha/mus-analytics");
    expect(screen.queryByRole("button", { name: "Actualizar" })).toBeNull();
  });

  it("el pie sigue el estado: guardando, lista (con el identificador de lo guardado) y error", async () => {
    const { sc, poner } = sinConexionFalso({ tipo: "preparando" });
    render(<App cargador={cargador} sinConexion={sc} />);
    await screen.findByText("Mete tus 4 cartas con el teclado de abajo.");
    const pie = screen.getByRole("contentinfo");
    expect(within(pie).getByText("Guardando la web para usarla sin conexión…")).toBeDefined();
    poner({ tipo: "lista", version: "abc1234def567890" });
    expect(within(pie).getByText("Lista para usar sin conexión.")).toBeDefined();
    expect(within(pie).getByText(/^Versión \S+ \(abc1234\) · datos del/)).toBeDefined();
    poner({ tipo: "error" });
    expect(within(pie).getByText(/^No se ha podido guardar/)).toBeDefined();
  });

  it("versión nueva: avisa arriba sin tocar la mano a medias, y «Actualizar» le da paso", async () => {
    const { sc, poner, actualizar } = sinConexionFalso({ tipo: "lista", version: "abc1234def567890" });
    const usuario = userEvent.setup();
    render(<App cargador={cargador} sinConexion={sc} />);
    await screen.findByText("Mete tus 4 cartas con el teclado de abajo.");
    await meterCartas(usuario, ["rey", "caballo", "cinco", "cuatro"]);
    await usuario.click(screen.getByRole("button", { name: "Mano" }));
    expect(await screen.findByText("Da mus")).toBeDefined();

    poner({ tipo: "nueva", version: "abc1234def567890" });
    expect(screen.getByText("Hay una versión nueva. Al actualizar se empieza una mano nueva.")).toBeDefined();
    expect(cartasEnMano()).toHaveLength(4);
    expect(screen.getByText("Da mus")).toBeDefined();
    expect(actualizar).not.toHaveBeenCalled();

    await usuario.click(screen.getByRole("button", { name: "Actualizar" }));
    expect(actualizar).toHaveBeenCalledTimes(1);
  });
});
