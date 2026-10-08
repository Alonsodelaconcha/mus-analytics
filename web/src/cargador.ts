import { type Cargador } from "./nucleo/datos";

/** Lee los ficheros de datos publicados junto a la web (carpeta `datos/`). */
export const cargadorWeb: Cargador = async (ruta) => {
  let respuesta: Response;
  try {
    respuesta = await fetch(`${import.meta.env.BASE_URL}datos/${ruta}`);
  } catch {
    // Cada navegador da su propio mensaje en inglés ("Failed to fetch", "Load failed"...).
    throw new Error("no hay conexión con el servidor de la web");
  }
  if (!respuesta.ok) {
    throw new Error(`No se pudo cargar ${ruta} (error ${String(respuesta.status)})`);
  }
  return respuesta.arrayBuffer();
};
