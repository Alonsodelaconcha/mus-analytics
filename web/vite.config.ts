import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // Rutas relativas: la web funciona igual en la raíz de un dominio que en
  // https://<usuario>.github.io/mus-analytics/.
  base: "./",
  plugins: [react()],
  test: {
    include: ["test/**/*.test.ts"],
    environment: "node",
  },
});
