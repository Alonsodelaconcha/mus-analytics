import { useState } from "react";

import { LANCES, type Lance } from "../nucleo/evaluacion";
import { porcentaje } from "../vista/lenguaje";
import { type VistaOpcion, frasesResumen } from "../vista/vista";

const VISIBLES = 4;
const NOMBRE: Readonly<Record<Lance, string>> = {
  grande: "Grande",
  chica: "Chica",
  pares: "Pares",
  juego: "Juego",
  punto: "Punto",
};

/**
 * "Si hay mus, ¿qué tiro?": el mejor descarte y las alternativas. Al tocar
 * una opción se ve con qué acabarías y cuánto ganaríais tras el mus.
 */
export function Descartes({
  opciones,
  trasDescarte,
}: {
  opciones: readonly VistaOpcion[];
  /** Probabilidad de ganar cada lance tras el mus con cada opción (o null si no se puede). */
  trasDescarte: (opcion: VistaOpcion) => Readonly<Record<Lance, number>> | null;
}) {
  const [elegida, setElegida] = useState(0);
  const [todas, setTodas] = useState(false);
  const mejor = opciones[0];
  if (mejor === undefined) {
    return (
      <section className="bloque">
        <h2 className="bloque__titulo">Si hay mus, ¿qué tiro?</h2>
        <p className="nota">Con esta mano y posición no llega a haber mus en la mesa elegida.</p>
      </section>
    );
  }
  const seleccion = opciones[elegida] ?? mejor;
  const visibles = todas ? opciones : opciones.slice(0, VISIBLES);
  const ganar = trasDescarte(seleccion);

  return (
    <section className="bloque" aria-labelledby="titulo-descartes">
      <h2 className="bloque__titulo" id="titulo-descartes">Si hay mus, ¿qué tiro?</h2>
      <p className="descarte__mejor">{mejor.titulo}</p>
      <p className="descarte__detalle">{mejor.detalle}.</p>

      <ul className="opciones">
        {visibles.map((o, i) => (
          <li key={o.valor.opcion.codigo}>
            <button type="button" className="opcion" aria-pressed={i === elegida}
              data-mejor={o.mejor || o.casiIgual ? "si" : undefined}
              onClick={() => { setElegida(i); }}>
              <span className="opcion__titulo">{o.titulo}</span>
              <span className="opcion__comparacion">{o.comparacion}</span>
            </button>
          </li>
        ))}
      </ul>
      {opciones.length > VISIBLES && (
        <button type="button" className="boton boton--enlace" onClick={() => { setTodas(!todas); }}>
          {todas ? "Ver menos" : `Ver las ${opciones.length} formas de descartarte`}
        </button>
      )}

      <div className="descarte__resultado" aria-live="polite">
        <h3>{seleccion.titulo}: con qué acabarías</h3>
        <ul className="frases">
          {frasesResumen(seleccion.resumen).map((f) => <li key={f}>{f}</li>)}
        </ul>
        {ganar !== null && (
          <>
            <h3>Y tras el mus, ganaríais…</h3>
            <ul className="mini-lances">
              {LANCES.map((l) => (
                <li key={l}><span>{NOMBRE[l]}</span> <strong>{porcentaje(ganar[l])}</strong></li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
