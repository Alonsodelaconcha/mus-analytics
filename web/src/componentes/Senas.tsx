import { useEffect, useRef, useState } from "react";

import { type SenaDatos } from "../nucleo/datos";
import { Desplegable } from "./Desplegable";

/**
 * "¿Qué te ha dicho tu compañero?": las señas se marcan tocándolas y se
 * combinan (el compañero cumple todas). Incluye la chuleta con los gestos.
 */
export function Senas({
  senas,
  marcadas,
  onCambio,
  desactivadas,
  aviso,
}: {
  senas: readonly SenaDatos[];
  marcadas: readonly string[];
  onCambio: (ids: string[]) => void;
  /** Tras el mus las señas aún no se tienen en cuenta. */
  desactivadas: boolean;
  /** Problema con las señas marcadas (imposibles juntas o con tus cartas). */
  aviso: string | null;
}) {
  const [chuleta, setChuleta] = useState(false);
  const nombres = senas.filter((s) => marcadas.includes(s.id)).map((s) => s.nombre);
  const resumen = desactivadas ? "No se usan tras el mus" : nombres.length === 0 ? "Ninguna" : nombres.join(" + ");

  const alternar = (id: string): void => {
    onCambio(marcadas.includes(id) ? marcadas.filter((x) => x !== id) : [...marcadas, id]);
  };

  return (
    <section className="bloque" aria-label="Señas del compañero">
      <Desplegable titulo="¿Qué te ha dicho tu compañero?" resumen={resumen}>
        {desactivadas ? (
          <p className="nota">
            Tras el mus, las señas todavía no se tienen en cuenta: las probabilidades son sin
            información del compañero. Llegará en una versión posterior.
          </p>
        ) : (
          <>
            <p className="nota">Marca todas las señas que te haya hecho. Si no te ha hecho ninguna, no marques nada.</p>
            <div className="senas">
              {senas.map((s) => (
                <button key={s.id} type="button" className="sena" aria-pressed={marcadas.includes(s.id)}
                  onClick={() => { alternar(s.id); }}>
                  {s.nombre}
                </button>
              ))}
            </div>
            {aviso !== null && <p className="aviso" role="status">{aviso}</p>}
          </>
        )}
        <button type="button" className="boton boton--enlace" onClick={() => { setChuleta(true); }}>
          Ver la chuleta de señas
        </button>
      </Desplegable>
      {chuleta && <Chuleta senas={senas} onCerrar={() => { setChuleta(false); }} />}
    </section>
  );
}

function Chuleta({ senas, onCerrar }: { senas: readonly SenaDatos[]; onCerrar: () => void }) {
  const cerrar = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    cerrar.current?.focus();
    const alPulsar = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onCerrar();
    };
    document.addEventListener("keydown", alPulsar);
    return () => { document.removeEventListener("keydown", alPulsar); };
  }, [onCerrar]);

  return (
    <div className="velo" onClick={onCerrar}>
      <div className="dialogo" role="dialog" aria-modal="true" aria-labelledby="titulo-chuleta"
        onClick={(e) => { e.stopPropagation(); }}>
        <div className="dialogo__cabecera">
          <h2 id="titulo-chuleta">Chuleta de señas</h2>
          <button ref={cerrar} type="button" className="boton boton--secundario" onClick={onCerrar}>
            Cerrar
          </button>
        </div>
        <p className="nota">
          Las de nuestra mesa. Son libres: se puede hacer una, varias o ninguna. En 8 reyes, el 3
          cuenta como rey y el 2 como as.
        </p>
        <dl className="chuleta">
          {senas.map((s) => (
            <div key={s.id} className="chuleta__fila">
              <dt>{s.nombre}</dt>
              <dd>
                <span className="chuleta__gesto">{s.gesto}</span>
                <span className="chuleta__cartas">{s.cartas}</span>
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
