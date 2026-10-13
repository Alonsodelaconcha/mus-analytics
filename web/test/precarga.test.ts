/**
 * Lo que hace el plugin al construir la web: la lista de ficheros con sus
 * huellas (de la que sale la versión), la comprobación de los datos contra el
 * manifiesto y las licencias de terceros.
 */

import { cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, describe, expect, it } from "vitest";

import {
  commitDe,
  comprobarDatos,
  crearPrecarga,
  licenciasDeTerceros,
  listarFicheros,
  paqueteDe,
} from "../plugins/sinConexion";

const WEB = process.cwd();
const temporales: string[] = [];

function carpeta(ficheros: Record<string, string>): string {
  const raiz = mkdtempSync(join(tmpdir(), "mus-precarga-"));
  temporales.push(raiz);
  for (const [ruta, contenido] of Object.entries(ficheros)) {
    mkdirSync(join(raiz, ruta, ".."), { recursive: true });
    writeFileSync(join(raiz, ruta), contenido);
  }
  return raiz;
}

afterAll(() => {
  for (const t of temporales) rmSync(t, { recursive: true, force: true });
});

const WEB_PEQUENA = { "index.html": "<p>hola</p>", "assets/app.js": "app()", "datos/equity/a.json": "{}", "sw.js": "viejo" };

describe("la lista de ficheros de una versión", () => {
  it("recorre las subcarpetas, con rutas con «/» y en orden", () => {
    expect(listarFicheros(carpeta(WEB_PEQUENA))).toEqual(["assets/app.js", "datos/equity/a.json", "index.html", "sw.js"]);
  });

  it("lleva la huella de cada fichero y deja fuera sw.js", () => {
    const p = crearPrecarga(carpeta(WEB_PEQUENA));
    expect(p.ficheros.map((f) => f.ruta)).toEqual(["assets/app.js", "datos/equity/a.json", "index.html"]);
    // SHA-256 de "{}"
    expect(p.ficheros[1]?.sha256).toBe("44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a");
    expect(p.version).toMatch(/^[0-9a-f]{16}$/);
  });

  it("la versión es la misma con los mismos ficheros y cambia con cualquier cambio", () => {
    const base = crearPrecarga(carpeta(WEB_PEQUENA)).version;
    expect(crearPrecarga(carpeta({ ...WEB_PEQUENA, "sw.js": "otro" })).version).toBe(base);
    const cambios: Record<string, string>[] = [
      { ...WEB_PEQUENA, "assets/app.js": "app2()" }, // cambia el código
      { ...WEB_PEQUENA, "datos/equity/a.json": "{ }" }, // cambia un dato
      { ...WEB_PEQUENA, "datos/equity/b.json": "{}" }, // fichero nuevo
      { "index.html": "<p>hola</p>", "assets/app.js": "app()" }, // fichero que desaparece
      { "index.html": "<p>hola</p>", "assets/app2.js": "app()", "datos/equity/a.json": "{}" }, // cambia de nombre
    ];
    const versiones = cambios.map((c) => crearPrecarga(carpeta(c)).version);
    expect(new Set([base, ...versiones]).size).toBe(cambios.length + 1);
  });
});

describe("los datos publicados son los del manifiesto", () => {
  const publicados = (): string => {
    const raiz = carpeta({});
    cpSync(join(WEB, "public", "datos"), join(raiz, "datos"), { recursive: true });
    return raiz;
  };

  it("los datos de public/ coinciden con las huellas de su manifiesto", () => {
    const raiz = join(WEB, "public");
    const p = crearPrecarga(raiz);
    expect(p.ficheros.filter((f) => f.ruta.startsWith("datos/"))).toHaveLength(21);
    expect(() => { comprobarDatos(raiz, p); }).not.toThrow();
  });

  it("falla si un fichero de datos cambia, aunque sea un fin de línea", () => {
    const raiz = publicados();
    writeFileSync(join(raiz, "datos", "mesa-normal.json"), "\n", { flag: "a" });
    expect(() => { comprobarDatos(raiz, crearPrecarga(raiz)); }).toThrow(/mesa-normal\.json no coincide/);
  });

  it("falla si falta un fichero de datos", () => {
    const raiz = publicados();
    rmSync(join(raiz, "datos", "equity", "ciego.json"));
    expect(() => { comprobarDatos(raiz, crearPrecarga(raiz)); }).toThrow(/Falta el fichero de datos equity\/ciego\.json/);
  });

  it("falla si hay un fichero de datos que el manifiesto no conoce", () => {
    const raiz = publicados();
    writeFileSync(join(raiz, "datos", "equity", "sobra.json"), "{}");
    expect(() => { comprobarDatos(raiz, crearPrecarga(raiz)); }).toThrow(/no están en el manifiesto: equity\/sobra\.json/);
  });
});

describe("licencias de terceros", () => {
  it.each([
    ["C:\\proyecto\\web\\node_modules\\react-dom\\cjs\\react-dom-client.production.js", "C:/proyecto/web/node_modules/react-dom"],
    ["/proyecto/node_modules/@alcance/paquete/index.js", "/proyecto/node_modules/@alcance/paquete"],
    ["/proyecto/node_modules/a/node_modules/b/index.js", "/proyecto/node_modules/a/node_modules/b"],
    ["/proyecto/web/src/App.tsx", null],
    ["\0vite/preload-helper.js", null],
  ])("paquete al que pertenece %s", (id, esperado) => {
    expect(paqueteDe(id)).toBe(esperado);
  });

  it("recoge el texto de la licencia de cada librería empaquetada, una vez", () => {
    const react = join(WEB, "node_modules", "react");
    const texto = licenciasDeTerceros([react, join(WEB, "node_modules", "scheduler"), react]);
    expect(texto.match(/^react \d+\.\d+\.\d+ \(MIT\)$/gm)).toHaveLength(1);
    expect(texto).toMatch(/^scheduler \d+\.\d+\.\d+ \(MIT\)$/m);
    expect(texto.match(/Permission is hereby granted, free of charge/g)).toHaveLength(2);
    expect(texto).toContain("Copyright (c) Meta Platforms, Inc. and affiliates.");
  });
});

describe("el commit del que se construye la web", () => {
  /** Un git de mentira: responde a cada orden (rev-parse, status) lo que se le diga. */
  const git = (salidas: Record<string, string>) => (argumentos: string[]) => salidas[argumentos[0] ?? ""] ?? "";

  it("abreviado, y con un «+» si en la carpeta hay cambios sin confirmar", () => {
    expect(commitDe(".", git({ "rev-parse": "01c64d0\n", status: "" }))).toBe("01c64d0");
    expect(commitDe(".", git({ "rev-parse": "01c64d0\n", status: " M src/App.tsx\n" }))).toBe("01c64d0+");
  });

  it("sin git, o si responde otra cosa, no hay commit", () => {
    expect(commitDe(".", () => { throw new Error("no hay git"); })).toBeNull();
    expect(commitDe(".", git({ "rev-parse": "fatal: not a git repository" }))).toBeNull();
  });

  it("en este repositorio da un commit de verdad", () => {
    expect(commitDe(WEB)).toMatch(/^[0-9a-f]{7,40}\+?$/);
  });
});
