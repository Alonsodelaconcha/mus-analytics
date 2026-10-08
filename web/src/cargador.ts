import { type Cargador } from "./nucleo/datos";

/** Lee los ficheros de datos publicados junto a la web (carpeta `datos/`). */
export const cargadorWeb: Cargador = async (ruta) => {
  const respuesta = await fetch(`${import.meta.env.BASE_URL}datos/${ruta}`);
  if (!respuesta.ok) {
    throw new Error(`No se pudo cargar ${ruta} (error ${String(respuesta.status)})`);
  }
  return respuesta.arrayBuffer();
};
