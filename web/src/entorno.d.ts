/** Constantes que pone `plugins/sinConexion.ts` al construir (y en los tests). */

/** Versión de la web (la de `package.json`). */
declare const __VERSION_WEB__: string;

/**
 * Commit del repositorio del que se ha construido la web, abreviado; con un "+"
 * detrás si había cambios sin confirmar en `web/`. `null` en desarrollo, en los
 * tests y si no hay git.
 */
declare const __COMMIT__: string | null;

/**
 * Qué service worker acompaña a esta versión: el normal, el de emergencia (la
 * página no registra ninguno) o ninguno (desarrollo y tests).
 */
declare const __MODO_SW__: "normal" | "emergencia" | "ninguno";
