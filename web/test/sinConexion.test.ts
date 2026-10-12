/**
 * El modo sin conexión visto desde la página, con un navegador de mentira:
 * qué estado se enseña en cada momento y, sobre todo, cuándo se recarga la
 * página (solo al pasar a una versión nueva, nunca a mitad de una mano).
 */

import { describe, expect, it, vi } from "vitest";

import { type SinConexion, crearSinConexion } from "../src/sinConexion";

class Trabajador extends EventTarget {
  state = "installing";
  readonly mensajes: unknown[] = [];

  constructor(readonly version: string, readonly completa = true) {
    super();
  }

  postMessage(mensaje: { tipo: string }, puertos?: MessagePort[]): void {
    this.mensajes.push(mensaje);
    if (mensaje.tipo === "estado") puertos?.[0]?.postMessage({ version: this.version, completa: this.completa });
  }

  pasarA(estado: string): void {
    this.state = estado;
    this.dispatchEvent(new Event("statechange"));
  }
}

class Registro extends EventTarget {
  installing: Trabajador | null = null;
  waiting: Trabajador | null = null;
  active: Trabajador | null = null;
  comprobaciones = 0;

  update(): Promise<void> {
    this.comprobaciones++;
    return Promise.resolve();
  }
}

class Contenedor extends EventTarget {
  controller: Trabajador | null = null;
  readonly registro = new Registro();
  readonly registrados: unknown[][] = [];
  falla = false;

  register(...argumentos: unknown[]): Promise<Registro> {
    this.registrados.push(argumentos);
    return this.falla ? Promise.reject(new Error("sin red")) : Promise.resolve(this.registro);
  }

  /** El navegador encuentra una versión nueva y empieza a instalarla. */
  encontrar(nuevo: Trabajador): void {
    this.registro.installing = nuevo;
    this.registro.dispatchEvent(new Event("updatefound"));
  }

  /** La versión nueva toma el mando. */
  mandar(sw: Trabajador): void {
    this.controller = sw;
    this.registro.active = sw;
    this.registro.waiting = null;
    this.dispatchEvent(new Event("controllerchange"));
  }
}

class Documento extends EventTarget {
  visibilityState = "visible";

  volver(): void {
    this.visibilityState = "visible";
    this.dispatchEvent(new Event("visibilitychange"));
  }
}

function montar(preparar: (c: Contenedor) => void = () => undefined) {
  const contenedor = new Contenedor();
  preparar(contenedor);
  const recargar = vi.fn();
  const documento = new Documento();
  const reloj = { ahora: 0 };
  const sc = crearSinConexion(contenedor as unknown as ServiceWorkerContainer, {
    url: "./sw.js", recargar, documento, ahora: () => reloj.ahora,
  });
  const avisos = vi.fn();
  sc.suscribir(avisos);
  return { contenedor, registro: contenedor.registro, recargar, documento, reloj, sc, avisos };
}

const llega = (sc: SinConexion, esperado: unknown) => vi.waitFor(() => { expect(sc.estado()).toEqual(esperado); });
/** Deja que se resuelvan el registro y los mensajes pendientes. */
const asentar = () => new Promise((r) => setTimeout(r, 20));

describe("sin service worker", () => {
  it("por la red local o en un navegador que no lo admite, no hace nada", () => {
    const sc = crearSinConexion(undefined, { url: "./sw.js", recargar: () => { throw new Error("no debe recargar"); } });
    expect(sc.estado()).toEqual({ tipo: "no-disponible" });
    sc.actualizar();
    sc.suscribir(() => undefined)();
  });
});

describe("la primera vez", () => {
  it("registra sw.js sin caché HTTP, guarda la web y avisa cuando está lista, sin recargar", async () => {
    const sw = new Trabajador("aaaaaaa1");
    const m = montar((c) => { c.registro.installing = sw; });
    expect(m.sc.estado()).toEqual({ tipo: "preparando" });
    expect(m.contenedor.registrados).toEqual([["./sw.js", { updateViaCache: "none" }]]);
    await asentar();
    sw.pasarA("installed");
    expect(m.sc.estado()).toEqual({ tipo: "preparando" });
    sw.pasarA("activated");
    m.contenedor.mandar(sw);
    await llega(m.sc, { tipo: "lista", version: "aaaaaaa1" });
    expect(m.avisos).toHaveBeenCalled();
    expect(m.recargar).not.toHaveBeenCalled();
  });

  it("si la descarga falla, lo dice", async () => {
    const sw = new Trabajador("aaaaaaa1");
    const m = montar((c) => { c.registro.installing = sw; });
    await asentar();
    sw.pasarA("redundant");
    expect(m.sc.estado()).toEqual({ tipo: "error" });
  });

  it("si no se puede registrar, lo dice", async () => {
    const m = montar((c) => { c.falla = true; });
    await llega(m.sc, { tipo: "error" });
  });
});

