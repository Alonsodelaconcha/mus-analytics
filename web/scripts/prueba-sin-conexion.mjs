// Prueba del modo sin conexión en un navegador de verdad (Edge sin ventana,
// scripts/edge.mjs), con un servidor propio que se puede apagar y hacer fallar.
//
//   npm run prueba-sin-conexion
//
// Construye tres versiones de la web (dos normales y la de emergencia) en
// node_modules/.tmp y las sirve en http://127.0.0.1:4190/mus-analytics/, con la
// misma ruta y la misma caché HTTP de 10 minutos que GitHub Pages. Comprueba:
//
//   1. Primera visita: se guarda la web entera.
//   2. Modo avión (servidor apagado): la web abre y funciona entera.
//   3. Versión nueva cuya descarga falla a medias (corte, contenido cambiado,
//      error 500): no se instala y la anterior sigue entera, también sin red.
//   4. Versión nueva correcta: avisa sin tocar la mano a medias; al pulsar
//      «Actualizar» se pasa a la nueva y se borra la caché anterior.
//   5. Una versión nueva que estaba esperando se aplica sola al abrir la web.
//   6. Salida de emergencia: el service worker de emergencia borra las cachés
//      y se desregistra; la web sigue funcionando desde la red.
//   7. Tras la emergencia, una versión normal vuelve a guardarse.
//
// Sale con código 1 si algo falla.

import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import http from "node:http";
import { extname, join, resolve } from "node:path";

import { AYUDAS, abrirEdge, espera } from "./edge.mjs";

const PUERTO = 4190;
const RUTA = "/mus-analytics/";
const ORIGEN = `http://127.0.0.1:${String(PUERTO)}`;
const WEB = `${ORIGEN}${RUTA}`;
const TMP = resolve("node_modules/.tmp/prueba-sin-conexion");
const VERSIONES = {
  uno: { version: "1.0.0-uno" },
  dos: { version: "2.0.0-dos" },
  emergencia: { version: "9.9.9-emergencia", emergencia: true },
};

// --- Las tres versiones -------------------------------------------------------------------

function contarFicheros(carpeta) {
  return readdirSync(carpeta, { withFileTypes: true })
    .reduce((n, e) => n + (e.isDirectory() ? contarFicheros(join(carpeta, e.name)) : 1), 0);
}

for (const [nombre, v] of Object.entries(VERSIONES)) {
  v.carpeta = join(TMP, nombre);
  const r = spawnSync(process.execPath, [
    "scripts/construir.mjs", "--version", v.version, "--salida", v.carpeta, ...(v.emergencia ? ["--emergencia"] : []),
  ], { stdio: ["ignore", "ignore", "inherit"] });
  if (r.status !== 0) throw new Error(`No se ha podido construir la versión «${nombre}»`);
  v.guardados = contarFicheros(v.carpeta) - 1; // todos menos sw.js
  console.log(`· versión «${nombre}» (${v.version}): ${String(v.guardados)} ficheros`);
}

// --- Servidor: como GitHub Pages, pero se puede apagar y hacer fallar ------------------------

const TIPOS = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".png": "image/png", ".txt": "text/plain; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
};
const FALLOS = {
  /** La conexión se corta con medio fichero enviado. */
  corte: (res, contenido, cabeceras) => {
    res.writeHead(200, { ...cabeceras, "content-length": contenido.length });
    res.write(contenido.subarray(0, contenido.length >> 1));
    setTimeout(() => { res.destroy(); }, 50);
  },
  /** Llega entero, pero no es el fichero de esta versión. */
  cambiado: (res, contenido, cabeceras) => {
    const otro = Buffer.from(contenido);
    otro[otro.length >> 1] ^= 1;
    res.writeHead(200, { ...cabeceras, "content-length": otro.length }).end(otro);
  },
  "error 500": (res) => {
    res.writeHead(500).end("error del servidor");
  },
};
const servidor = { carpeta: null, fallo: null, servidas: [], http: null };

