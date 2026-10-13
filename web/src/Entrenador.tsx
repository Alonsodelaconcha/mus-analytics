import { type ReactNode, useMemo } from "react";

import { Carta } from "./componentes/Carta";
import { DatosSinCargar, Estado } from "./componentes/Carga";
import { SelectorMesa } from "./componentes/Decision";
import { Desplegable } from "./componentes/Desplegable";
import { PorLance } from "./componentes/PorLance";
import { Segmentado } from "./componentes/Segmentado";
import { type Anotacion, type Resumen, resumir } from "./entrenador/progreso";
import {
  type AccionSerie,
  type Contestada,
  type EstadoSerie,
  SITUACIONES_POR_SERIE,
  contestadaActual,
  situacionActual,
} from "./entrenador/serie";
import {
  type Azar,
  MODOS,
  type Modo,
  type Situacion,
  decisionesPorMano,
  pesos,
  situacionDe,
  sortear,
} from "./entrenador/situaciones";
import { MILESIMAS, type RespuestaCorte, valorarCorte } from "./entrenador/valoracion";
import { type Recurso, usePreferencia, usePromesa } from "./estado";
import { rangos } from "./nucleo/cartas";
import { type Datos, type DecisionMus, type FicheroMesa, type Manifiesto, decisionDe } from "./nucleo/datos";
import { tabla } from "./nucleo/tablas";
import {
  NOMBRE_MODO,
  contexto,
  fraseDecisionesPorMano,
  fraseSituacion,
  vistaPorLance,
  vistaRespuesta,
  vistaResumen,
} from "./vista/entrenador";
import { conSigno, decimal, describirMano, frecuencia, porcentaje } from "./vista/lenguaje";

const esModo = (v: string): v is Modo => (MODOS as readonly string[]).includes(v);
const POSICION = ["mano", "segundo", "tercero", "postre"] as const;
const RESPUESTA: Readonly<Record<RespuestaCorte, string>> = { mus: "mus", corta: "corto" };

/**
 * El entrenador de «¿Mus o corto?». Plantea una mano en una posición, se
 * responde con los dos botones de abajo y enseña cuántos tantos se pierden
 * frente a la mejor jugada y por qué, lance a lance. Las manos van en series;
 * al final de cada una, el resumen.
 *
 * No calcula nada del juego: la valoración sale de los mismos datos y las
 * mismas funciones que la calculadora. La serie vive en `App` (`serie`), para
 * que siga ahí al volver de la calculadora.
 */
export function Entrenador({
  datos,
  onReintentar,
  serie,
  despachar,
  mesaId,
  onMesa,
  registro,
  sinGuardar,
  onAnotar,
  azar,
  ahora,
  avisoVersion,
  pieDePagina,
}: {
  datos: Recurso<Datos>;
  onReintentar: () => void;
  serie: EstadoSerie;
  despachar: (accion: AccionSerie) => void;
  /** Tipo de mesa elegido (el mismo que en la calculadora). */
  mesaId: string;
  onMesa: (id: string) => void;
  /** Todas las respuestas anotadas en este móvil. */
  registro: readonly Anotacion[];
  /** La última respuesta no se ha podido guardar. */
  sinGuardar: boolean;
  onAnotar: (anotacion: Anotacion) => void;
  azar: Azar;
  ahora: () => number;
  avisoVersion: ReactNode;
  pieDePagina: ReactNode;
}) {
  const d = datos.estado === "listo" ? datos.valor : null;
  // Una serie se juega entera en la mesa con que empezó.
  const mesaDeLaSerie = serie.fase === "serie"
    ? serie.situaciones[0]?.mesa
    : serie.fase === "resumen" ? serie.contestadas[0]?.situacion.mesa : undefined;
  const idMesa = mesaDeLaSerie ?? mesaId;
  const promesaMesa = useMemo(() => (d !== null ? d.mesa(idMesa) : null), [d, idMesa]);
  const mesa = usePromesa(promesaMesa);

  if (d !== null && mesa.estado === "listo") {
    return (
      <EntrenadorListo manifiesto={d.manifiesto} mesa={mesa.valor} idMesa={idMesa} serie={serie}
        despachar={despachar} onMesa={onMesa} registro={registro} sinGuardar={sinGuardar}
        onAnotar={onAnotar} azar={azar} ahora={ahora} avisoVersion={avisoVersion}
        pieDePagina={pieDePagina} />
    );
  }
  return (
    <main>
      {avisoVersion}
      {datos.estado === "error"
        ? <DatosSinCargar error={datos.error} onReintentar={onReintentar} />
        : d === null
          ? <p className="pista">Cargando datos…</p>
          : <Estado recurso={mesa} que="las manos del entrenador" plural />}
      {pieDePagina}
    </main>
  );
}

