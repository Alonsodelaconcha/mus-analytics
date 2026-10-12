// Construye la web con las variantes que entiende plugins/sinConexion.ts, sin
// depender de cómo pone cada terminal las variables de entorno:
//
//   node scripts/construir.mjs --emergencia          # service worker de emergencia (npm run build:emergencia)
//   node scripts/construir.mjs --version 9.9.9 --salida node_modules/.tmp/otra   # para la prueba sin conexión

import { spawnSync } from "node:child_process";
import { parseArgs } from "node:util";

const { values: opciones } = parseArgs({
  options: {
    emergencia: { type: "boolean", default: false },
    version: { type: "string" },
    salida: { type: "string" },
  },
});

const resultado = spawnSync(
  process.execPath,
  ["node_modules/vite/bin/vite.js", "build", ...(opciones.salida ? ["--outDir", opciones.salida, "--emptyOutDir"] : [])],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      ...(opciones.emergencia ? { MUS_SW: "emergencia" } : {}),
      ...(opciones.version ? { MUS_VERSION: opciones.version } : {}),
    },
  },
);
process.exitCode = resultado.status ?? 1;