function atender(req, res) {
  const { pathname } = new URL(req.url, ORIGEN);
  const ruta = pathname.startsWith(RUTA) ? pathname.slice(RUTA.length) || "index.html" : null;
  const fichero = ruta === null ? null : join(servidor.carpeta, ruta);
  if (fichero === null || !fichero.startsWith(servidor.carpeta) || !existsSync(fichero) || !statSync(fichero).isFile()) {
    res.writeHead(404).end("no existe");
    return;
  }
  const contenido = readFileSync(fichero);
  const cabeceras = { "content-type": TIPOS[extname(fichero)] ?? "application/octet-stream", "cache-control": "max-age=600" };
  if (servidor.fallo?.ruta === ruta) {
    // Un poco tarde, para que el resto de la versión ya se haya descargado: falla «a mitad».
    servidor.fallo.veces++;
    setTimeout(() => { FALLOS[servidor.fallo.tipo](res, contenido, cabeceras); }, 400);
    return;
  }
  servidor.servidas.push(ruta);
  res.writeHead(200, { ...cabeceras, "content-length": contenido.length }).end(contenido);
}

async function encender(nombre, fallo = null) {
  await apagar();
  servidor.carpeta = VERSIONES[nombre].carpeta;
  servidor.fallo = fallo === null ? null : { ...fallo, veces: 0 };
  servidor.servidas = [];
  servidor.http = http.createServer(atender);
  await new Promise((ok, ko) => { servidor.http.once("error", ko).listen(PUERTO, "127.0.0.1", ok); });
}

async function apagar() {
  if (servidor.http === null) return;
  const cerrado = new Promise((ok) => { servidor.http.close(ok); });
  servidor.http.closeAllConnections();
  await cerrado;
  servidor.http = null;
}

// --- Lo que se mira en la página ------------------------------------------------------------

const edge = await abrirEdge({ nombre: "prueba", puerto: 9335 });
let pasos = 0;

function bien(mensaje) {
  pasos++;
  console.log(`  ✓ ${mensaje}`);
}

function afirmar(condicion, mensaje, detalle = "") {
  if (!condicion) throw new Error(`${mensaje}${detalle === "" ? "" : `\n    ${detalle}`}`);
  bien(mensaje);
}

/** Estado de la página; `null` mientras se está recargando. */
async function mirar() {
  try {
    return await edge.evaluar(`
      const registros = await navigator.serviceWorker.getRegistrations();
      const guardado = {};
      for (const n of await caches.keys()) guardado[n] = (await (await caches.open(n)).keys()).length;
      const texto = document.body?.innerText ?? "";
      return {
        texto,
        version: /Versión (\\S+)/.exec(texto)?.[1] ?? null,
        id: /Versión \\S+ \\(([0-9a-f]{7})\\)/.exec(texto)?.[1] ?? null,
        controlada: navigator.serviceWorker.controller !== null,
        registros: registros.length,
        esperando: registros.some((r) => r.waiting !== null),
        guardado,
      };`);
  } catch {
    return null;
  }
}

async function hasta(condicion, que, segundos = 30) {
  let ultimo = null;
  for (let i = 0; i < segundos * 5; i++) {
    ultimo = await mirar();
    if (ultimo !== null && condicion(ultimo)) return ultimo;
    await espera(200);
  }
  const resumen = ultimo === null ? "la página no responde" : JSON.stringify({ ...ultimo, texto: ultimo.texto.slice(-300) });
  throw new Error(`tiempo agotado esperando ${que}\n    ${resumen}`);
}

const lista = (e) => e.texto.includes("Lista para usar sin conexión");
/** Una sola caché, la de la versión que enseña la página, con todos sus ficheros. */
function afirmarGuardada(e, nombre) {
  const v = VERSIONES[nombre];
  const nombres = Object.keys(e.guardado);
  afirmar(e.version === v.version && e.controlada, `la página es la versión «${nombre}» (${v.version}) y la sirve el service worker`,
    `versión ${String(e.version)}, controlada: ${String(e.controlada)}`);
  afirmar(nombres.length === 1 && e.id !== null && nombres[0].startsWith(`mus-analytics-${e.id}`) && e.guardado[nombres[0]] === v.guardados,
  `hay una sola caché, la suya, con sus ${String(v.guardados)} ficheros`, JSON.stringify(e.guardado));
}