function EntrenadorListo({
  manifiesto,
  mesa,
  idMesa,
  serie,
  despachar,
  onMesa,
  registro,
  sinGuardar,
  onAnotar,
  azar,
  ahora,
  avisoVersion,
  pieDePagina,
}: {
  manifiesto: Manifiesto;
  mesa: FicheroMesa;
  idMesa: string;
  serie: EstadoSerie;
  despachar: (accion: AccionSerie) => void;
  onMesa: (id: string) => void;
  registro: readonly Anotacion[];
  sinGuardar: boolean;
  onAnotar: (anotacion: Anotacion) => void;
  azar: Azar;
  ahora: () => number;
  avisoVersion: ReactNode;
  pieDePagina: ReactNode;
}) {
  const [modo, setModo] = usePreferencia<Modo>("mus-analytics.entrenador.modo", "mesa", esModo);
  const nombreMesa = manifiesto.mesas.find((m) => m.id === idMesa)?.nombre ?? "";
  const pesosMesa = useMemo(() => pesos("corte", "mesa", mesa, manifiesto), [mesa, manifiesto]);
  const porMano = decisionesPorMano("corte", pesosMesa, manifiesto.escalas);

  const subir = (): void => {
    if (window.scrollY > 0) window.scrollTo({ top: 0 });
  };
  const empezar = (): void => {
    const disponibles = modo === "mesa" ? pesosMesa : pesos("corte", modo, mesa, manifiesto);
    const numeros = sortear(disponibles, SITUACIONES_POR_SERIE, azar);
    despachar({ tipo: "empezar", modo, situaciones: numeros.map((k) => situacionDe(k, "corte", idMesa)) });
    subir();
  };
  const situacion = situacionActual(serie);
  // Tras el primer toque, React vuelve a pintar antes de atender el siguiente y los
  // botones de respuesta ya no están: un segundo toque no puede anotar otra respuesta.
  const responder = (respuesta: RespuestaCorte): void => {
    if (serie.fase !== "serie" || serie.valorando || situacion === null) return;
    const decision = decisionDe(mesa, manifiesto.escalas, situacion.indice, situacion.posicion);
    if (decision === null) return;
    const valoracion = valorarCorte(decision);
    despachar({ tipo: "responder", respuesta, valoracion });
    onAnotar({
      fecha: ahora(),
      ejercicio: "corte",
      modo: serie.modo,
      mesa: situacion.mesa,
      mano: tabla().textos[situacion.indice] ?? "",
      posicion: situacion.posicion,
      respuesta,
      mejor: valoracion.veredicto,
      intensidad: valoracion.intensidad,
      perdidos: valoracion.perdidos[respuesta],
      datos: manifiesto.generado,
      web: __VERSION_WEB__,
    });
  };
  const siguiente = (): void => {
    despachar({ tipo: "siguiente" });
    subir();
  };
  const salir = (): void => {
    despachar({ tipo: "salir" });
    subir();
  };

  const avisoGuardado = sinGuardar && (
    <p className="aviso" role="status">
      No se ha podido guardar el progreso en este móvil: se perderá al cerrar la web.
    </p>
  );
  // Lo anotado en esta mesa con las manos «como en la mesa», que es lo que se parece a una partida.
  const acumulado = resumir(registro.filter((a) => a.ejercicio === "corte" && a.mesa === idMesa && a.modo === "mesa"));
  const progreso = acumulado.n > 0 && (
    <section className="bloque" aria-labelledby="titulo-progreso">
      <h2 className="bloque__titulo" id="titulo-progreso">
        Tu progreso <span className="bloque__contexto">Mesa {nombreMesa.toLowerCase()}, como en la mesa</span>
      </h2>
      <LineasResumen vista={vistaResumen(acumulado, porMano)} />
    </section>
  );

  let contenido: ReactNode;
  let acciones: ReactNode;
  if (serie.fase === "inicio") {
    contenido = (
      <>
        <section className="bloque" aria-labelledby="titulo-entrenador">
          <h2 className="bloque__titulo" id="titulo-entrenador">Entrenador: ¿mus o corto?</h2>
          <p className="entrenador__entrada">
            Te sale una mano y una posición, y decides si cortas o das mus. Cada respuesta se valora
            por los tantos que pierdes frente a la mejor jugada: si la diferencia no se distingue,
            cualquiera vale.
          </p>
          <SelectorMesa mesas={manifiesto.mesas} valor={idMesa} onCambio={onMesa} />
          <Segmentado etiqueta="Qué manos salen" pequeno valor={modo} onCambio={setModo}
            opciones={MODOS.map((m) => ({ valor: m, texto: NOMBRE_MODO[m].corto }))} />
          <p className="nota">{NOMBRE_MODO[modo].descripcion}</p>
          <p className="nota entrenador__contexto">{contexto(nombreMesa)}</p>
        </section>
        {progreso}
      </>
    );
    acciones = (
      <button type="button" className="boton" onClick={empezar}>
        Empezar: {SITUACIONES_POR_SERIE} manos
      </button>
    );
  } else if (serie.fase === "serie" && situacion !== null) {
    const contestada = contestadaActual(serie);
    const decision = decisionDe(mesa, manifiesto.escalas, situacion.indice, situacion.posicion);
    const ultima = serie.contestadas.length >= serie.situaciones.length;
    contenido = (
      <>
        <BloqueSituacion situacion={situacion} nombreMesa={nombreMesa} respondida={contestada !== null}
          numero={serie.contestadas.length + (serie.valorando ? 0 : 1)} total={serie.situaciones.length}
          onSalir={salir} />
        {contestada !== null && decision !== null && (
          <BloqueValoracion contestada={contestada} decision={decision} nombreMesa={nombreMesa} />
        )}
        {avisoGuardado}
      </>
    );
    acciones = contestada === null ? (
      <>
        <button type="button" className="boton boton--corta" onClick={() => { responder("corta"); }}>Corto</button>
        <button type="button" className="boton boton--mus" onClick={() => { responder("mus"); }}>Mus</button>
      </>
    ) : (
      <button type="button" className="boton" onClick={siguiente}>
        {ultima ? "Ver el resumen" : "Siguiente"}
      </button>
    );
  } else if (serie.fase === "resumen") {
    contenido = (
      <>
        <section className="bloque" aria-labelledby="titulo-resumen">
          <h2 className="bloque__titulo" id="titulo-resumen">
            Serie terminada <span className="bloque__contexto">Mesa {nombreMesa.toLowerCase()}</span>
          </h2>
          <LineasResumen
            vista={vistaResumen(resumirSerie(serie.contestadas), serie.modo === "mesa" ? porMano : null)} />
          {serie.modo === "mesa" && <p className="nota">{fraseDecisionesPorMano(nombreMesa, porMano)}</p>}
          <ol className="resumen__lista">
            {serie.contestadas.map((c, i) => <FilaResumen key={i} contestada={c} />)}
          </ol>
        </section>
        {progreso}
        {avisoGuardado}
      </>
    );
    acciones = (
      <>
        <button type="button" className="boton boton--secundario" onClick={salir}>Inicio</button>
        <button type="button" className="boton" onClick={empezar}>Otra serie</button>
      </>
    );
  } else {
    contenido = null;
    acciones = null;
  }

  return (
    <>
      <main>
        {avisoVersion}
        {contenido}
        {pieDePagina}
      </main>
      <div className="pie">
        <div className="pie__acciones pie__acciones--entrenador">{acciones}</div>
      </div>
    </>
  );
}

