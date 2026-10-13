import { type ReactNode, useMemo } from "react";

import { ConMesa, DatosSinCargar, Estado } from "./componentes/Carga";
import { Decision, SelectorMesa } from "./componentes/Decision";
import { Descartes } from "./componentes/Descartes";
import { FilaLances } from "./componentes/FilaLances";
import { ID_PANEL, Pestanas, idPestana } from "./componentes/Pestanas";
import { Probabilidades } from "./componentes/Probabilidades";
import { Senas } from "./componentes/Senas";
import { Teclado } from "./componentes/Teclado";
import { POSICIONES, TuMano } from "./componentes/TuMano";
import { type Recurso, usePromesa } from "./estado";
import { type Accion, type EstadoMano, type Pestana, cartasDe } from "./mano";
import { desdeRangos, rangos } from "./nucleo/cartas";
import {
  type Datos,
  type FicheroMesa,
  type Manifiesto,
  decisionDe,
  equityDe,
  opcionesDe,
} from "./nucleo/datos";
import { tablaParaSenas } from "./nucleo/senas";
import { indiceMano } from "./nucleo/tablas";
import { describirMano } from "./vista/lenguaje";
import {
  probabilidadesTrasDescarte,
  vistaDecision,
  vistaDescartes,
  vistaProbabilidades,
} from "./vista/vista";

/**
 * La calculadora, pensada para el móvil. Arriba, la mano y la posición; en
 * medio, lo que toca en cada momento de la mano; abajo, fijos para el pulgar,
 * el teclado de cartas (o «Nueva mano») y las tres pestañas:
 *
 * - «¿Mus o corto?»: la recomendación y el descarte;
 * - «Se ha cortado»: las señas y las probabilidades con las cartas del reparto;
 * - «Ha habido mus»: las cartas nuevas y las probabilidades tras el mus.
 *
 * La mano que se está metiendo vive en `App` (`estado`), para que siga ahí al
 * volver del entrenador.
 */
