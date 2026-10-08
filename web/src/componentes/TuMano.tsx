import { type ReactNode } from "react";

import { Carta } from "./Carta";
import { Segmentado } from "./Segmentado";

export const POSICIONES = [
  { valor: 1, texto: "Mano" },
  { valor: 2, texto: "Segundo" },
  { valor: 3, texto: "Tercero" },
  { valor: 4, texto: "Postre" },
] as const;

/**
 * La mano, compacta y siempre arriba: las cuatro cartas (se quitan
 * tocándolas), la jugada, de qué cartas se trata y la posición.
 */
export function TuMano({
  titulo,
  cartas,
  jugada,
  contexto,
  posicion,
  aviso,
  onQuitar,
  onPosicion,
}: {
  /** "Tu mano" o "Tu mano después del mus" (para los lectores de pantalla). */
  titulo: string;
  /** Rangos de mayor a menor. */
  cartas: readonly number[];
  /** Una línea por dato: ["Par de reyes", "31 de juego"], o una pista si faltan cartas. */
  jugada: readonly string[];
  /** De qué cartas se trata y el tipo de mesa, una línea por dato. */
  contexto: readonly string[];
  posicion: number | null;
  /** Aviso del giro de la posición, si lo hay. */
  aviso: ReactNode;
  onQuitar: (rango: number) => void;
  onPosicion: (posicion: number) => void;
}) {
  return (
    <section className="bloque mano" aria-label={titulo}>
      <div className="mano__fila">
        <div className="mano__cartas">
          {[0, 1, 2, 3].map((i) => {
            const r = cartas[i];
            return r === undefined ? (
              <Carta key={i} rango={null} pequena />
            ) : (
              <button key={i} type="button" className="mano__hueco"
                onClick={() => { onQuitar(r); }} aria-label={`Quitar carta ${String(i + 1)}`}>
                <Carta rango={r} pequena />
              </button>
            );
          })}
        </div>
        <div className="mano__info">
          <p className="mano__jugada" aria-live="polite">
            {jugada.map((linea, i) => <span key={i} className="mano__linea">{linea}</span>)}
          </p>
          <p className="mano__contexto">
            {contexto.map((linea, i) => <span key={i} className="mano__linea">{linea}</span>)}
          </p>
        </div>
      </div>
      <Segmentado etiqueta="Posición" etiquetaOculta opciones={POSICIONES} valor={posicion}
        onCambio={onPosicion} />
      {aviso}
    </section>
  );
}
