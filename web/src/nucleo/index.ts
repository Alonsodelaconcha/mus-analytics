/**
 * Núcleo de Mus Analytics en TypeScript: la parte del motor de Python que se
 * calcula en el navegador (leer y evaluar manos, opciones de descarte y
 * distribución exacta de la mano final) y la lectura de los datos
 * precalculados. Todo se comprueba contra los ficheros de referencia que
 * exporta `python -m mus exportar-web`.
 */

export * from "./cartas";
export * from "./datos";
export * from "./descarte";
export * from "./evaluacion";
export * from "./senas";
export * from "./sha256";
export * from "./tablas";
