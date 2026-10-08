import { type ReactNode } from "react";

import { porcentaje } from "../vista/lenguaje";
import { type VistaProbabilidades } from "../vista/vista";

/**
 * Probabilidad de ganar cada lance, con una barra por lance y la frase en
 * lenguaje de jugador. "Ganáis" es tu pareja (tú o tu compañero).
 */
export function Probabilidades({
  titulo,
  subtitulo,
  vista,
  pie,
}: {
  titulo: string;
  subtitulo: ReactNode;
  vista: VistaProbabilidades;
  pie?: ReactNode;
}) {
  return (
    <section className="bloque" aria-labelledby="titulo-probabilidades">
      <h2 className="bloque__titulo" id="titulo-probabilidades">{titulo}</h2>
      <p className="nota">{subtitulo}</p>
      <ul className="lances">
        {vista.lances.map((l) => (
          <li key={l.lance} className="lance" data-sin-jugar={l.seJuega === 0 ? "si" : undefined}>
            <div className="lance__cabecera">
              <span className="lance__nombre">{l.nombre}</span>
              <span className="lance__cifra">{porcentaje(l.pareja)}</span>
            </div>
            <div className="barra" aria-hidden="true">
              <span className="barra__yo" style={{ width: `${(l.yo * 100).toFixed(1)}%` }} />
              <span className="barra__pareja" style={{ width: `${((l.pareja - l.yo) * 100).toFixed(1)}%` }} />
            </div>
            <p className="lance__frase">
              {l.frase}{" "}
              {l.seJuega > 0 && <span className="lance__yo">Tú solo: {porcentaje(l.yo)}.</span>}
            </p>
            {l.nota !== "" && <p className="lance__nota">{l.nota}</p>}
          </li>
        ))}
      </ul>
      <p className="tantos">{vista.fraseTantos}</p>
      {pie}
    </section>
  );
}
