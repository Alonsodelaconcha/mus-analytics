import { useEffect, useState } from "react";

import { Datos } from "./nucleo";

/** Lee un fichero de datos publicado junto a la web. */
async function cargarFichero(ruta: string): Promise<ArrayBuffer> {
  const respuesta = await fetch(`${import.meta.env.BASE_URL}datos/${ruta}`);
  if (!respuesta.ok) {
    throw new Error(`No se pudo cargar ${ruta} (${respuesta.status})`);
  }
  return respuesta.arrayBuffer();
}

type Estado =
  | { readonly tipo: "cargando" }
  | { readonly tipo: "listo"; readonly datos: Datos }
  | { readonly tipo: "error"; readonly mensaje: string };

/**
 * Página provisional del paso 2: comprueba en el navegador que los datos se
 * cargan y coinciden con el núcleo. La interfaz llega en el paso 3.
 */
export function App() {
  const [estado, setEstado] = useState<Estado>({ tipo: "cargando" });

  useEffect(() => {
    Datos.cargar(cargarFichero)
      .then(async (datos) => {
        // La validación del manifiesto garantiza que la primera tabla existe.
        const [sinSenas] = datos.manifiesto.tablas_equity;
        await Promise.all([datos.mesa(), sinSenas && datos.equity(sinSenas)]);
        setEstado({ tipo: "listo", datos });
      })
      .catch((error: unknown) => {
        setEstado({ tipo: "error", mensaje: String(error) });
      });
  }, []);

  return (
    <main>
      <h1>Mus Analytics</h1>
      <p>En construcción.</p>
      {estado.tipo === "cargando" && <p>Cargando datos…</p>}
      {estado.tipo === "error" && <p role="alert">Error: {estado.mensaje}</p>}
      {estado.tipo === "listo" && (
        <p>
          Datos del {estado.datos.manifiesto.generado} cargados y verificados:{" "}
          {estado.datos.manifiesto.manos.length} manos, {estado.datos.manifiesto.senas.length} señas
          y {estado.datos.manifiesto.mesas.length} tipos de mesa.
        </p>
      )}
    </main>
  );
}
