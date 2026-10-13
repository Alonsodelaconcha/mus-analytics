import { useReducer, useRef, useState, useSyncExternalStore } from "react";

import { Calculadora } from "./Calculadora";
import { Creditos } from "./componentes/Creditos";
import { Limitaciones } from "./componentes/Limitaciones";
import { Segmentado } from "./componentes/Segmentado";
import { Entrenador } from "./Entrenador";
import {
  ALMACEN_LOCAL,
  type Almacen,
  type Anotacion,
  type Persistencia,
  anotar,
  leerProgreso,
  pedirPersistencia,
} from "./entrenador/progreso";
import { SERIE_INICIAL, reducirSerie } from "./entrenador/serie";
import { type Azar } from "./entrenador/situaciones";
import { usePreferencia, usePromesa } from "./estado";
import { ESTADO_INICIAL, cartasDe, reducirMano } from "./mano";
import { type Cargador, Datos } from "./nucleo/datos";
import { SIN_SERVICE_WORKER, type SinConexion } from "./sinConexion";

const MODOS_WEB = [
  { valor: "calculadora", texto: "Calculadora" },
  { valor: "entrenador", texto: "Entrenador" },
] as const;
type ModoWeb = (typeof MODOS_WEB)[number]["valor"];

const esTexto = (v: string): v is string => v.length > 0;
const esModoWeb = (v: string): v is ModoWeb => MODOS_WEB.some((m) => m.valor === v);

/**
 * La web: la cabecera, con el modo, y debajo la calculadora o el entrenador.
 *
 * Aquí vive lo que tiene que seguir ahí al cambiar de modo: los datos
 * cargados, la mano que se está metiendo en la calculadora, la serie del
 * entrenador, el tipo de mesa (el mismo en los dos) y el registro de
 * respuestas, que se guarda en el móvil.
 */
export function App({
  cargador,
  sinConexion = SIN_SERVICE_WORKER,
  almacen = ALMACEN_LOCAL,
  azar = Math.random,
  ahora = Date.now,
  persistir = pedirPersistencia,
}: {
  cargador: Cargador;
  sinConexion?: SinConexion;
  /** Dónde se guarda el progreso del entrenador. */
  almacen?: Almacen;
  /** El azar con que se sortean las manos: solo los tests pasan uno con semilla. */
  azar?: Azar;
  ahora?: () => number;
  /** Pide al navegador que no borre lo guardado. */
  persistir?: () => Promise<Persistencia>;
}) {
  const guardado = useSyncExternalStore(sinConexion.suscribir, sinConexion.estado);

  // Reintentar (p. ej. al volver la cobertura) crea una carga nueva.
  const [promesaDatos, setPromesaDatos] = useState(() => Datos.cargar(cargador));
  const datos = usePromesa(promesaDatos);
  const reintentar = (): void => {
    setPromesaDatos(Datos.cargar(cargador));
  };

  const [modo, setModo] = usePreferencia<ModoWeb>("mus-analytics.modo", "calculadora", esModoWeb);
  // Todas las reglas de la mano (pestañas, giro de la posición...) están en mano.ts;
  // las de una serie del entrenador, en entrenador/serie.ts.
  const [mano, despacharMano] = useReducer(reducirMano, ESTADO_INICIAL);
  const [serie, despacharSerie] = useReducer(reducirSerie, SERIE_INICIAL);
  const [mesaGuardada, setMesa] = usePreferencia("mus-analytics.mesa", "normal", esTexto);

  const manifiesto = datos.estado === "listo" ? datos.valor.manifiesto : null;
  const mesaId = manifiesto?.mesas.some((m) => m.id === mesaGuardada) === true
    ? mesaGuardada
    : (manifiesto?.mesas.find((m) => m.por_defecto)?.id ?? mesaGuardada);
  const nombreMesa = manifiesto?.mesas.find((m) => m.id === mesaId)?.nombre ?? "";

  // El registro de respuestas se lee una vez; cada respuesta nueva se guarda al momento.
  const [registro, setRegistro] = useState(() => leerProgreso(almacen));
  const [sinGuardar, setSinGuardar] = useState(false);
  const persistenciaPedida = useRef(false);
  const anotarRespuesta = (anotacion: Anotacion): void => {
    const resultado = anotar(almacen, registro, anotacion);
    setRegistro(resultado.anotaciones);
    setSinGuardar(!resultado.guardado);
    // Con la primera respuesta ya hay algo que conservar: se pide al navegador que no lo borre.
    if (!persistenciaPedida.current) {
      persistenciaPedida.current = true;
      void persistir();
    }
  };

  const cambiarModo = (m: ModoWeb): void => {
    setModo(m);
    if (window.scrollY > 0) window.scrollTo({ top: 0 });
  };

  const avisoVersion = guardado.tipo === "nueva" && (
    <div className="aviso aviso--version" role="status">
      <p>
        Hay una versión nueva. Al actualizar se empieza una mano nueva
        {serie.fase === "serie" ? " y se deja la serie del entrenador" : ""}.
      </p>
      <button type="button" className="boton" onClick={sinConexion.actualizar}>Actualizar</button>
    </div>
  );
  const pieDePagina = (
    <>
      <Limitaciones manifiesto={manifiesto} />
      <Creditos guardado={guardado} datos={manifiesto?.generado ?? null} />
    </>
  );

  const pie = modo === "entrenador" ? "entrenador" : cartasDe(mano).length === 4 ? "corto" : "teclado";
  return (
    <div className="app" data-pie={pie}>
      <header className="cabecera">
        <div className="cabecera__titulo">
          <h1>Mus Analytics</h1>
          <span className="cabecera__variante">Mus a 8 reyes</span>
        </div>
        <Segmentado etiqueta="Modo" etiquetaOculta pequeno clase="segmentado--cabecera"
          opciones={MODOS_WEB} valor={modo} onCambio={cambiarModo} />
      </header>

      {modo === "entrenador" ? (
        <Entrenador datos={datos} onReintentar={reintentar} serie={serie} despachar={despacharSerie}
          mesaId={mesaId} onMesa={setMesa} registro={registro} sinGuardar={sinGuardar}
          onAnotar={anotarRespuesta} azar={azar} ahora={ahora} avisoVersion={avisoVersion}
          pieDePagina={pieDePagina} />
      ) : (
        <Calculadora datos={datos} onReintentar={reintentar} estado={mano} despachar={despacharMano}
          mesaId={mesaId} nombreMesa={nombreMesa} onMesa={setMesa} avisoVersion={avisoVersion}
          pieDePagina={pieDePagina} />
      )}
    </div>
  );
}