/** Las cifras de una serie, a partir de lo contestado. */
function resumirSerie(contestadas: readonly Contestada[]): Resumen {
  return resumir(contestadas.map((c) => ({
    perdidos: c.valoracion.perdidos[c.respuesta],
    intensidad: c.valoracion.intensidad,
  })));
}

function LineasResumen({ vista }: { vista: ReturnType<typeof vistaResumen> }) {
  return (
    <>
      <p className="resumen__total">{vista.total}</p>
      <p className="nota">{vista.desglose}</p>
      {vista.ritmo !== "" && <p className="resumen__ritmo">{vista.ritmo}</p>}
    </>
  );
}

/**
 * La mano, la posición y contra qué se juega: lo que se sabe antes de responder.
 * Una vez respondida, las cartas se encogen y el contra qué pasa al bloque de la
 * valoración, que es donde se lee: así la valoración cabe en la pantalla del móvil.
 */
function BloqueSituacion({ situacion, nombreMesa, respondida, numero, total, onSalir }: {
  situacion: Situacion;
  nombreMesa: string;
  respondida: boolean;
  numero: number;
  total: number;
  onSalir: () => void;
}) {
  const mano = tabla().manos[situacion.indice] ?? [];
  return (
    <section className="bloque situacion" data-respondida={respondida ? "si" : undefined}
      aria-labelledby="titulo-situacion">
      <div className="situacion__cabecera">
        <h2 className="bloque__titulo" id="titulo-situacion">
          ¿Mus o corto? <span className="bloque__contexto">Mano {numero} de {total}</span>
        </h2>
        <button type="button" className="boton--enlace situacion__salir" onClick={onSalir}>Dejar la serie</button>
      </div>
      <div className="situacion__cartas">
        {rangos(mano).map((r, i) => <Carta key={i} rango={r} pequena={respondida} />)}
      </div>
      <p className="situacion__jugada">{describirMano(mano).join(" · ")}</p>
      <p className="situacion__posicion">{fraseSituacion(situacion.posicion)}</p>
      {!respondida && <p className="nota situacion__contexto">{contexto(nombreMesa)}</p>}
    </section>
  );
}

