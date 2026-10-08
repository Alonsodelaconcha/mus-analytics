import { type ReactNode, useMemo, useState } from "react";

import { Carta } from "./componentes/Carta";
import { Decision, SelectorMesa } from "./componentes/Decision";
import { Descartes } from "./componentes/Descartes";
import { Limitaciones } from "./componentes/Limitaciones";
import { Probabilidades } from "./componentes/Probabilidades";
import { Segmentado } from "./componentes/Segmentado";
import { Senas } from "./componentes/Senas";
import { Teclado } from "./componentes/Teclado";
import { type Recurso, usePreferencia, usePromesa } from "./estado";
import { desdeRangos, rangos } from "./nucleo/cartas";
import {
  type Cargador,
  Datos,
  type FicheroMesa,
  type Manifiesto,
  decisionDe,
  equityDe,
  opcionesDe,
} from "./nucleo/datos";
import { tablaParaSenas } from "./nucleo/senas";
import { indiceMano } from "./nucleo/tablas";
import { describirJuego, describirPares } from "./vista/lenguaje";
import {
  probabilidadesTrasDescarte,
  vistaDecision,
  vistaDescartes,
  vistaProbabilidades,
} from "./vista/vista";

const POSICIONES = [
  { valor: 1, texto: "Mano" },
  { valor: 2, texto: "Segundo" },
  { valor: 3, texto: "Tercero" },
  { valor: 4, texto: "Postre" },
] as const;

const esTexto = (v: string): v is string => v.length > 0;

/**
 * La calculadora: una sola pantalla pensada para el móvil. Arriba, la mano,
 * la posición y las señas; debajo, los resultados; abajo del todo, fijo, el
 * teclado de cartas para usarlo con el pulgar.
 */
