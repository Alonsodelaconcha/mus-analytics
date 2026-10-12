import { type EstadoSinConexion } from "../sinConexion";
import { textoSinConexion, textoVersion } from "../vista/lenguaje";

const REPOSITORIO = "https://github.com/Alonsodelaconcha/mus-analytics";

/**
 * Pie de la página: qué versión hay en este móvil, si está guardada para
 * usarla sin conexión, y dónde están el código y las licencias.
 */
export function Creditos({ guardado, datos }: { guardado: EstadoSinConexion; datos: string | null }) {
  return (
    <footer className="creditos">
      <p>{textoVersion(__VERSION_WEB__, guardado, datos)}</p>
      <p>{textoSinConexion(guardado)}</p>
      <p>
        <a href={REPOSITORIO} target="_blank" rel="noreferrer">Código fuente</a>
        {" · licencia AGPL-3.0"}
        {/* El fichero se genera al construir la web: en desarrollo no existe. */}
        {__MODO_SW__ !== "ninguno" && (
          <>
            {" · "}
            <a href={`${import.meta.env.BASE_URL}licencias-de-terceros.txt`}>licencias de terceros</a>
          </>
        )}
      </p>
    </footer>
  );
}
