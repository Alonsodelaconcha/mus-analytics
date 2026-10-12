import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { sinConexion } from "./plugins/sinConexion.ts";

export default defineConfig({
  // Rutas relativas: la web funciona igual en la raíz de un dominio que en
  // https://alonsodelaconcha.github.io/mus-analytics/.
  base: "./",
  plugins: [react(), sinConexion()],
  test: {
    include: ["test/**/*.test.{ts,tsx}"],
    environment: "node",
  },
});
