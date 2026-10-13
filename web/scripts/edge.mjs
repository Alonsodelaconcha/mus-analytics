// Edge sin ventana, manejado por su protocolo de depuración (CDP). Lo comparten
// las capturas, los iconos y la prueba del modo sin conexión. Sin dependencias:
// Node (>= 22) trae `WebSocket` y `fetch`.

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const espera = (ms) => new Promise((r) => setTimeout(r, ms));

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

/**
 * Abre Edge con una pestaña en blanco y devuelve cómo hablarle:
 * - `cdp(metodo, parametros)`: una orden del protocolo;
 * - `evaluar(codigo)`: ejecuta en la página el cuerpo de una función asíncrona y devuelve su resultado;
 * - `errores`: los errores de consola de la página desde la última vez que se vació;
 * - `cerrar()`: cierre ordenado.
 *
 * El perfil es propio y siempre el mismo para cada `nombre`: no toca el del
 * usuario y no deja una carpeta nueva en cada ejecución (Edge tarda en soltar
 * sus ficheros y no se puede borrar al acabar).
 */
export async function abrirEdge({ nombre = "capturas", puerto = 9333, argumentos = [] } = {}) {
  const perfil = join(tmpdir(), `mus-analytics-${nombre}-edge`);
  const navegador = spawn(buscarEdge(), [
    "--headless=new", `--remote-debugging-port=${String(puerto)}`, "--no-first-run",
    "--no-default-browser-check", "--disable-extensions", `--user-data-dir=${perfil}`, ...argumentos, "about:blank",
  ], { stdio: "ignore" });

  let pestana;
  for (let i = 0; i < 50 && pestana === undefined; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${String(puerto)}/json/new?about:blank`, { method: "PUT" });
      if (r.ok) pestana = await r.json();
    } catch {
      // Edge aún está arrancando.
    }
    if (pestana === undefined) await espera(200);
  }
  if (pestana === undefined) {
    navegador.kill();
    throw new Error("Edge no responde");
  }

  const ws = new WebSocket(pestana.webSocketDebuggerUrl);
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
    } else if (m.method === "Log.entryAdded" && m.params.entry.level === "error") {
      errores.push(`${m.params.entry.text} ${m.params.entry.url ?? ""}`.trim());
    }
  });
  const cdp = (method, params = {}) => new Promise((ok, ko) => {
    const id = ++siguiente;
    pendientes.set(id, { ok, ko });
    ws.send(JSON.stringify({ id, method, params }));
  });

  await cdp("Page.enable");
  await cdp("Runtime.enable");
  await cdp("Log.enable");

  const evaluar = async (codigo) => {
    const r = await cdp("Runtime.evaluate", {
      expression: `(async () => { ${codigo} })()`, awaitPromise: true, returnByValue: true,
    });
    if (r.exceptionDetails) {
      throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text);
    }
    return r.result.value;
  };

  const cerrar = async () => {
    // Cierre ordenado: si se mata el proceso sin más, sus hijos siguen usando el perfil.
    const cerrado = new Promise((r) => { navegador.once("exit", r); });
    await Promise.race([cdp("Browser.close").catch(() => undefined), espera(2000)]);
    ws.close();
    await Promise.race([cerrado, espera(3000)]);
    navegador.kill();
  };

  return { cdp, evaluar, errores, cerrar };
}

const NOMBRE_CARTA = { R: "rey", C: "caballo", S: "sota", 7: "siete", 6: "seis", 5: "cinco", 4: "cuatro", A: "as" };

/**
 * Ayudas para manejar la web desde `evaluar`: `cartas("R C 5 4")`,
 * `posicion("Mano")`, `pestana("Se ha cortado")`, `toca("Dos reyes")`,
 * `hasta(() => condición, "qué se espera")` y `cargada()`.
 */
export const AYUDAS = `
  const espera = (ms) => new Promise((r) => setTimeout(r, ms));
  const hasta = async (f, que, intentos = 150) => {
    for (let i = 0; i < intentos; i++) { if (await f()) return; await espera(100); }
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
  const cargada = () => hasta(() => document.querySelector('[role="tab"]') && !/Cargando datos/.test(document.body.innerText), "los datos");
  const calculada = () => hasta(() => !/Calculando|Cargando/.test(document.body.innerText), "los cálculos");
`;

/**
 * Para `evaluar`: cómo está el modo sin conexión en la página. Devuelve la
 * versión que enseña el pie, si la sirve un service worker, cuántos hay
 * registrados, si alguno espera y cuántos ficheros tiene cada caché.
 */
export const ESTADO_PAGINA = `
  const registros = await navigator.serviceWorker.getRegistrations();
  const guardado = {};
  for (const n of await caches.keys()) guardado[n] = (await (await caches.open(n)).keys()).length;
  const texto = document.body?.innerText ?? "";
  return {
    texto,
    version: /Versión (\\S+)/.exec(texto)?.[1] ?? null,
    // La huella de lo guardado: «huella 60df1e6» (hasta la 0.1.1 iba entre paréntesis tras la versión).
    id: (/huella ([0-9a-f]{7})/.exec(texto) ?? /Versión \\S+ \\(([0-9a-f]{7})\\)/.exec(texto))?.[1] ?? null,
    commit: /commit ([0-9a-f]{7,40})/.exec(texto)?.[1] ?? null,
    controlada: navigator.serviceWorker.controller !== null,
    registros: registros.length,
    esperando: registros.some((r) => r.waiting !== null),
    guardado,
  };
`;

/**
 * Para `evaluar`: una mano entera en las tres pestañas y todos los ficheros de
 * datos, uno por uno. Devuelve qué ha salido bien.
 */
export const MANO_ENTERA = `
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
  };
`;
