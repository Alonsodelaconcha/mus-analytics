/**
 * Plugin de Vite para el modo sin conexión. Al construir la web:
 *
 * 1. escribe `licencias-de-terceros.txt` con las licencias de las librerías
 *    que van dentro del JavaScript publicado (React);
 * 2. recorre la carpeta de salida y calcula la huella SHA-256 de cada fichero:
 *    esa lista es la `Precarga`, y su propia huella, el identificador de la versión;
 * 3. comprueba que las huellas de los datos son las del manifiesto (las que
 *    comprueba la web al cargarlos);
 * 4. construye `sw.js` con la lista dentro, siempre con ese nombre.
 *
 * Además define las constantes que enseña el pie de la web: la versión y el
 * commit del que se construye.
 *
 * Variables de entorno: `MUS_SW=emergencia` publica el *service worker* de
 * emergencia (`sw/emergencia.ts`) y una web que no registra ninguno;
 * `MUS_VERSION` cambia el número de versión que enseña la web (para las
 * pruebas de actualización, que necesitan dos versiones distintas).
 */

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";

import { type Plugin, type ResolvedConfig, build } from "vite";

import type { Precarga } from "../sw/logica.ts";

const SW = "sw.js";
const LICENCIAS = "licencias-de-terceros.txt";

function sha256(contenido: Uint8Array | string): string {
  return createHash("sha256").update(contenido).digest("hex");
}

/** Los ficheros de una carpeta y sus subcarpetas: rutas relativas con "/", ordenadas. */
export function listarFicheros(carpeta: string, prefijo = ""): string[] {
  const rutas: string[] = [];
  for (const entrada of readdirSync(join(carpeta, prefijo), { withFileTypes: true })) {
    const ruta = prefijo === "" ? entrada.name : `${prefijo}/${entrada.name}`;
    if (entrada.isDirectory()) rutas.push(...listarFicheros(carpeta, ruta));
    else rutas.push(ruta);
  }
  return rutas.sort();
}

/**
 * La lista de ficheros de una versión con sus huellas. El identificador de la
 * versión es la huella de la lista: cambia si cambia, aparece o desaparece
 * cualquier fichero.
 */
export function crearPrecarga(carpeta: string, excluidos: readonly string[] = [SW]): Precarga {
  const ficheros = listarFicheros(carpeta)
    .filter((ruta) => !excluidos.includes(ruta))
    .map((ruta) => ({ ruta, sha256: sha256(readFileSync(join(carpeta, ruta))) }));
  return { version: sha256(JSON.stringify(ficheros)).slice(0, 16), ficheros };
}

/**
 * Los datos que se publican tienen que ser, byte a byte, los que describe el
 * manifiesto: ni uno de más, ni uno de menos, ni uno con otra huella.
 */
export function comprobarDatos(carpeta: string, precarga: Precarga): void {
  const manifiesto = JSON.parse(readFileSync(join(carpeta, "datos", "manifiesto.json"), "utf8")) as {
    ficheros: Record<string, { sha256: string }>;
  };
  const publicados = new Map(
    precarga.ficheros
      .filter((f) => f.ruta.startsWith("datos/") && f.ruta !== "datos/manifiesto.json")
      .map((f) => [f.ruta.slice("datos/".length), f.sha256]),
  );
  for (const [ruta, { sha256: esperada }] of Object.entries(manifiesto.ficheros)) {
    const publicada = publicados.get(ruta);
    if (publicada === undefined) throw new Error(`Falta el fichero de datos ${ruta}`);
    if (publicada !== esperada) throw new Error(`${ruta} no coincide con la huella del manifiesto`);
    publicados.delete(ruta);
  }
  if (publicados.size > 0) {
    throw new Error(`Ficheros de datos que no están en el manifiesto: ${[...publicados.keys()].join(", ")}`);
  }
}

/** Carpeta del paquete de `node_modules` al que pertenece un módulo, o `null` si es código propio. */
export function paqueteDe(idModulo: string): string | null {
  const id = idModulo.replaceAll("\\", "/");
  const corte = id.lastIndexOf("/node_modules/");
  if (corte < 0) return null;
  const partes = id.slice(corte + "/node_modules/".length).split("/");
  const nombre = partes[0]?.startsWith("@") === true ? `${partes[0]}/${partes[1] ?? ""}` : (partes[0] ?? "");
  return `${id.slice(0, corte)}/node_modules/${nombre}`;
}

