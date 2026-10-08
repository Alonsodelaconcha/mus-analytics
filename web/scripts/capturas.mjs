// Capturas de la web a tamaño de móvil, con Edge sin ventana manejado por su
// protocolo de depuración (CDP). Sin dependencias: solo Node (>= 22) y Edge.
//
// Uso (desde web/, con la web servida: npm run dev, npm run movil-final...):
//   npm run capturas                                    # escenas por defecto, http://localhost:5173/
//   npm run capturas -- --url http://192.168.1.37:4173/ # por la IP de red
//   npm run capturas -- --escenas mis-escenas.json --salida ../resultados/otra --tema oscuro
//
// Cada escena es { "nombre", "pasos", "tema"? }: "pasos" es código que se ejecuta en
// la página con las ayudas de AYUDAS (cartas("R C 5 4"), posicion("Mano"),
// pestana("Se ha cortado"), toca("Dos reyes")...). Además de las capturas,
// comprueba que la página no da errores en la consola y dice si es un contexto
// seguro (por la IP de red no lo es: sin crypto.subtle ni service worker).
// Sale con código 1 si algo falla.

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { parseArgs } from "node:util";

const { values: opciones } = parseArgs({
  options: {
    url: { type: "string", default: "http://localhost:5173/" },
    salida: { type: "string", default: "../resultados/capturas" },
    escenas: { type: "string" },
    tema: { type: "string", default: "claro" }, // claro, oscuro o ambos
    ancho: { type: "string", default: "390" },
    alto: { type: "string", default: "844" },
  },
});

/** Las tres pestañas con las manos de las maquetas, el detalle de un lance y el teclado a medio meter. */
const CORTADO = 'await cartas("R C 5 4"); await posicion("Mano"); await pestana("Se ha cortado"); await toca("Dos reyes");';
const ESCENAS_POR_DEFECTO = [
  { nombre: "1-mus-o-corto", pasos: 'await cartas("R C 5 4"); await posicion("Mano");' },
  { nombre: "2-se-ha-cortado", pasos: CORTADO },
  {
    nombre: "3-ha-habido-mus",
    pasos: 'await posicion("Postre"); await pestana("Ha habido mus"); await cartas("R R C S");',
  },
  { nombre: "4-detalle-de-un-lance", pasos: `${CORTADO} await toca("Grande");` },
  { nombre: "5-teclado", pasos: 'await posicion("Tercero"); await cartas("R 7");' },
];

const NOMBRE_CARTA = { R: "rey", C: "caballo", S: "sota", 7: "siete", 6: "seis", 5: "cinco", 4: "cuatro", A: "as" };

const AYUDAS = `
  const espera = (ms) => new Promise((r) => setTimeout(r, ms));
  const hasta = async (f, que) => {
    for (let i = 0; i < 150; i++) { if (f()) return; await espera(100); }
    throw new Error("tiempo agotado esperando " + que);
  };
  const texto = (b) => (b.getAttribute("aria-label") ?? b.innerText).trim();
  const toca = async (t) => {
    const b = [...document.querySelectorAll("button")].find((x) => texto(x) === t || x.innerText.trim().startsWith(t + "\\n"));
    if (!b) throw new Error("no hay botón " + t);
    b.click();
    await espera(120);
  };
  const cartas = async (mano) => {
    for (const c of mano.split(/\\s+/)) await toca("Añadir " + ${JSON.stringify(NOMBRE_CARTA)}[c]);
  };
  const posicion = (p) => toca(p);
  const pestana = async (p) => {
    const b = [...document.querySelectorAll('[role="tab"]')].find((x) => x.innerText.trim().startsWith(p));
    if (!b) throw new Error("no hay pestaña " + p);
    b.click();
    await espera(120);
  };
`;

