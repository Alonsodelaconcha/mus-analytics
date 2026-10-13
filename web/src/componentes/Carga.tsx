import { type ReactNode } from "react";

import { type Recurso } from "../estado";
import { type FicheroMesa } from "../nucleo/datos";

/** Los datos no han llegado: el motivo y un botón para volver a intentarlo. */
export function DatosSinCargar({ error, onReintentar }: { error: string; onReintentar: () => void }) {
  return (
    <div className="bloque aviso" role="alert">
      <p>No se han podido cargar los datos: {error}</p>
      <button type="button" className="boton" onClick={onReintentar}>Reintentar</button>
    </div>
  );
}

/**
 * Mensaje de carga o de error de un recurso. `plural` concuerda el verbo:
 * "No se ha podido cargar la recomendación", "No se han podido cargar los descartes".
 */
export function Estado<T>({ recurso, que, plural }: { recurso: Recurso<T>; que: string; plural: boolean }) {
  if (recurso.estado === "error") {
    return (
      <p className="bloque aviso" role="alert">
        No se {plural ? "han" : "ha"} podido cargar {que}: {recurso.error}
      </p>
    );
  }
  return <p className="pista">Calculando {que}…</p>;
}

/** Pinta su contenido cuando el fichero de la mesa está cargado. */
export function ConMesa({ mesa, que, plural, children }: {
  mesa: Recurso<FicheroMesa>;
  que: string;
  plural: boolean;
  children: (mesa: FicheroMesa) => ReactNode;
}) {
  return mesa.estado === "listo"
    ? <>{children(mesa.valor)}</>
    : <Estado recurso={mesa} que={que} plural={plural} />;
}
