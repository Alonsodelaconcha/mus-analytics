// Comprueba la web ya publicada (por defecto, la de GitHub Pages), con Edge sin
// ventana (scripts/edge.mjs). Para después de cada publicación:
//
//   npm run comprobar-publicada
//   npm run comprobar-publicada -- --version 0.1.1      # exige esa versión
//   npm run comprobar-publicada -- --url https://otra.direccion/
//
// Y para comprobar el paso de una versión a la siguiente, en un navegador que
// conserva lo guardado entre las dos ejecuciones:
//
//   npm run comprobar-publicada -- --actualizacion antes     # ANTES de publicar
//   npm run comprobar-publicada -- --actualizacion despues   # DESPUÉS de publicar
//
// 1. Ficheros: lee la lista de `sw.js` y descarga todos; cada uno tiene que
//    coincidir con su huella, y los datos ser, byte a byte, los de public/datos.
// 2. Primera visita en un navegador limpio: se guarda entera, sin errores.
// 3. Modo avión: el navegador se vuelve a abrir sin red (no resuelve ningún
//    nombre) y la web tiene que abrir y funcionar entera.
//
// Con --actualizacion despues: el navegador abre con la versión que tenía, avisa
// de la nueva sin tocar la mano a medias y, al pulsar «Actualizar», pasa a ella.
//
// Sale con código 1 si algo falla.

import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseArgs } from "node:util";

import { AYUDAS, ESTADO_PAGINA, MANO_ENTERA, abrirEdge, espera } from "./edge.mjs";

const { values: opciones } = parseArgs({
  options: {
    url: { type: "string", default: "https://alonsodelaconcha.github.io/mus-analytics/" },
    version: { type: "string" },
    actualizacion: { type: "string" }, // antes o despues
  },
});
const WEB = opciones.url.endsWith("/") ? opciones.url : `${opciones.url}/`;
const PUERTO = 9336;

let pasos = 0;
function afirmar(condicion, mensaje, detalle = "") {
  if (!condicion) throw new Error(`${mensaje}${detalle === "" ? "" : `\n    ${detalle}`}`);
  pasos++;
  console.log(`  ✓ ${mensaje}`);
}

const sha256 = (contenido) => createHash("sha256").update(contenido).digest("hex");

async function descargar(ruta) {
  const respuesta = await fetch(new URL(ruta, WEB), { cache: "no-store" });
  if (!respuesta.ok) throw new Error(`${ruta}: error ${String(respuesta.status)}`);
  return { contenido: Buffer.from(await respuesta.arrayBuffer()), cabeceras: respuesta.headers };
}

async function hasta(edge, condicion, que, segundos = 60) {
  let ultimo = null;
  for (let i = 0; i < segundos * 5; i++) {
    ultimo = await edge.evaluar(ESTADO_PAGINA).catch(() => null);
    if (ultimo !== null && condicion(ultimo)) return ultimo;
    await espera(200);
  }
  const resumen = ultimo === null ? "la página no responde" : JSON.stringify({ ...ultimo, texto: ultimo.texto.slice(-300) });
  throw new Error(`tiempo agotado esperando ${que}\n    ${resumen}`);
}

const lista = (e) => e.texto.includes("Lista para usar sin conexión");

/** Dónde se apunta, entre las dos ejecuciones, qué versión tenía guardada el navegador. */
const NOTA = join(tmpdir(), "mus-analytics-actualizacion.json");