describe("con una versión ya guardada", () => {
  const conVersion = () => {
    const uno = new Trabajador("aaaaaaa1");
    const m = montar((c) => { c.controller = uno; c.registro.active = uno; });
    return { ...m, uno };
  };

  it("pregunta al service worker y enseña «lista» con su versión", async () => {
    const m = conVersion();
    await llega(m.sc, { tipo: "lista", version: "aaaaaaa1" });
    expect(m.recargar).not.toHaveBeenCalled();
  });

  it("si el navegador vació la caché y no se pudo rehacer, lo dice", async () => {
    const rota = new Trabajador("aaaaaaa1", false);
    const m = montar((c) => { c.controller = rota; });
    await llega(m.sc, { tipo: "error" });
  });

  it("tras una recarga forzada (nadie manda en la página), pregunta al activo", async () => {
    const uno = new Trabajador("aaaaaaa1");
    const m = montar((c) => { c.registro.active = uno; });
    await llega(m.sc, { tipo: "lista", version: "aaaaaaa1" });
  });

  it("versión nueva: avisa sin recargar; solo al pulsar «Actualizar» le da paso y recarga una vez", async () => {
    const m = conVersion();
    await llega(m.sc, { tipo: "lista", version: "aaaaaaa1" });
    const dos = new Trabajador("bbbbbbb2");
    m.contenedor.encontrar(dos);
    expect(m.sc.estado().tipo).toBe("lista"); // descargando: aún no se dice nada
    m.registro.installing = null;
    m.registro.waiting = dos;
    dos.pasarA("installed");
    expect(m.sc.estado()).toEqual({ tipo: "nueva", version: "aaaaaaa1" });
    expect(dos.mensajes).toEqual([]);
    expect(m.recargar).not.toHaveBeenCalled();

    m.sc.actualizar();
    expect(dos.mensajes).toEqual([{ tipo: "activar" }]);
    expect(m.recargar).not.toHaveBeenCalled(); // hasta que la nueva tome el mando
    m.contenedor.mandar(dos);
    m.contenedor.dispatchEvent(new Event("controllerchange"));
    expect(m.recargar).toHaveBeenCalledTimes(1);
  });

  it("«Actualizar» no hace nada si no hay versión nueva", async () => {
    const m = conVersion();
    await llega(m.sc, { tipo: "lista", version: "aaaaaaa1" });
    m.sc.actualizar();
    expect(m.uno.mensajes).toEqual([{ tipo: "estado" }]);
    expect(m.recargar).not.toHaveBeenCalled();
  });

  it("si la descarga de la versión nueva falla, todo sigue igual", async () => {
    const m = conVersion();
    await llega(m.sc, { tipo: "lista", version: "aaaaaaa1" });
    const dos = new Trabajador("bbbbbbb2");
    m.contenedor.encontrar(dos);
    dos.pasarA("redundant");
    expect(m.sc.estado()).toEqual({ tipo: "lista", version: "aaaaaaa1" });
    expect(m.recargar).not.toHaveBeenCalled();
  });

  it("si al abrir ya había una versión esperando, le da paso sin preguntar", async () => {
    const uno = new Trabajador("aaaaaaa1");
    const dos = new Trabajador("bbbbbbb2");
    const m = montar((c) => { c.controller = uno; c.registro.active = uno; c.registro.waiting = dos; });
    await vi.waitFor(() => { expect(dos.mensajes).toEqual([{ tipo: "activar" }]); });
    m.contenedor.mandar(dos);
    expect(m.recargar).toHaveBeenCalledTimes(1);
  });

  it("al volver a la web busca una versión nueva, como mucho una vez por minuto", async () => {
    const m = conVersion();
    await asentar();
    m.documento.volver();
    expect(m.registro.comprobaciones).toBe(0); // acaba de abrirse
    m.reloj.ahora = 61_000;
    m.documento.visibilityState = "hidden";
    m.documento.dispatchEvent(new Event("visibilitychange"));
    expect(m.registro.comprobaciones).toBe(0); // al irse no
    m.documento.volver();
    expect(m.registro.comprobaciones).toBe(1);
    m.reloj.ahora = 90_000;
    m.documento.volver();
    expect(m.registro.comprobaciones).toBe(1);
    m.reloj.ahora = 125_000;
    m.documento.volver();
    expect(m.registro.comprobaciones).toBe(2);
  });
});
