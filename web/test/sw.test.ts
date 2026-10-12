/**
 * La lógica del service worker con una caché y una red de mentira. Lo que
 * importa: una versión se guarda entera o no se guarda, y un fallo nunca toca
 * la versión que ya estaba. En un navegador de verdad lo comprueba
 * `npm run prueba-sin-conexion`.
 */

import { createHash } from "node:crypto";

import { describe, expect, it } from "vitest";

import {
  type Entorno,
  type Precarga,
  activar,
  estaCompleta,
  estado,
  instalar,
  nombreCache,
  rutaDe,
  servir,
} from "../sw/logica";

const BASE = "https://ejemplo.test/mus-analytics/";

function sha256(contenido: ArrayBuffer | string): string {
  return createHash("sha256").update(typeof contenido === "string" ? contenido : new Uint8Array(contenido)).digest("hex");
}

/** Una versión de la web: sus ficheros (ruta → contenido) con las huellas que les tocan. */
function version(nombre: string, ficheros: Record<string, string>): Precarga {
  return { version: nombre, ficheros: Object.entries(ficheros).map(([ruta, c]) => ({ ruta, sha256: sha256(c) })) };
}

/** Lo justo de `CacheStorage` para la lógica. */
function cachesFalsas() {
  const cajas = new Map<string, Map<string, Response>>();
  const caches = {
    open: (nombre: string) => {
      let caja = cajas.get(nombre);
      if (caja === undefined) cajas.set(nombre, caja = new Map<string, Response>());
      const contenido = caja;
      return Promise.resolve({
        put: (url: string, respuesta: Response) => Promise.resolve(void contenido.set(url, respuesta)),
        match: (url: string) => Promise.resolve(contenido.get(url)?.clone()),
        keys: () => Promise.resolve([...contenido.keys()].map((url) => ({ url }))),
      });
    },
    has: (nombre: string) => Promise.resolve(cajas.has(nombre)),
    delete: (nombre: string) => Promise.resolve(cajas.delete(nombre)),
    keys: () => Promise.resolve([...cajas.keys()]),
  };
  return { cajas, caches: caches as unknown as CacheStorage };
}

const SIN_RED = { fallo: "sin red" } as const;
const CORTE = { fallo: "corte" } as const;
type Servido = string | { estado: number } | typeof SIN_RED | typeof CORTE;

/** Una red que sirve lo que se le diga: contenido, un error del servidor, sin red o un corte a mitad. */
function red(ficheros: Record<string, Servido>) {
  const pedidas: { url: string; opciones: RequestInit }[] = [];
  const fetch: Entorno["fetch"] = (url, opciones) => {
    pedidas.push({ url, opciones });
    const servido = ficheros[url.slice(BASE.length)];
    if (servido === undefined) return Promise.resolve(new Response("no existe", { status: 404 }));
    if (servido === SIN_RED) return Promise.reject(new TypeError("Failed to fetch"));
    if (servido === CORTE) {
      const cuerpo = new ReadableStream<Uint8Array>({
        start(control) {
          control.enqueue(new TextEncoder().encode("medio fich"));
          control.error(new TypeError("network error"));
        },
      });
      return Promise.resolve(new Response(cuerpo));
    }
    if (typeof servido !== "string") {
      return Promise.resolve(new Response("error", { status: "estado" in servido ? servido.estado : 500 }));
    }
    return Promise.resolve(new Response(servido, { headers: { "content-type": "text/x-prueba", "x-otra": "no se guarda" } }));
  };
  return { fetch, pedidas };
}

function entorno(ficheros: Record<string, Servido>, guardado = cachesFalsas()) {
  const { fetch, pedidas } = red(ficheros);
  const e: Entorno = { base: BASE, caches: guardado.caches, fetch, sha256: (c) => Promise.resolve(sha256(c)) };
  return { e, pedidas, cajas: guardado.cajas, guardado };
}

const UNO = { "index.html": "<p>uno</p>", "assets/app-1.js": "uno()", "datos/manifiesto.json": '{"v":1}' };
const DOS = { "index.html": "<p>dos</p>", "assets/app-2.js": "dos()", "datos/manifiesto.json": '{"v":2}' };

async function textos(cajas: Map<string, Map<string, Response>>, nombre: string): Promise<Record<string, string>> {
  const salida: Record<string, string> = {};
  for (const [url, respuesta] of cajas.get(nombre) ?? []) salida[url.slice(BASE.length)] = await respuesta.clone().text();
  return salida;
}