function buscarEdge() {
  const candidatos = [
    process.env.EDGE,
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/microsoft-edge",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  ];
  const ruta = candidatos.find((c) => c !== undefined && existsSync(c));
  if (ruta === undefined) throw new Error("No encuentro Edge: indica su ruta en la variable EDGE.");
  return ruta;
}

const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const PUERTO = 9333;
const escenas = opciones.escenas ? JSON.parse(readFileSync(opciones.escenas, "utf8")) : ESCENAS_POR_DEFECTO;
const temas = opciones.tema === "ambos" ? ["claro", "oscuro"] : [opciones.tema];
const salida = resolve(opciones.salida);
mkdirSync(salida, { recursive: true });

// Perfil propio y siempre el mismo: no toca el del usuario, y no deja una carpeta
// nueva en cada ejecución (Edge tarda en soltar sus ficheros y no se puede borrar al acabar).
const perfil = join(tmpdir(), "mus-analytics-capturas-edge");
const navegador = spawn(buscarEdge(), [
  "--headless=new", `--remote-debugging-port=${String(PUERTO)}`, "--no-first-run",
  "--no-default-browser-check", "--disable-extensions", `--user-data-dir=${perfil}`, "about:blank",
], { stdio: "ignore" });

async function conectar() {
  for (let i = 0; i < 50; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${String(PUERTO)}/json/new?about:blank`, { method: "PUT" });
      if (r.ok) return await r.json();
    } catch {
      // Edge aún está arrancando.
    }
    await espera(200);
  }
  throw new Error("Edge no responde");
}

let fallos = 0;
const ws = new WebSocket((await conectar()).webSocketDebuggerUrl);
await new Promise((r) => { ws.addEventListener("open", r, { once: true }); });
let siguiente = 0;
const pendientes = new Map();
const errores = [];
ws.addEventListener("message", (e) => {
  const m = JSON.parse(e.data);
  if (m.id !== undefined && pendientes.has(m.id)) {
    const { ok, ko } = pendientes.get(m.id);
    pendientes.delete(m.id);
    if (m.error) ko(new Error(m.error.message)); else ok(m.result);
  } else if (m.method === "Runtime.exceptionThrown") {
    errores.push(m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text);
  } else if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") {
    errores.push(m.params.args.map((a) => a.value ?? a.description).join(" "));
  } else if (m.method === "Log.entryAdded" && m.params.entry.level === "error"
    // El navegador pide el icono por su cuenta; la web aún no lo tiene (llegará con la PWA).
    && !(m.params.entry.url ?? "").endsWith("/favicon.ico")) {
    errores.push(`${m.params.entry.text} ${m.params.entry.url ?? ""}`.trim());
  }
});
const cdp = (method, params = {}) => new Promise((ok, ko) => {
  const id = ++siguiente;
  pendientes.set(id, { ok, ko });
  ws.send(JSON.stringify({ id, method, params }));
});

try {
  await cdp("Page.enable");
  await cdp("Runtime.enable");
  await cdp("Log.enable");
  await cdp("Emulation.setDeviceMetricsOverride", {
    width: Number(opciones.ancho), height: Number(opciones.alto), deviceScaleFactor: 2, mobile: true,
  });
  for (const tema of temas) {
    await cdp("Emulation.setEmulatedMedia", {
      features: [{ name: "prefers-color-scheme", value: tema === "oscuro" ? "dark" : "light" }],
    });
    for (const escena of escenas) {
      const nombre = temas.length > 1 ? `${escena.nombre}-${tema}` : escena.nombre;
      errores.length = 0;
      await cdp("Page.navigate", { url: opciones.url });
      const r = await cdp("Runtime.evaluate", {
        expression: `(async () => {
          ${AYUDAS}
          try { localStorage.clear(); } catch {}
          await hasta(() => document.querySelector('[role="tab"]') && !/Cargando datos/.test(document.body.innerText), "los datos");
          ${escena.pasos ?? ""};
          await hasta(() => !/Calculando|Cargando/.test(document.body.innerText), "los cálculos");
          await espera(300);
          return { seguro: window.isSecureContext, subtle: typeof crypto !== "undefined" && crypto.subtle !== undefined };
        })()`,
        awaitPromise: true,
        returnByValue: true,
      });
      if (r.exceptionDetails) {
        fallos++;
        console.error(`✗ ${nombre}: ${r.exceptionDetails.exception?.description ?? r.exceptionDetails.text}`);
        continue;
      }
      const { data } = await cdp("Page.captureScreenshot", { format: "png" });
      writeFileSync(join(salida, `${nombre}.png`), Buffer.from(data, "base64"));
      const { seguro, subtle } = r.result.value;
      console.log(`✓ ${nombre}.png  (contexto ${seguro ? "seguro" : "NO seguro"}; crypto.subtle ${subtle ? "sí" : "no"})`);
      if (errores.length > 0) {
        fallos++;
        console.error(`  errores en la consola:\n  - ${errores.join("\n  - ")}`);
      }
    }
  }
  console.log(`\nCapturas en ${salida}`);
} finally {
  // Cierre ordenado: si se mata el proceso sin más, sus hijos siguen usando el perfil.
  const cerrado = new Promise((r) => { navegador.once("exit", r); });
  await Promise.race([cdp("Browser.close").catch(() => undefined), espera(2000)]);
  ws.close();
  await Promise.race([cerrado, espera(3000)]);
  navegador.kill();
}
process.exitCode = fallos > 0 ? 1 : 0;