export function App({ cargador }: { cargador: Cargador }) {
  // Reintentar (p. ej. al volver la cobertura) crea una carga nueva.
  const [promesaDatos, setPromesaDatos] = useState(() => Datos.cargar(cargador));
  const datos = usePromesa(promesaDatos);

  const [cartas, setCartas] = useState<number[]>([]);
  const [posicion, setPosicion] = useState<number | null>(null);
  const [huboMus, setHuboMus] = useState(false);
  const [senas, setSenas] = useState<string[]>([]);
  const [mesaGuardada, setMesa] = usePreferencia("mus-analytics.mesa", "normal", esTexto);

  const d = datos.estado === "listo" ? datos.valor : null;
  const manifiesto = d?.manifiesto ?? null;
  const mesaId = manifiesto?.mesas.some((m) => m.id === mesaGuardada) === true
    ? mesaGuardada
    : (manifiesto?.mesas.find((m) => m.por_defecto)?.id ?? mesaGuardada);

  const mano = useMemo(() => desdeRangos(cartas), [cartas]);
  const completa = cartas.length === 4;
  const indice = completa ? indiceMano(mano) : null;

  const resultadoSenas = useMemo(
    () => (manifiesto !== null && !huboMus ? tablaParaSenas(manifiesto, senas) : null),
    [manifiesto, huboMus, senas],
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

  // Equity de mi mano (sin mus): null si las señas son imposibles con mis cartas.
  const miEquity = equity.estado === "listo" && indice !== null && posicion !== null && manifiesto !== null
    ? equityDe(equity.valor.datos, manifiesto.escalas, indice, posicion)
    : undefined;
  let avisoSenas: string | null = null;
  if (resultadoSenas?.tipo === "imposible") {
    avisoSenas = "Esas señas no pueden ir juntas: ninguna mano las cumple todas.";
  } else if (miEquity === null) {
    avisoSenas = "Con tus cartas, tu compañero no puede tener eso: revisa las señas.";
  }

  // Actualizaciones funcionales: dos toques muy seguidos no pueden pisarse.
  const ponerCarta = (rango: number): void => {
    setCartas((c) => (c.length < 4 ? [...c, rango] : c));
  };
  const quitarCarta = (rango: number): void => {
    setCartas((c) => {
      const i = c.lastIndexOf(rango);
      return i < 0 ? c : [...c.slice(0, i), ...c.slice(i + 1)];
    });
  };
  const nuevaMano = (): void => {
    setCartas([]);
    setSenas([]);
    setHuboMus(false);
  };
  // Tras el mus la mano siempre es otra (hay que tirar al menos una carta): se vacía.
  const cambiarMus = (si: boolean): void => {
    if (si === huboMus) return;
    setHuboMus(si);
    setCartas([]);
    if (si) setSenas([]);
  };

  const nombrePosicion = POSICIONES.find((p) => p.valor === posicion)?.texto ?? "";
  const selectorMesa = manifiesto !== null && (
    <SelectorMesa mesas={manifiesto.mesas} valor={mesaId} onCambio={setMesa} />
  );

  let resultados: ReactNode;
  if (datos.estado === "cargando" || datos.estado === "inactivo") {
    resultados = <p className="pista">Cargando datos…</p>;
  } else if (datos.estado === "error") {
    resultados = (
      <div className="bloque aviso" role="alert">
        <p>No se han podido cargar los datos: {datos.error}</p>
        <button type="button" className="boton" onClick={() => { setPromesaDatos(Datos.cargar(cargador)); }}>
          Reintentar
        </button>
      </div>
    );
  } else if (!completa) {
    resultados = (
      <p className="pista">
        {huboMus ? "Mete las 4 cartas que tienes después del mus." : "Mete tus 4 cartas con el teclado de abajo."}
      </p>
    );
  } else if (posicion === null || indice === null || manifiesto === null) {
    resultados = <p className="pista pista--destacada">¿En qué posición estás? Elígela arriba.</p>;
  } else if (!huboMus) {
    resultados = (
      <>
        <ConMesa mesa={mesa} que="la recomendación">
          {(m) => {
            const decision = decisionDe(m, manifiesto.escalas, indice, posicion);
            return decision === null
              ? <p className="pista">No hay recomendación para esta mano.</p>
              : <Decision vista={vistaDecision(decision)} posicion={nombrePosicion} selectorMesa={selectorMesa} />;
          }}
        </ConMesa>
        <ConMesa mesa={mesa} que="los descartes">
          {(m) => (
            <BloqueDescartes key={`${String(indice)}-${String(posicion)}-${mesaId}`} mesa={m}
              manifiesto={manifiesto} mano={mano} indice={indice} posicion={posicion} />
          )}
        </ConMesa>
        {avisoSenas !== null ? (
          <p className="pista">Corrige las señas para ver las probabilidades de ganar.</p>
        ) : miEquity === undefined || miEquity === null ? (
          <Estado recurso={equity} que="las probabilidades" />
        ) : (
          <Probabilidades
            titulo="Si se juega con estas cartas"
            subtitulo={
              <>
                Exacto, si alguien corta y se juega con las cartas del reparto.{" "}
                {resultadoSenas?.tipo === "tabla"
                  ? `Sabiendo que tu compañero tiene: ${nombresSenas(manifiesto, senas)}.`
                  : "Sin información de tu compañero."}
              </>
            }
            vista={vistaProbabilidades(miEquity, mano)}
          />
        )}
      </>
    );
  } else {
    resultados = (
      <ConMesa mesa={mesa} que="las probabilidades">
        {(m) => {
          const e = equityDe(m.tras_mus.datos, manifiesto.escalas, indice, posicion);
          return e === null ? null : (
            <Probabilidades
              titulo="Tras el mus"
              subtitulo={
                <>
                  Con las cartas que tienes después del mus, frente a lo que suelen llevar los
                  demás tras descartarse en una mesa «{manifiesto.mesas.find((x) => x.id === mesaId)?.nombre}».
                  Sin señas: todavía no se tienen en cuenta tras el mus.
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

  return (
    <div className="app" data-teclado={completa ? undefined : "si"}>
      <header className="cabecera">
        <h1>Mus Analytics</h1>
        <span className="cabecera__variante">Mus a 8 reyes</span>
      </header>

      <main>
        <section className="bloque mano" aria-labelledby="titulo-mano">
          <h2 className="bloque__titulo" id="titulo-mano">{huboMus ? "Tu mano después del mus" : "Tu mano"}</h2>
          <div className="mano__cartas">
            {[0, 1, 2, 3].map((i) => {
              const r = rangos(mano)[i];
              return r === undefined ? (
                <Carta key={i} rango={null} />
              ) : (
                <button key={i} type="button" className="mano__hueco" onClick={() => { quitarCarta(r); }}
                  aria-label={`Quitar carta ${String(i + 1)}`}>
                  <Carta rango={r} />
                </button>
              );
            })}
          </div>
          <p className="mano__jugada" aria-live="polite">
            {completa ? `${describirPares(mano)} · ${describirJuego(mano)}` : "El 3 cuenta como rey y el 2 como as. Toca una carta para quitarla."}
          </p>
          <Segmentado etiqueta="Posición" opciones={POSICIONES} valor={posicion} onCambio={setPosicion} />
          <Segmentado etiqueta="¿Ha habido mus?" pequeno valor={huboMus ? "si" : "no"}
            opciones={[{ valor: "no", texto: "No" }, { valor: "si", texto: "Sí" }]}
            onCambio={(v) => { cambiarMus(v === "si"); }} />
        </section>

        {manifiesto !== null && (
          <Senas senas={manifiesto.senas} marcadas={senas} onCambio={setSenas} desactivadas={huboMus}
            aviso={avisoSenas} />
        )}

        {resultados}

        <Limitaciones manifiesto={manifiesto} />
      </main>

      {completa ? (
        <div className="barra-inferior">
          {!huboMus && (
            <button type="button" className="boton boton--secundario" onClick={() => { cambiarMus(true); }}>
              Ha habido mus
            </button>
          )}
          <button type="button" className="boton" onClick={nuevaMano}>Nueva mano</button>
        </div>
      ) : (
        <Teclado cuantas={cartas.length} titulo={huboMus ? "Cartas después del mus" : "Tus cartas"}
          onCarta={ponerCarta} onBorrar={() => { setCartas((c) => c.slice(0, -1)); }}
          onNueva={nuevaMano} />
      )}
    </div>
  );
}

function nombresSenas(manifiesto: Manifiesto, ids: readonly string[]): string {
  return manifiesto.senas.filter((s) => ids.includes(s.id)).map((s) => s.nombre.toLowerCase()).join(" y ");
}

/** Mensaje de carga o de error de un recurso. */
function Estado<T>({ recurso, que }: { recurso: Recurso<T>; que: string }) {
  if (recurso.estado === "error") {
    return <p className="bloque aviso" role="alert">No se han podido cargar {que}: {recurso.error}</p>;
  }
  return <p className="pista">Calculando {que}…</p>;
}

/** Pinta su contenido cuando el fichero de la mesa está cargado. */
function ConMesa({ mesa, que, children }: {
  mesa: Recurso<FicheroMesa>;
  que: string;
  children: (mesa: FicheroMesa) => ReactNode;
}) {
  return mesa.estado === "listo" ? <>{children(mesa.valor)}</> : <Estado recurso={mesa} que={que} />;
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