describe("instalar una versión", () => {
  it("guarda todos sus ficheros, pedidos a la red sin caché HTTP, con su tipo", async () => {
    const p = version("uno", UNO);
    const { e, pedidas, cajas } = entorno(UNO);
    await instalar(p, e);
    expect(await textos(cajas, nombreCache("uno"))).toEqual(UNO);
    expect(pedidas.map((x) => x.url).sort()).toEqual(Object.keys(UNO).map((r) => BASE + r).sort());
    expect(pedidas.every((x) => x.opciones.cache === "no-store")).toBe(true);
    const guardada = await servir(p, e, "index.html");
    expect(guardada?.headers.get("content-type")).toBe("text/x-prueba");
    expect(guardada?.headers.get("x-otra")).toBeNull();
    expect(await estaCompleta(p, e)).toBe(true);
  });

  it.each<[string, Servido | undefined]>([
    ["no existe (404)", undefined],
    ["error del servidor (500)", { estado: 500 }],
    ["se va la red", SIN_RED],
    ["la descarga se corta a mitad", CORTE],
    ["llega entero pero es de otra versión", "dos(), cambiado"],
  ])("todo o nada: si un fichero falla (%s), no queda nada de la nueva y la anterior sigue entera", async (_, servido) => {
    const guardado = cachesFalsas();
    await instalar(version("uno", UNO), entorno(UNO, guardado).e);
    guardado.cajas.set("cache-de-otra-cosa", new Map());

    const servidos: Record<string, Servido> = { ...DOS };
    if (servido === undefined) delete servidos["assets/app-2.js"];
    else servidos["assets/app-2.js"] = servido;
    const { e, pedidas } = entorno(servidos, guardado);
    await expect(instalar(version("dos", DOS), e)).rejects.toThrow(/app-2\.js|fetch|network/);

    // Se intentaron todos: el fallo llegó con el resto ya descargado.
    expect(pedidas).toHaveLength(3);
    expect([...guardado.cajas.keys()].sort()).toEqual(["cache-de-otra-cosa", nombreCache("uno")]);
    expect(await textos(guardado.cajas, nombreCache("uno"))).toEqual(UNO);
    expect(await estaCompleta(version("uno", UNO), e)).toBe(true);
    expect(await estaCompleta(version("dos", DOS), e)).toBe(false);
  });

  it("tras un fallo, el siguiente intento empieza de cero y sale bien", async () => {
    const guardado = cachesFalsas();
    const p = version("dos", DOS);
    await expect(instalar(p, entorno({ ...DOS, "index.html": SIN_RED }, guardado).e)).rejects.toThrow();
    await instalar(p, entorno(DOS, guardado).e);
    expect(await textos(guardado.cajas, nombreCache("dos"))).toEqual(DOS);
  });
});

describe("activar una versión", () => {
  it("borra las cachés de las versiones anteriores y nada más", async () => {
    const guardado = cachesFalsas();
    await instalar(version("uno", UNO), entorno(UNO, guardado).e);
    const { e } = entorno(DOS, guardado);
    await instalar(version("dos", DOS), e);
    guardado.cajas.set("cache-de-otra-cosa", new Map());
    expect([...guardado.cajas.keys()]).toContain(nombreCache("uno")); // hasta ahora conviven las dos
    await activar(version("dos", DOS), e);
    expect([...guardado.cajas.keys()].sort()).toEqual(["cache-de-otra-cosa", nombreCache("dos")]);
    expect(await textos(guardado.cajas, nombreCache("dos"))).toEqual(DOS);
  });
});

describe("servir lo guardado", () => {
  const p = version("uno", UNO);

  it.each([
    ["la carpeta de la web es index.html", "GET", BASE, "index.html"],
    ["con parámetros en la dirección", "GET", `${BASE}?origen=inicio`, "index.html"],
    ["un fichero de la versión", "GET", `${BASE}datos/manifiesto.json`, "datos/manifiesto.json"],
    ["un fichero que no es de esta versión", "GET", `${BASE}assets/app-2.js`, null],
    ["el propio sw.js", "GET", `${BASE}sw.js`, null],
    ["no es una lectura", "POST", `${BASE}index.html`, null],
    ["otra carpeta del mismo dominio", "GET", "https://ejemplo.test/otra/index.html", null],
    ["otro dominio", "GET", "https://otro.test/mus-analytics/index.html", null],
  ])("%s", (_, metodo, url, esperado) => {
    expect(rutaDe(p, BASE, metodo, url)).toBe(esperado);
  });

  it("devuelve el fichero guardado, y nada si falta", async () => {
    const { e } = entorno(UNO);
    expect(await servir(p, e, "index.html")).toBeUndefined();
    await instalar(p, e);
    expect(await (await servir(p, e, "assets/app-1.js"))?.text()).toBe("uno()");
  });
});

describe("estado que se le cuenta a la página", () => {
  const p = version("uno", UNO);

  it("completa si están todos los ficheros", async () => {
    const { e, pedidas } = entorno(UNO);
    await instalar(p, e);
    pedidas.length = 0;
    expect(await estado(p, e)).toEqual({ version: "uno", completa: true });
    expect(pedidas).toHaveLength(0);
  });

  it("si el navegador ha vaciado la caché, la vuelve a guardar cuando hay red", async () => {
    const { e, cajas } = entorno(UNO);
    await instalar(p, e);
    cajas.get(nombreCache("uno"))?.delete(`${BASE}index.html`);
    expect(await estaCompleta(p, e)).toBe(false);
    expect(await estado(p, e)).toEqual({ version: "uno", completa: true });
    expect(await textos(cajas, nombreCache("uno"))).toEqual(UNO);
  });

  it("y si no hay red, dice que no está completa", async () => {
    const guardado = cachesFalsas();
    const sinRed = Object.fromEntries(Object.keys(UNO).map((r) => [r, SIN_RED]));
    expect(await estado(p, entorno(sinRed, guardado).e)).toEqual({ version: "uno", completa: false });
  });
});
