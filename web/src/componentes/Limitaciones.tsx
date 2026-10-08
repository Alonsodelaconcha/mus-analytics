import { type Manifiesto } from "../nucleo/datos";
import { Desplegable } from "./Desplegable";

/** "ⓘ Cifras sin apostar (en paso)": las limitaciones, en lenguaje llano. */
export function Limitaciones({ manifiesto }: { manifiesto: Manifiesto | null }) {
  return (
    <section className="bloque bloque--discreto" aria-label="Limitaciones">
      <Desplegable titulo="ⓘ Cifras sin apostar (en paso)" clase="desplegable--discreto">
        <ul className="limitaciones">
          <li>
            <strong>Sin envites.</strong> Todas las cifras cuentan los tantos que se cobran en
            paso: sin envites, órdagos ni marcador. Con envites, las decisiones dudosas pueden
            cambiar.
          </li>
          <li>
            <strong>Una sola ronda de mus.</strong> «¿Mus o corto?» se calcula para la primera
            ronda.
          </li>
          <li>
            <strong>Las señas solo cuentan si no ha habido mus.</strong> Si ha habido mus, las
            probabilidades son sin información de tu compañero.
          </li>
          <li>
            <strong>No se tiene en cuenta quién ha cortado.</strong> Si corta un rival, suele ir
            bien, y estas cifras no lo reflejan.
          </li>
          <li>
            <strong>«¿Mus o corto?» no usa las señas</strong> ni lo que hables con tu compañero:
            cada uno decide con sus cartas. Y pueden cambiar la decisión: con A A 4 5 de postre en
            una mesa normal, la web dice «Corta», pero si tu compañero te ha hecho ciego conviene dar
            mus (unos 4 tantos más cada 10 manos).
          </li>
          <li>
            <strong>Tipo de mesa.</strong> Las decisiones dudosas dependen de cuánto se corte en tu
            mesa: elige el tipo que más se parezca.
          </li>
          <li>
            <strong>Exactas y simuladas.</strong> Las probabilidades sin mus son exactas. «¿Mus o
            corto?», los descartes y las cifras tras el mus salen de simular cientos de miles de
            manos, con un margen de error pequeño (se ve en «Más detalle»).
          </li>
        </ul>
        {manifiesto !== null && (
          <p className="nota">
            Datos del {manifiesto.generado} · motor {manifiesto.versiones.equity ?? "?"} ·
            mus a 8 reyes.
          </p>
        )}
      </Desplegable>
    </section>
  );
}