/** Una mano entera en las tres pestañas y todos los ficheros de datos, uno por uno. */
async function usarLaWeb() {
  const r = await edge.evaluar(`
    ${AYUDAS}
    await cargada();
    await cartas("R C 5 4"); await posicion("Mano"); await calculada();
    const decidir = document.body.innerText;
    await pestana("Se ha cortado"); await toca("Dos reyes"); await calculada();
    const cortado = document.body.innerText;
    await pestana("Ha habido mus"); await cartas("R R C S"); await calculada();
    const mus = document.body.innerText;
    const manifiesto = await (await fetch("datos/manifiesto.json")).json();
    const rutas = Object.keys(manifiesto.ficheros);
    const estados = await Promise.all(rutas.map((r) => fetch("datos/" + r).then((x) => x.status, () => 0)));
    return {
      decidir: /Quédate con/.test(decidir), cortado: /ganáis/.test(cortado), mus: /Tras el mus/.test(mus),
      errores: /No se (ha|han) podido cargar/.test(decidir + cortado + mus),
      datos: estados.filter((s) => s === 200).length, total: rutas.length,
    };`);
  afirmar(r.decidir && r.cortado && r.mus && !r.errores, "una mano entera en las tres pestañas, sin errores", JSON.stringify(r));
  afirmar(r.datos === r.total && r.total > 0, `los ${String(r.total)} ficheros de datos están disponibles`);
}

/** Pide al navegador que busque una versión nueva y devuelve cómo acaba su instalación. */
function buscarVersion() {
  return edge.evaluar(`
    const registro = await navigator.serviceWorker.getRegistration();
    // El navegador también busca versiones por su cuenta al abrir la página: puede haberse adelantado.
    if (registro.waiting !== null) return "installed";
    const seguir = (nuevo) => new Promise((resolver) => {
      const comprobar = () => {
        if (nuevo.state === "installed" || nuevo.state === "redundant") resolver(nuevo.state);
      };
      nuevo.addEventListener("statechange", comprobar);
      comprobar();
    });
    const fin = registro.installing !== null
      ? seguir(registro.installing)
      : new Promise((resolver) => {
        registro.addEventListener("updatefound", () => { resolver(seguir(registro.installing)); }, { once: true });
        registro.update().catch(() => undefined);
      });
    return await Promise.race([fin, new Promise((r) => setTimeout(() => r("no ha encontrado ninguna versión nueva"), 30000))]);`);
}

const recargar = () => edge.cdp("Page.reload");

// --- La prueba ----------------------------------------------------------------------------

