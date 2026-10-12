/**
 * El modo sin conexión, visto desde la página: registra el *service worker*
 * (`sw/sw.ts`) y sigue en qué estado está, para enseñarlo y para avisar cuando
 * hay una versión nueva.
 *
 * El *service worker* solo existe en contextos seguros (HTTPS o localhost).
 * Abierta por la red local (http://192.168…) no lo hay: la web funciona igual,
 * sin guardar nada. Por eso el contenedor llega por parámetro y puede faltar.
 */

import { type EstadoVersion } from "../sw/logica";

export type EstadoSinConexion =
  /** Sin *service worker*: desarrollo, red local por HTTP o navegador que no lo admite. */
  | { readonly tipo: "no-disponible" }
  /** Guardando la web por primera vez. */
  | { readonly tipo: "preparando" }
  /** Todo guardado: funciona sin conexión. `version` identifica lo guardado. */
  | { readonly tipo: "lista"; readonly version: string }
  /** Hay una versión nueva ya descargada, esperando a que se le dé paso. */
  | { readonly tipo: "nueva"; readonly version: string | null }
  /** No se ha podido guardar (p. ej. se cortó la descarga la primera vez). */
  | { readonly tipo: "error" };

export interface SinConexion {
  readonly estado: () => EstadoSinConexion;
  /** Avisa de cada cambio de estado; devuelve cómo dejar de escuchar. */
  readonly suscribir: (avisar: () => void) => () => void;
  /** Pasa a la versión nueva y recarga la página. Solo hace algo en el estado "nueva". */
  readonly actualizar: () => void;
}

/** Lo mínimo de `document` que hace falta para saber cuándo se vuelve a la web. */
export interface Visibilidad {
  readonly visibilityState: string;
  addEventListener(tipo: "visibilitychange", oyente: () => void): void;
}

export interface Opciones {
  /** Dirección de `sw.js`. */
  readonly url: string;
  readonly recargar: () => void;
  readonly documento?: Visibilidad;
  readonly ahora?: () => number;
}

/** Como mucho, una comprobación de versión nueva por minuto al volver a la web. */
const PAUSA_COMPROBACION_MS = 60_000;

const NO_DISPONIBLE: EstadoSinConexion = { tipo: "no-disponible" };

/** Para cuando no hay modo sin conexión (y para los tests de la interfaz). */
export const SIN_SERVICE_WORKER: SinConexion = {
  estado: () => NO_DISPONIBLE,
  suscribir: () => () => undefined,
  actualizar: () => undefined,
};

function preguntarEstado(sw: ServiceWorker): Promise<EstadoVersion> {
  return new Promise((resolver) => {
    const canal = new MessageChannel();
    canal.port1.onmessage = (evento) => {
      canal.port1.close();
      resolver(evento.data as EstadoVersion);
    };
    sw.postMessage({ tipo: "estado" }, [canal.port2]);
  });
}

export function crearSinConexion(contenedor: ServiceWorkerContainer | undefined, opciones: Opciones): SinConexion {
  if (contenedor === undefined) return SIN_SERVICE_WORKER;
  const ahora = opciones.ahora ?? Date.now;

  let estado: EstadoSinConexion = { tipo: "preparando" };
  const oyentes = new Set<() => void>();
  const poner = (nuevo: EstadoSinConexion): void => {
    estado = nuevo;
    for (const avisar of oyentes) avisar();
  };

  let registro: ServiceWorkerRegistration | null = null;
  let versionEnUso: string | null = null;
  let recargando = false;
  // Si al abrir ya mandaba un service worker, un cambio de mando es el paso a una
  // versión nueva y hay que recargar para usar su código. La primera vez no: la
  // página ya es la buena y solo empieza a servirse de la caché.
  const habiaVersion = contenedor.controller !== null;

  const preguntar = async (): Promise<void> => {
    // Tras una recarga forzada la página no tiene quien la mande, pero lo guardado sigue ahí.
    const sw = contenedor.controller ?? registro?.active ?? null;
    if (sw === null) return; // aún se está instalando por primera vez
    const respuesta = await preguntarEstado(sw);
    if (estado.tipo === "nueva") return; // llegó una versión nueva mientras se preguntaba
    versionEnUso = respuesta.version;
    poner(respuesta.completa ? { tipo: "lista", version: respuesta.version } : { tipo: "error" });
  };

  const darPaso = (): void => {
    registro?.waiting?.postMessage({ tipo: "activar" });
  };

  /** Sigue la instalación de un service worker recién encontrado. */
  const vigilar = (): void => {
    const nuevo = registro?.installing ?? null;
    if (nuevo === null) return;
    nuevo.addEventListener("statechange", () => {
      if (nuevo.state === "installed" && contenedor.controller !== null) {
        // Descargada entera. La versión en uso sigue hasta que se le dé paso.
        poner({ tipo: "nueva", version: versionEnUso });
      } else if (nuevo.state === "redundant" && contenedor.controller === null) {
        // Falló la primera instalación. Si falla una actualización no pasa nada:
        // la versión en uso sigue entera y se reintentará.
        poner({ tipo: "error" });
      }
    });
  };

  contenedor.addEventListener("controllerchange", () => {
    if (!habiaVersion) {
      void preguntar();
    } else if (!recargando) {
      recargando = true;
      opciones.recargar();
    }
  });

  // updateViaCache "none": `sw.js` se pide siempre a la red, sin caché HTTP.
  contenedor.register(opciones.url, { updateViaCache: "none" }).then((r) => {
    registro = r;
    if (r.waiting !== null && contenedor.controller !== null) {
      // Al abrir ya había una versión nueva esperando: se le da paso sin
      // preguntar, porque todavía no hay ninguna mano a medias.
      darPaso();
      return;
    }
    r.addEventListener("updatefound", vigilar);
    vigilar();
    void preguntar();
  }, () => {
    poner({ tipo: "error" });
  });

  // Las webs instaladas en el móvil no se recargan al volver a ellas: se quedan
  // dormidas. Al despertar, se mira si hay una versión nueva.
  let ultima = ahora();
  opciones.documento?.addEventListener("visibilitychange", () => {
    if (opciones.documento?.visibilityState !== "visible" || registro === null) return;
    if (ahora() - ultima < PAUSA_COMPROBACION_MS) return;
    ultima = ahora();
    registro.update().catch(() => undefined); // sin cobertura: ya se mirará
  });

  return {
    estado: () => estado,
    suscribir: (avisar) => {
      oyentes.add(avisar);
      return () => {
        oyentes.delete(avisar);
      };
    },
    actualizar: () => {
      if (estado.tipo === "nueva") darPaso();
    },
  };
}
