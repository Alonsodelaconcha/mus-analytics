import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig(
  { ignores: ["dist", "public", "test/referencia"] },
  js.configs.recommended,
  tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Los números en plantillas de texto son habituales aquí (mensajes con cifras).
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
    extends: [reactHooks.configs.flat.recommended],
    rules: {
      // APIs que solo existen en contextos seguros (HTTPS o localhost). Abierta
      // por la red local (http://192.168…) no están: hay que comprobarlas antes
      // y que la web siga funcionando sin ellas. Ver docs/decisiones.md.
      "no-restricted-properties": [
        "error",
        { object: "crypto", property: "subtle", message: "Solo en contextos seguros: usa sha256() de nucleo/datos." },
        { object: "crypto", property: "randomUUID", message: "Solo en contextos seguros." },
        { object: "navigator", property: "serviceWorker", message: "Solo en contextos seguros: comprueba antes que exista." },
        { object: "navigator", property: "clipboard", message: "Solo en contextos seguros: comprueba antes que exista." },
        { object: "navigator", property: "storage", message: "Solo en contextos seguros: comprueba antes que exista." },
      ],
      "no-restricted-globals": [
        "error",
        { name: "caches", message: "La caché del navegador solo existe en contextos seguros: comprueba antes que exista." },
      ],
    },
  },
  {
    files: ["test/**/*.ts", "vite.config.ts", "eslint.config.js"],
    languageOptions: { globals: globals.node },
  },
);
