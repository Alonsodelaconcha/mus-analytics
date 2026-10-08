import { type ReactNode, useEffect, useId, useRef, useState } from "react";

import { type Lance } from "../nucleo/evaluacion";
import { porcentaje } from "../vista/lenguaje";
import { type VistaProbabilidades } from "../vista/vista";

/**
 * Las cinco probabilidades de ganar en una fila: en cada lance, la de la
 * pareja y su frecuencia en corto ("9 de 10"). Al tocar un lance se ve la
 * frase completa y la probabilidad de ganarlo tú solo.
 */
export function FilaLances({
  titulo,
  nota,
  vista,
}: {
  titulo: string;
  nota: ReactNode;
  vista: VistaProbabilidades;
}) {
  const [elegido, setElegido] = useState<Lance | null>(null);
  const idTitulo = useId();
  const detalle = vista.lances.find((l) => l.lance === elegido);
  // Al tocar un lance, que se vea su frase aunque quede bajo el pie fijo (ver scroll-margin en el CSS).
  const refDetalle = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (elegido !== null) refDetalle.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [elegido]);

  return (
    <section className="bloque" aria-labelledby={idTitulo}>
      <h2 className="bloque__titulo" id={idTitulo}>{titulo}</h2>
      <p className="nota">{nota}</p>
      <div className="fila-lances">
        {vista.lances.map((l) => (
          <button key={l.lance} type="button" className="fila-lances__lance"
            aria-pressed={l.lance === elegido} data-sin-jugar={l.sinJugar ? "si" : undefined}
            onClick={() => { setElegido(l.lance === elegido ? null : l.lance); }}>
            <span className="fila-lances__nombre">{l.nombre}</span>
            <span className="fila-lances__cifra">{l.sinJugar ? "—" : porcentaje(l.pareja)}</span>
            <span className="fila-lances__frecuencia">{l.frecuenciaCorta}</span>
          </button>
        ))}
      </div>
      <div ref={refDetalle} className="fila-lances__detalle" aria-live="polite">
        {detalle === undefined ? (
          <p className="nota">Toca un lance para ver la frase completa y lo que ganas tú solo.</p>
        ) : (
          <>
            <p className="lance__frase">
              {detalle.frase}
              {!detalle.sinJugar && <> <span className="lance__yo">Tú solo: {porcentaje(detalle.yo)}.</span></>}
            </p>
            {detalle.nota !== "" && <p className="lance__nota">{detalle.nota}</p>}
          </>
        )}
      </div>
      <p className="tantos">{vista.fraseTantos}</p>
    </section>
  );
}