/** Texto con la licencia de cada librería empaquetada en el JavaScript publicado. */
export function licenciasDeTerceros(carpetas: readonly string[]): string {
  const bloques = [...new Set(carpetas)].sort().map((carpeta) => {
    const paquete = JSON.parse(readFileSync(join(carpeta, "package.json"), "utf8")) as {
      name: string; version: string; license?: string;
    };
    const fichero = readdirSync(carpeta).find((f) => /^licen[cs]e(\.md|\.txt)?$/i.test(f));
    if (fichero === undefined) throw new Error(`${paquete.name} no trae fichero de licencia`);
    const texto = readFileSync(join(carpeta, fichero), "utf8").replaceAll("\r\n", "\n").trim();
    return `${paquete.name} ${paquete.version} (${paquete.license ?? "licencia en el texto"})\n\n${texto}\n`;
  });
  return [
    "Mus Analytics incluye en su código publicado estas librerías de terceros,",
    "cada una con su propia licencia. El código de Mus Analytics es AGPL-3.0:",
    "https://github.com/Alonsodelaconcha/mus-analytics",
    "",
    ...bloques.map((b) => `${"-".repeat(72)}\n${b}`),
  ].join("\n");
}

/**
 * Commit del que se construye la web, abreviado, con un "+" detrás si en su
 * carpeta hay cambios sin confirmar (lo construido no sería entonces lo de ese
 * commit). `null` si no hay git, como en una copia sin historial.
 *
 * Va en el pie de la web junto a la huella de lo guardado: los dos códigos se
 * parecen, y con su nombre al lado no se confunden.
 */
export function commitDe(
  carpeta: string,
  git: (argumentos: string[]) => string = (argumentos) =>
    execFileSync("git", argumentos, { cwd: carpeta, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }),
): string | null {
  try {
    const commit = git(["rev-parse", "--short=7", "HEAD"]).trim();
    if (!/^[0-9a-f]{7,40}$/.test(commit)) return null;
    const conCambios = git(["status", "--porcelain", "--", "."]).trim() !== "";
    return conCambios ? `${commit}+` : commit;
  } catch {
    return null;
  }
}

export function sinConexion(): Plugin {
  const emergencia = process.env.MUS_SW === "emergencia";
  const carpetaWeb = resolve(import.meta.dirname, "..");
  const paquete = JSON.parse(readFileSync(resolve(carpetaWeb, "package.json"), "utf8")) as {
    version: string;
  };
  let config: ResolvedConfig;
  return {
    name: "mus-sin-conexion",
    config(_, { command }) {
      return {
        define: {
          __VERSION_WEB__: JSON.stringify(process.env.MUS_VERSION ?? paquete.version),
          // En desarrollo y en los tests no se enseña ningún commit.
          __COMMIT__: JSON.stringify(command === "build" ? commitDe(carpetaWeb) : null),
          // En desarrollo y en los tests no hay service worker.
          __MODO_SW__: JSON.stringify(command !== "build" ? "ninguno" : emergencia ? "emergencia" : "normal"),
        },
      };
    },
    configResolved(resuelta) {
      config = resuelta;
    },
    generateBundle(_, bundle) {
      const carpetas: string[] = [];
      for (const trozo of Object.values(bundle)) {
        if (trozo.type !== "chunk") continue;
        for (const id of trozo.moduleIds) {
          const carpeta = paqueteDe(id);
          if (carpeta !== null && existsSync(join(carpeta, "package.json"))) carpetas.push(carpeta);
        }
      }
      this.emitFile({ type: "asset", fileName: LICENCIAS, source: licenciasDeTerceros(carpetas) });
    },
    async closeBundle() {
      if (config.command !== "build") return;
      const salida = resolve(config.root, config.build.outDir);
      const precarga = crearPrecarga(salida);
      comprobarDatos(salida, precarga);
      // El service worker se construye aparte, como un único fichero con nombre fijo.
      await build({
        configFile: false,
        root: config.root,
        logLevel: "warn",
        publicDir: false,
        define: { __PRECARGA__: JSON.stringify(precarga) },
        build: {
          outDir: salida,
          emptyOutDir: false,
          minify: false,
          lib: {
            entry: resolve(config.root, "sw", emergencia ? "emergencia.ts" : "sw.ts"),
            formats: ["iife"],
            name: "sw",
            fileName: () => SW,
          },
        },
      });
      config.logger.info(
        emergencia
          ? `\n${SW}: SERVICE WORKER DE EMERGENCIA (borra las cachés y se desregistra)`
          : `\n${SW}: versión ${precarga.version}, ${String(precarga.ficheros.length)} ficheros guardados para usar sin conexión`,
      );
    },
  };
}
