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
      <p>{textoVersion(__VERSION_WEB__, guardado, datos, __COMMIT__)}</p>
      <p>{textoSinConexion(guardado)}</p>
      <p>
        <a href={REPOSITORIO} target="_blank" rel="noreferrer">Código fuente</a>
        {" · licencia AGPL-3.0"}
        {/* El fichero se genera al construir la web: en desarrollo no existe. Se abre
            aparte, como el código: la web instalada en el móvil no tiene botón de volver. */}
        {__MODO_SW__ !== "ninguno" && (
          <>
            {" · "}
            <a href={`${import.meta.env.BASE_URL}licencias-de-terceros.txt`} target="_blank" rel="noreferrer">
              licencias de terceros
            </a>
          </>
        )}
      </p>
    </footer>
  );
}