async function actualizacion(paso) {
  if (paso !== "antes" && paso !== "despues") throw new Error("--actualizacion es «antes» o «despues»");
  const edge = await abrirEdge({ nombre: "actualizacion", puerto: PUERTO });
  try {
    await edge.cdp("Emulation.setDeviceMetricsOverride", { width: 393, height: 852, deviceScaleFactor: 1, mobile: true });
    if (paso === "antes") {
      console.log(`\nAntes de publicar: un navegador guarda la versión que hay ahora en ${WEB}`);
      await edge.cdp("Network.clearBrowserCache");
      await edge.cdp("Storage.clearDataForOrigin", { origin: new URL(WEB).origin, storageTypes: "all" });
      await edge.cdp("Page.navigate", { url: WEB });
      const e = await hasta(edge, lista, "«Lista para usar sin conexión»", 120);
      writeFileSync(NOTA, JSON.stringify({ version: e.version, id: e.id }));
      afirmar(e.controlada && e.id !== null, `guardada la versión ${String(e.version)} (${String(e.id)})`);
      console.log("    Publica la versión nueva y ejecuta: npm run comprobar-publicada -- --actualizacion despues");
      return;
    }
    const anterior = JSON.parse(readFileSync(NOTA, "utf8"));
    console.log(`\nDespués de publicar: el navegador que tenía la ${anterior.version} (${anterior.id}) abre ${WEB}`);
    await edge.cdp("Page.navigate", { url: WEB });
    let e = await hasta(edge, (x) => x.version !== null, "la web");
    afirmar(e.version === anterior.version && e.id === anterior.id && e.controlada,
      "abre con la versión que tenía guardada, servida por el service worker", `${String(e.version)} (${String(e.id)})`);
    await edge.evaluar(`${AYUDAS} await cargada(); await cartas("R C 5 4"); await posicion("Mano"); await calculada();`);
    const inicio = Date.now();
    await hasta(edge, (x) => x.texto.includes("Hay una versión nueva. Al actualizar"), "el aviso de versión nueva", 120);
    const segundos = Math.round((Date.now() - inicio) / 1000);
    // Se espera un rato: la versión nueva no puede tomar el mando por su cuenta.
    await espera(3000);
    e = await edge.evaluar(ESTADO_PAGINA);
    afirmar(e.esperando && e.texto.includes("Hay una versión nueva. Al actualizar"), `avisa de la versión nueva (a los ${String(segundos)} s de meter la mano) y espera`);
    afirmar(e.version === anterior.version && e.texto.includes("29 al punto") && e.texto.includes("Quédate con"),
      "la página sigue en la versión anterior, con la mano a medias tal como estaba");
    const pulsado = await edge.evaluar(`
      const boton = [...document.querySelectorAll("button")].find((b) => b.innerText.trim() === "Actualizar");
      boton?.click();
      return boton !== undefined;`);
    afirmar(pulsado, "se pulsa «Actualizar»");
    e = await hasta(edge, (x) => x.id !== null && x.id !== anterior.id && lista(x) && Object.keys(x.guardado).length === 1, "la versión nueva");
    afirmar(e.controlada && !e.texto.includes("Hay una versión nueva"), `ahora es la versión ${String(e.version)} (${String(e.id)}), con una sola caché y sin aviso`);
    if (opciones.version !== undefined) {
      afirmar(e.version === opciones.version, `es la versión ${opciones.version}`, `la publicada es la ${String(e.version)}`);
    }
  } finally {
    await edge.cerrar();
  }
}

