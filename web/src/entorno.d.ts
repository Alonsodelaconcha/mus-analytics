/** Constantes que pone `plugins/sinConexion.ts` al construir (y en los tests). */

/** Versión de la web (la de `package.json`). */
declare const __VERSION_WEB__: string;

/**
 * Qué service worker acompaña a esta versión: el normal, el de emergencia (la
 * página no registra ninguno) o ninguno (desarrollo y tests).
 */
declare const __MODO_SW__: "normal" | "emergencia" | "ninguno";