export function Calculadora({
  datos,
  onReintentar,
  estado,
  despachar,
  mesaId,
  nombreMesa,
  onMesa,
  avisoVersion,
  pieDePagina,
}: {
  datos: Recurso<Datos>;
  onReintentar: () => void;
  estado: EstadoMano;
  despachar: (accion: Accion) => void;
  mesaId: string;
  nombreMesa: string;
  onMesa: (id: string) => void;
  /** Aviso de versión nueva, si lo hay. */
  avisoVersion: ReactNode;
  /** Limitaciones y créditos: lo mismo en la calculadora y en el entrenador. */
  pieDePagina: ReactNode;
}) {
  const { pestana, posicion, senas, giro } = estado;
  const cartas = cartasDe(estado);

  const d = datos.estado === "listo" ? datos.valor : null;
  const manifiesto = d?.manifiesto ?? null;

  const mano = useMemo(() => desdeRangos(cartas), [cartas]);
  const completa = cartas.length === 4;
  const indice = completa ? indiceMano(mano) : null;

  // Las señas solo cuentan en «Se ha cortado».
  const resultadoSenas = useMemo(
    () => (manifiesto !== null && pestana === "cortado" ? tablaParaSenas(manifiesto, senas) : null),
    [manifiesto, pestana, senas],
  );
  const promesaEquity = useMemo(
    () => (d !== null && resultadoSenas !== null && resultadoSenas.tipo !== "imposible"
      ? d.equity(resultadoSenas.tabla)
      : null),
    [d, resultadoSenas],
  );
  const equity = usePromesa(promesaEquity);
  const promesaMesa = useMemo(() => (d !== null ? d.mesa(mesaId) : null), [d, mesaId]);
  const mesa = usePromesa(promesaMesa);

  // Equity de mi mano con las cartas del reparto: null si las señas son imposibles con mis cartas.
  const miEquity = equity.estado === "listo" && indice !== null && posicion !== null && manifiesto !== null
    ? equityDe(equity.valor.datos, manifiesto.escalas, indice, posicion)
    : undefined;
  let avisoSenas: string | null = null;
  if (resultadoSenas?.tipo === "imposible") {
    avisoSenas = "Esas señas no pueden ir juntas: ninguna mano las cumple todas.";
  } else if (miEquity === null) {
    avisoSenas = "Con tus cartas, tu compañero no puede tener eso: revisa las señas.";
  }

  // Con un reducer, dos toques muy seguidos no pueden pisarse. Al cambiar de
  // momento de la mano, se vuelve arriba para ver la pestaña desde el principio.
  const subir = (): void => {
    if (window.scrollY > 0) window.scrollTo({ top: 0 });
  };
  const nuevaMano = (): void => {
    despachar({ tipo: "nueva-mano" });
    subir();
  };
  const cambiarPestana = (p: Pestana): void => {
    despachar({ tipo: "pestana", pestana: p });
    subir();
  };

  const nombre = (p: number | null): string => POSICIONES.find((x) => x.valor === p)?.texto ?? "";
  const nombrePosicion = nombre(posicion);
  const selectorMesa = manifiesto !== null && (
    <SelectorMesa mesas={manifiesto.mesas} valor={mesaId} onCambio={onMesa} />
  );
  const trasMus = pestana === "mus";
  // Junto a la mano: de qué cartas se trata y, donde cuenta, el tipo de mesa.
  const lineaMesa = nombreMesa === "" ? [] : [`Mesa: ${nombreMesa.toLowerCase()}`];
  const contexto = {
    decidir: lineaMesa,
    cortado: ["Cartas del reparto"],
    mus: ["Cartas tras el mus", ...lineaMesa],
  }[pestana];

  let panel: ReactNode;
  if (datos.estado === "cargando" || datos.estado === "inactivo") {
    panel = <p className="pista">Cargando datos…</p>;
  } else if (datos.estado === "error") {
    panel = <DatosSinCargar error={datos.error} onReintentar={onReintentar} />;
  } else if (manifiesto === null) {
    panel = null;
  } else {
    let resultados: ReactNode;
    if (!completa) {
      resultados = (
        <p className="pista">
          {trasMus ? "Mete las 4 cartas que tienes después del mus." : "Mete tus 4 cartas con el teclado de abajo."}
        </p>
      );
    } else if (posicion === null || indice === null) {
      resultados = <p className="pista pista--destacada">¿En qué posición estás? Elígela arriba.</p>;
    } else if (pestana === "decidir") {
      resultados = (
        <>
          <ConMesa mesa={mesa} que="la recomendación" plural={false}>
            {(m) => {
              const decision = decisionDe(m, manifiesto.escalas, indice, posicion);
              return decision === null
                ? <p className="pista">No hay recomendación para esta mano.</p>
                : <Decision vista={vistaDecision(decision)} posicion={nombrePosicion} selectorMesa={selectorMesa} />;
            }}
          </ConMesa>
          <ConMesa mesa={mesa} que="los descartes" plural>
            {(m) => (
              <BloqueDescartes key={`${String(indice)}-${String(posicion)}-${mesaId}`} mesa={m}
                manifiesto={manifiesto} mano={mano} indice={indice} posicion={posicion} />
            )}
          </ConMesa>
        </>
      );
    } else if (pestana === "cortado") {
      resultados = avisoSenas !== null ? (
        <p className="pista">Corrige las señas para ver las probabilidades de ganar.</p>
      ) : miEquity === undefined || miEquity === null ? (
        <Estado recurso={equity} que="las probabilidades" plural />
      ) : (
        <FilaLances
          titulo="Si se juega con estas cartas, ganáis…"
          nota={resultadoSenas?.tipo === "tabla" ? "Exacto, con las señas marcadas." : "Exacto, sin señas de tu compañero."}
          vista={vistaProbabilidades(miEquity, mano)}
        />
      );
    } else {
      resultados = (
        <ConMesa mesa={mesa} que="las probabilidades" plural>
          {(m) => {
            const e = equityDe(m.tras_mus.datos, manifiesto.escalas, indice, posicion);
            return e === null ? null : (
              <Probabilidades
                titulo="Tras el mus"
                subtitulo={
                  <>
                    Frente a lo que suelen llevar los demás tras descartarse en una mesa
                    «{nombreMesa}». Sin señas: llegarán en una versión posterior.
                  </>
                }
                vista={vistaProbabilidades(e, mano)}
                pie={selectorMesa}
              />
            );
          }}
        </ConMesa>
      );
    }
    panel = (
      <>
        {pestana === "cortado" && (
          <Senas senas={manifiesto.senas} marcadas={senas} aviso={avisoSenas}
            onCambio={(ids) => { despachar({ tipo: "senas", ids }); }} />
        )}
        {resultados}
      </>
    );
  }

  return (
    <>
      <main>
        {avisoVersion}

        <TuMano
          titulo={trasMus ? "Tu mano después del mus" : "Tu mano"}
          cartas={rangos(mano)}
          jugada={completa
            ? describirMano(mano)
            : [cartas.length === 0 ? "El 3 es rey y el 2 es as." : "Toca una carta para quitarla."]}
          contexto={contexto}
          posicion={posicion}
          onQuitar={(rango) => { despachar({ tipo: "quitar", rango }); }}
          onPosicion={(p) => { despachar({ tipo: "posicion", posicion: p }); }}
          aviso={giro !== null && posicion !== null && (
            <p className="aviso aviso--giro" role="status">
              {giro.veces > 1 ? `Ojo: has pulsado «Nueva mano» ${String(giro.veces)} veces seguidas: ` : "Nueva mano: "}
              ahora eres <strong>{nombrePosicion.toLowerCase()}</strong> (antes, {nombre(giro.desde).toLowerCase()}).
              Si no es así, toca tu posición.
            </p>
          )}
        />

        <div className="panel" role="tabpanel" id={ID_PANEL} aria-labelledby={idPestana(pestana)}>
          {panel}
        </div>

        {pieDePagina}
      </main>

      <div className="pie">
        {completa ? (
          <div className="pie__acciones">
            <button type="button" className="boton" onClick={nuevaMano}>Nueva mano</button>
          </div>
        ) : (
          <Teclado cuantas={cartas.length}
            titulo={`${trasMus ? "Cartas después del mus" : "Tus cartas"} · ${posicion === null ? "elige tu posición arriba" : `eres ${nombrePosicion.toLowerCase()}`}`}
            onCarta={(rango) => { despachar({ tipo: "poner", rango }); }}
            onBorrar={() => { despachar({ tipo: "borrar" }); }} onNueva={nuevaMano} />
        )}
        <Pestanas valor={pestana} onCambio={cambiarPestana} />
      </div>
    </>
  );
}

function BloqueDescartes({ mesa, manifiesto, mano, indice, posicion }: {
  mesa: FicheroMesa;
  manifiesto: Manifiesto;
  mano: readonly number[];
  indice: number;
  posicion: number;
}) {
  const opciones = useMemo(
    () => vistaDescartes(opcionesDe(mesa, manifiesto, mano, indice, posicion), mano),
    [mesa, manifiesto, mano, indice, posicion],
  );
  return (
    <Descartes opciones={opciones}
      trasDescarte={(o) => probabilidadesTrasDescarte(o.distribucion, mesa.tras_mus.datos,
        manifiesto.escalas, posicion)} />
  );
}
