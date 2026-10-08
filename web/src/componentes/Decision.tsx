import { type ReactNode } from "react";

import { type MesaDatos } from "../nucleo/datos";
import { conSigno, decimal, porcentaje } from "../vista/lenguaje";
import { type VistaDecision } from "../vista/vista";
import { Desplegable } from "./Desplegable";
import { Segmentado } from "./Segmentado";

/** Nombres cortos de los tipos de mesa para el selector. */
const CORTO: Readonly<Record<string, string>> = {
  "mucho-mus": "Mucho mus",
  normal: "Normal",
  "se-corta": "Se corta mucho",
};

export function SelectorMesa({
  mesas,
  valor,
  onCambio,
}: {
  mesas: readonly MesaDatos[];
  valor: string;
  onCambio: (id: string) => void;
}) {
  const actual = mesas.find((m) => m.id === valor);
  return (
    <div className="selector-mesa">
      <Segmentado etiqueta="Tipo de mesa" pequeno valor={valor} onCambio={onCambio}
        opciones={mesas.map((m) => ({ valor: m.id, texto: CORTO[m.id] ?? m.nombre }))} />
      {actual !== undefined && <p className="nota">{actual.descripcion}</p>}
    </div>
  );
}

/** "¿Mus o corto?": el veredicto en grande y, debajo, cuánto se gana. */
export function Decision({
  vista,
  posicion,
  selectorMesa,
}: {
  vista: VistaDecision;
  posicion: string;
  selectorMesa: ReactNode;
}) {
  return (
    <section className="bloque decision" data-veredicto={vista.veredicto} aria-labelledby="titulo-decision">
      <h2 className="bloque__titulo" id="titulo-decision">
        ¿Mus o corto? <span className="bloque__contexto">Siendo {posicion.toLowerCase()}</span>
      </h2>
      <p className="decision__veredicto">
        <span className="decision__titulo">{vista.titulo}</span>
        {vista.etiqueta !== "" && <span className="decision__etiqueta">{vista.etiqueta}</span>}
      </p>
      <p className="decision__explicacion">{vista.explicacion}</p>
      {vista.matiz !== "" && <p className="decision__matiz">{vista.matiz}</p>}
      {/* Fijo: el compañero hace las señas antes de que decidas, y en el MVP no cuentan aquí. */}
      <p className="nota decision__senas">No tiene en cuenta las señas de tu compañero.</p>
      {selectorMesa}
      <Desplegable titulo="Más detalle" clase="desplegable--discreto">
        <ul className="detalle">
          <li>
            Dar mus menos cortar: {conSigno(vista.ventaja)} tantos por mano
            (margen de error ±{decimal(vista.radio)}).
          </li>
          <li>
            Si das mus, los que hablan después también lo dan {porcentaje(vista.pMusDespues)} de
            las veces; si alguno corta, se juega con las cartas del reparto.
          </li>
          <li>
            Calculado simulando {vista.repartos.toLocaleString("es-ES")} repartos con tus cartas,
            en los que cada uno corta o se descarta según el tipo de mesa.
          </li>
        </ul>
      </Desplegable>
    </section>
  );
}