let fallo = null;
try {
  if (opciones.actualizacion !== undefined) {
    await actualizacion(opciones.actualizacion);
  } else {
    console.log(`\n1. Ficheros publicados en ${WEB}`);
    const sw = await descargar("sw.js");
    const texto = sw.contenido.toString("utf8");
    const version = /"version":\s*"([0-9a-f]{16})"/.exec(texto)?.[1];
    const ficheros = [...texto.matchAll(/"ruta":\s*"([^"]+)",\s*"sha256":\s*"([0-9a-f]{64})"/g)]
      .map(([, ruta, huella]) => ({ ruta, huella }));
    afirmar(version !== undefined && ficheros.length > 0, `sw.js está en su dirección fija: versión ${String(version)}, ${String(ficheros.length)} ficheros`);
    afirmar((sw.cabeceras.get("content-type") ?? "").includes("javascript"), `sw.js se sirve como JavaScript (caché HTTP: ${sw.cabeceras.get("cache-control") ?? "sin cabecera"})`);

    const descargados = await Promise.all(ficheros.map(async (f) => ({ ...f, ...(await descargar(f.ruta)) })));
    const distintos = descargados.filter((f) => sha256(f.contenido) !== f.huella).map((f) => f.ruta);
    afirmar(distintos.length === 0, `los ${String(ficheros.length)} ficheros coinciden con la huella de la lista`, distintos.join(", "));

    const datos = descargados.filter((f) => f.ruta.startsWith("datos/"));
    const locales = datos.filter((f) => !f.contenido.equals(readFileSync(join("public", f.ruta)))).map((f) => f.ruta);
    afirmar(datos.length === 21 && locales.length === 0, "los 21 ficheros de datos son, byte a byte, los del repositorio (public/datos)", locales.join(", "));
    const kb = (lista_) => Math.round(lista_.reduce((n, f) => n + f.contenido.length, 0) / 1024);
    console.log(`    (${String(kb(descargados))} KB en total; ${String(kb(datos))} KB de datos)`);

    console.log("\n2. Primera visita en un navegador limpio");
    let edge = await abrirEdge({ nombre: "publicada", puerto: PUERTO });
    let e;
    try {
      await edge.cdp("Emulation.setDeviceMetricsOverride", { width: 393, height: 852, deviceScaleFactor: 1, mobile: true });
      await edge.cdp("Network.clearBrowserCache");
      await edge.cdp("Storage.clearDataForOrigin", { origin: new URL(WEB).origin, storageTypes: "all" });
      edge.errores.length = 0;
      await edge.cdp("Page.navigate", { url: WEB });
      e = await hasta(edge, lista, "«Lista para usar sin conexión»", 120);
      afirmar(await edge.evaluar("return window.isSecureContext;"), "contexto seguro (HTTPS)");
      afirmar(e.controlada && e.registros === 1, "el service worker está registrado y sirve la página");
      const nombres = Object.keys(e.guardado);
      afirmar(nombres.length === 1 && nombres[0] === `mus-analytics-${String(version)}` && e.guardado[nombres[0]] === ficheros.length,
        `una caché, la de esta versión, con sus ${String(ficheros.length)} ficheros`, JSON.stringify(e.guardado));
      afirmar(e.id === String(version).slice(0, 7), `el pie dice: Versión ${String(e.version)} (${String(e.id)})`);
      if (opciones.version !== undefined) {
        afirmar(e.version === opciones.version, `es la versión ${opciones.version}`, `la publicada es la ${String(e.version)}`);
      }
      afirmar(edge.errores.length === 0, "sin errores en la consola", edge.errores.join(" | "));
    } finally {
      await edge.cerrar();
    }

    console.log("\n3. Modo avión: el mismo navegador, abierto sin red");
    edge = await abrirEdge({ nombre: "publicada", puerto: PUERTO, argumentos: ["--host-resolver-rules=MAP * ~NOTFOUND"] });
    try {
      await edge.cdp("Emulation.setDeviceMetricsOverride", { width: 393, height: 852, deviceScaleFactor: 1, mobile: true });
      await edge.cdp("Page.navigate", { url: WEB });
      const sinRed = await hasta(edge, lista, "la web sin red", 30);
      const fuera = await edge.evaluar(`
        const pedir = (url) => fetch(url, { mode: "no-cors", cache: "no-store" }).then(() => "llega", () => "no llega");
        return [await pedir("https://github.com/"), await pedir("sw.js?comprobacion")];`);
      afirmar(fuera.every((x) => x === "no llega"), "no hay red de verdad: ni otra web ni un fichero sin guardar responden", fuera.join(", "));
      afirmar(sinRed.version === e.version && sinRed.controlada, `la web abre sin red, en la misma versión (${String(sinRed.version)})`);
      const r = await edge.evaluar(MANO_ENTERA);
      afirmar(r.decidir && r.cortado && r.mus && !r.errores, "una mano entera en las tres pestañas, sin errores", JSON.stringify(r));
      afirmar(r.datos === r.total && r.total > 0, `los ${String(r.total)} ficheros de datos están disponibles sin red`);
    } finally {
      await edge.cerrar();
    }
  }
  console.log(`\n${String(pasos)} comprobaciones correctas.`);
} catch (error) {
  fallo = error;
  console.error(`  ✗ ${error.message}`);
}
process.exitCode = fallo === null ? 0 : 1;
