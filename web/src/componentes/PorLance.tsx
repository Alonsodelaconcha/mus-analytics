import { type VistaPorLance } from "../vista/entrenador";

/**
 * El porqué de «¿Mus o corto?»: lo que se gana o se pierde en cada lance por
 * dar mus en vez de cortar. Una barra por lance, a la derecha si se gana y a
 * la izquierda si se pierde.
 */
export function PorLance({ vista }: { vista: VistaPorLance }) {
  return (
    <div className="por-lance">
      <h3 className="por-lance__titulo">Por qué, lance a lance</h3>
      <p className="por-lance__frase">{vista.frase}</p>
      <ul className="por-lance__lista">
        {vista.lances.map((l) => (
          <li key={l.lance} className="por-lance__fila" data-efecto={l.efecto}>
            <span className="por-lance__nombre">{l.nombre}</span>
            <span className="por-lance__barra" aria-hidden="true">
              <span className="por-lance__relleno" style={{ width: `${String(Math.round(l.ancho * 50))}%` }} />
            </span>
            <span className="por-lance__cifra">{l.cifra}</span>
          </li>
        ))}
      </ul>
      <p className="nota por-lance__nota">Lo que cambia por dar mus en vez de cortar, en tantos por mano.</p>
    </div>
  );
}
