import { SIMBOLOS } from "../nucleo/cartas";
import { nombreSingular } from "../vista/lenguaje";

/**
 * Una carta con diseño propio: una letra grande en un rectángulo. Las figuras
 * (rey, caballo y sota) van en otro color para distinguirlas de un vistazo.
 */
export function Carta({ rango, pequena = false }: { rango: number | null; pequena?: boolean }) {
  const clase = `carta${pequena ? " carta--pequena" : ""}`;
  if (rango === null) {
    return <span className={`${clase} carta--vacia`} aria-hidden="true" />;
  }
  const simbolo = SIMBOLOS[rango] ?? "?";
  return (
    <span className={clase} data-figura={rango >= 5 ? "si" : undefined} role="img"
      aria-label={nombreSingular(rango)}>
      <span className="carta__simbolo">{simbolo}</span>
    </span>
  );
}
