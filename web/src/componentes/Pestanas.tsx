import { type KeyboardEvent, useRef } from "react";

import { type Pestana } from "../mano";

/** Una pestaña por momento de la mano, con lo que la distingue debajo. */
export const PESTANAS: readonly { readonly valor: Pestana; readonly titulo: string; readonly subtitulo: string }[] = [
  { valor: "decidir", titulo: "¿Mus o corto?", subtitulo: "decidir" },
  { valor: "cortado", titulo: "Se ha cortado", subtitulo: "cartas del reparto" },
  { valor: "mus", titulo: "Ha habido mus", subtitulo: "cartas nuevas" },
];

export const ID_PANEL = "panel-pestana";
export const idPestana = (p: Pestana): string => `pestana-${p}`;

/**
 * Las pestañas, en la barra de abajo para tocarlas con el pulgar. Siguen el
 * patrón de pestañas accesible: con el teclado, las flechas cambian de pestaña.
 */
export function Pestanas({ valor, onCambio }: { valor: Pestana; onCambio: (p: Pestana) => void }) {
  const botones = useRef<(HTMLButtonElement | null)[]>([]);

  const alPulsar = (e: KeyboardEvent, i: number): void => {
    const paso = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    const destino = PESTANAS[(i + paso + PESTANAS.length) % PESTANAS.length];
    if (paso === 0 || destino === undefined) return;
    e.preventDefault();
    onCambio(destino.valor);
    botones.current[PESTANAS.indexOf(destino)]?.focus();
  };

  return (
    <div className="pestanas" role="tablist" aria-label="Momento de la mano">
      {PESTANAS.map((p, i) => (
        <button key={p.valor} ref={(b) => { botones.current[i] = b; }} type="button" role="tab"
          id={idPestana(p.valor)} className="pestana" aria-selected={p.valor === valor}
          aria-controls={ID_PANEL} tabIndex={p.valor === valor ? 0 : -1}
          onClick={() => { onCambio(p.valor); }} onKeyDown={(e) => { alPulsar(e, i); }}>
          <span className="pestana__titulo">{p.titulo}</span>
          <span className="pestana__subtitulo">{p.subtitulo}</span>
        </button>
      ))}
    </div>
  );
}