let fallo = null;
try {
  await edge.cdp("Emulation.setDeviceMetricsOverride", { width: 393, height: 852, deviceScaleFactor: 1, mobile: true });
  await edge.cdp("Network.clearBrowserCache");
  await edge.cdp("Storage.clearDataForOrigin", { origin: ORIGEN, storageTypes: "all" });

  console.log("\n1. Primera visita");
  await encender("uno");
  await edge.cdp("Page.navigate", { url: WEB });
  let e = await hasta(lista, "«Lista para usar sin conexión»", 60);
  afirmarGuardada(e, "uno");
  afirmar(servidor.servidas.includes("sw.js"), "sw.js se ha pedido en su dirección fija");

  console.log("\n2. Modo avión: servidor apagado");
  await apagar();
  await recargar();
  e = await hasta(lista, "la web sin conexión");
  afirmarGuardada(e, "uno");
  await usarLaWeb();

  for (const tipo of Object.keys(FALLOS)) {
    console.log(`\n3. Versión nueva, pero un fichero de datos falla a mitad de la descarga (${tipo})`);
    await encender("dos", { ruta: "datos/mesa-normal.json", tipo });
    const final = await buscarVersion();
    afirmar(servidor.fallo.veces > 0 && servidor.servidas.length >= VERSIONES.dos.guardados - 1,
      `el fallo llegó con el resto de la versión ya descargado (${String(servidor.servidas.length)} ficheros servidos)`);
    afirmar(final === "redundant", "la versión nueva no se ha instalado", `estado final: ${String(final)}`);
    e = await mirar();
    afirmar(!e.esperando && !e.texto.includes("Hay una versión nueva"), "no hay ninguna versión esperando ni aviso en la página");
    afirmarGuardada(e, "uno");
    await apagar();
    await recargar();
    e = await hasta(lista, "la versión anterior sin conexión");
    afirmarGuardada(e, "uno");
    await usarLaWeb();
  }

  console.log("\n4. Versión nueva correcta, con una mano a medias");
  await recargar();
  await edge.evaluar(`${AYUDAS} await cargada(); await cartas("R C 5 4"); await posicion("Mano"); await calculada();`);
  await encender("dos");
  afirmar(await buscarVersion() === "installed", "la versión nueva se ha descargado entera");
  await hasta((x) => x.texto.includes("Hay una versión nueva. Al actualizar"), "el aviso de versión nueva");
  // Se espera un rato: la versión nueva no puede tomar el mando por su cuenta ni recargar la página.
  await espera(3000);
  e = await mirar();
  afirmar(e.esperando && e.texto.includes("Hay una versión nueva. Al actualizar"), "la versión nueva espera y la página lo avisa");
  afirmar(e.version === VERSIONES.uno.version && e.texto.includes("29 al punto") && e.texto.includes("Quédate con"),
    "la página sigue en la versión anterior, con la mano y su recomendación tal como estaban");
  afirmar(Object.keys(e.guardado).length === 2 && Object.values(e.guardado).includes(VERSIONES.dos.guardados),
    "las dos versiones están guardadas enteras, cada una en su caché", JSON.stringify(e.guardado));
  const pulsado = await edge.evaluar(`
    const boton = [...document.querySelectorAll("button")].find((b) => b.innerText.trim() === "Actualizar");
    boton?.click();
    return boton !== undefined;`);
  afirmar(pulsado, "se pulsa «Actualizar»");
  e = await hasta((x) => x.version === VERSIONES.dos.version && lista(x) && Object.keys(x.guardado).length === 1, "la versión nueva tras «Actualizar»");
  afirmarGuardada(e, "dos");
  afirmar(!e.texto.includes("Hay una versión nueva"), "el aviso ha desaparecido");
  await apagar();
  await recargar();
  e = await hasta(lista, "la versión nueva sin conexión");
  afirmarGuardada(e, "dos");
  await usarLaWeb();

  console.log("\n5. Una versión que estaba esperando se aplica sola al abrir la web");
  await encender("uno");
  await recargar();
  await hasta((x) => x.version !== null, "la web");
  afirmar(await buscarVersion() === "installed", "otra versión descargada entera y esperando");
  await edge.cdp("Page.navigate", { url: WEB });
  e = await hasta((x) => x.version === VERSIONES.uno.version && lista(x) && Object.keys(x.guardado).length === 1, "el paso a la versión que esperaba");
  afirmarGuardada(e, "uno");

  console.log("\n6. Salida de emergencia");
  await encender("emergencia");
  await recargar();
  e = await hasta((x) => x.registros === 0 && Object.keys(x.guardado).length === 0 && x.version === VERSIONES.emergencia.version,
    "que el service worker de emergencia limpie el móvil");
  afirmar(true, "sin service worker registrado y sin cachés; la página es la publicada, servida por la red");
  afirmar(e.texto.includes("Aquí no se puede usar sin conexión"), "la web lo dice: «Aquí no se puede usar sin conexión»");
  await usarLaWeb();
  await recargar();
  await espera(2000);
  e = await hasta((x) => x.version !== null, "la web tras recargar");
  afirmar(e.registros === 0 && Object.keys(e.guardado).length === 0 && !e.controlada, "al recargar sigue limpio: no se vuelve a registrar");

  console.log("\n7. Tras la emergencia, una versión normal vuelve a guardarse");
  await encender("dos");
  await recargar();
  e = await hasta((x) => x.version === VERSIONES.dos.version && lista(x), "la versión normal", 60);
  afirmarGuardada(e, "dos");
  await apagar();
  await recargar();
  e = await hasta(lista, "la web sin conexión");
  await usarLaWeb();

  console.log(`\n${String(pasos)} comprobaciones correctas.`);
} catch (error) {
  fallo = error;
  console.error(`  ✗ ${error.message}`);
} finally {
  await edge.cerrar();
  await apagar();
}
process.exitCode = fallo === null ? 0 : 1;
