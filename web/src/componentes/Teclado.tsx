import { SIMBOLOS } from "../nucleo/cartas";
import { NOMBRES_TECLA, nombreSingular } from "../vista/lenguaje";

/** Teclas de mayor a menor, como piensa un jugador: R C S 7 / 6 5 4 A. */
const ORDEN = [7, 6, 5, 4, 3, 2, 1, 0] as const;

/**
 * Teclado de cartas, fijo abajo para usarlo con el pulgar. Cada carta es un
 * botón grande; el 3 entra como rey y el 2 como as.
 */
export function Teclado({
  cuantas,
  titulo,
  onCarta,
  onBorrar,
  onNueva,
}: {
  cuantas: number;
  titulo: string;
  onCarta: (rango: number) => void;
  onBorrar: () => void;
  onNueva: () => void;
}) {
  return (
    <div className="teclado" role="group" aria-label="Teclado de cartas">
      <p className="teclado__titulo">{titulo} <span className="teclado__cuenta">{cuantas}/4</span></p>
      <div className="teclado__cartas">
        {ORDEN.map((r) => (
          <button key={r} type="button" className="tecla" data-figura={r >= 5 ? "si" : undefined}
            disabled={cuantas >= 4} onClick={() => { onCarta(r); }}
            aria-label={`Añadir ${nombreSingular(r)}`}>
            <span className="tecla__simbolo">{SIMBOLOS[r]}</span>
            <span className="tecla__nombre">{NOMBRES_TECLA[r]}</span>
          </button>
        ))}
      </div>
      <div className="teclado__acciones">
        <button type="button" className="boton boton--secundario" disabled={cuantas === 0}
          onClick={onBorrar}>⌫ Borrar</button>
        <button type="button" className="boton boton--secundario" onClick={onNueva}>Nueva mano</button>
      </div>
    </div>
  );
}