/** Lo que valía la respuesta y por qué. */
function BloqueValoracion({ contestada, decision, nombreMesa }: {
  contestada: Contestada;
  decision: DecisionMus;
  nombreMesa: string;
}) {
  const vista = vistaRespuesta(decision, contestada.valoracion, contestada.respuesta);
  const posicion = contestada.situacion.posicion;
  return (
    <section className="bloque valoracion" data-resultado={vista.resultado} aria-labelledby="titulo-valoracion"
      aria-live="polite">
      <p className="valoracion__respuesta">Has respondido: {RESPUESTA[contestada.respuesta]}</p>
      <h2 className="valoracion__titulo" id="titulo-valoracion">{vista.titulo}</h2>
      <p className="valoracion__detalle">{vista.detalle}</p>
      {vista.matiz !== "" && <p className="decision__matiz">{vista.matiz}</p>}
      <PorLance vista={vistaPorLance(decision)} />
      <p className="nota valoracion__contexto">{contexto(nombreMesa)}</p>
      <Desplegable titulo="Más detalle" clase="desplegable--discreto">
        <ul className="detalle">
          <li>
            Dar mus menos cortar: {conSigno(decision.ventaja)} tantos por mano
            (margen de error ±{decimal(decision.radio)}).
          </li>
          {posicion > 1 && (
            <li>Con esta mano, te toca hablar de {POSICION[posicion - 1]} {frecuencia(decision.pHabla)}.</li>
          )}
          <li>
            Si das mus, los que hablan después también lo dan {porcentaje(decision.pMusDespues)} de
            las veces; si alguno corta, se juega con las cartas del reparto.
          </li>
          <li>
            Calculado simulando {decision.repartos.toLocaleString("es-ES")} repartos con estas cartas,
            en los que cada uno corta o se descarta según el tipo de mesa.
          </li>
        </ul>
      </Desplegable>
    </section>
  );
}

function FilaResumen({ contestada }: { contestada: Contestada }) {
  const { situacion, respuesta, valoracion } = contestada;
  const perdidos = valoracion.perdidos[respuesta];
  return (
    <li className="resumen__fila" data-resultado={perdidos > 0 ? "fallo" : "bien"}>
      <span className="resumen__mano">{tabla().textos[situacion.indice]}</span>
      <span className="resumen__posicion">{POSICION[situacion.posicion - 1]} · {RESPUESTA[respuesta]}</span>
      <span className="resumen__resultado">
        {perdidos > 0 ? `−${decimal(perdidos / MILESIMAS)}` : valoracion.veredicto === "igual" ? "daba igual" : "bien"}
      </span>
    </li>
  );
}
