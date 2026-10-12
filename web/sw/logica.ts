/**
 * Lógica del *service worker*, sin tocar `self`: recibe por parámetro la caché,
 * la red y la función de huella, para poder probarla con dobles
 * (`test/sw.test.ts`).
 *
 * La idea: cada versión publicada de la web es un conjunto cerrado de ficheros
 * con su huella SHA-256 (la `Precarga`, que escribe `plugins/sinConexion.ts`
 * al construir). Una versión se descarga **entera** a su propia caché o no se
 * instala; mientras tanto sigue sirviendo la anterior, también entera. Así
 * nunca se mezclan el código de una versión y los datos de otra.
 */

export interface FicheroPrecarga {
  /** Ruta relativa a la carpeta de la web, p. ej. `datos/manifiesto.json`. */
  readonly ruta: string;
  readonly sha256: string;
}

export interface Precarga {
  /** Identificador de la versión: huella de la lista de ficheros. */
  readonly version: string;
  readonly ficheros: readonly FicheroPrecarga[];
}

export interface Entorno {
  /** Dirección de la carpeta de la web, acabada en "/". */
  readonly base: string;
  readonly caches: CacheStorage;
  readonly fetch: (url: string, opciones: RequestInit) => Promise<Response>;
  readonly sha256: (contenido: ArrayBuffer) => Promise<string>;
}

/** Todas las cachés de la web empiezan así; lo demás del origen no se toca. */
export const PREFIJO_CACHE = "mus-analytics-";

export function nombreCache(version: string): string {
  return `${PREFIJO_CACHE}${version}`;
}

function direccion(e: Entorno, ruta: string): string {
  return new URL(ruta, e.base).href;
}

/**
 * Descarga la versión entera a su caché. Todo o nada: si un fichero no llega,
 * llega a medias o no coincide con su huella, la caché se borra y la
 * instalación falla. El navegador descarta entonces este *service worker* y
 * la versión anterior sigue como estaba; se reintenta en la próxima comprobación.
 */
export async function instalar(p: Precarga, e: Entorno): Promise<void> {
  const nombre = nombreCache(p.version);
  await e.caches.delete(nombre); // restos de un intento anterior
  const cache = await e.caches.open(nombre);
  const resultados = await Promise.allSettled(p.ficheros.map(async (f) => {
    const url = direccion(e, f.ruta);
    // "no-store": ni la caché HTTP del navegador ni una copia vieja de un intento anterior.
    const respuesta = await e.fetch(url, { cache: "no-store" });
    if (!respuesta.ok) {
      throw new Error(`${f.ruta}: error ${String(respuesta.status)}`);
    }
    const contenido = await respuesta.arrayBuffer();
    if ((await e.sha256(contenido)) !== f.sha256) {
      throw new Error(`${f.ruta}: no coincide con su huella`);
    }
    // Una respuesta nueva, solo con el contenido comprobado y su tipo.
    const tipo = respuesta.headers.get("content-type");
    await cache.put(url, new Response(contenido, tipo === null ? {} : { headers: { "content-type": tipo } }));
  }));
  const fallo = resultados.find((r) => r.status === "rejected");
  if (fallo !== undefined) {
    await e.caches.delete(nombre);
    throw fallo.reason instanceof Error ? fallo.reason : new Error(String(fallo.reason));
  }
}

/** Al tomar el mando: borra las cachés de las versiones anteriores. */
export async function activar(p: Precarga, e: Entorno): Promise<void> {
  const actual = nombreCache(p.version);
  for (const nombre of await e.caches.keys()) {
    if (nombre.startsWith(PREFIJO_CACHE) && nombre !== actual) {
      await e.caches.delete(nombre);
    }
  }
}

/** Si la caché de la versión tiene todos sus ficheros. */
export async function estaCompleta(p: Precarga, e: Entorno): Promise<boolean> {
  if (!(await e.caches.has(nombreCache(p.version)))) return false;
  const cache = await e.caches.open(nombreCache(p.version));
  const guardadas = new Set((await cache.keys()).map((peticion) => peticion.url));
  return p.ficheros.every((f) => guardadas.has(direccion(e, f.ruta)));
}

/**
 * Qué fichero de la versión responde a una petición, o `null` si no es cosa
 * del *service worker* (otra web, otro método, un fichero que no es de esta
 * versión) y debe seguir su camino a la red. La carpeta sola es `index.html`.
 */
export function rutaDe(p: Precarga, base: string, metodo: string, url: string): string | null {
  if (metodo !== "GET") return null;
  const pedida = new URL(url);
  const raiz = new URL(base);
  if (pedida.origin !== raiz.origin || !pedida.pathname.startsWith(raiz.pathname)) return null;
  const resto = pedida.pathname.slice(raiz.pathname.length);
  const ruta = resto === "" ? "index.html" : resto;
  return p.ficheros.some((f) => f.ruta === ruta) ? ruta : null;
}

/** El fichero guardado, o `undefined` si falta (el navegador puede vaciar la caché). */
export async function servir(p: Precarga, e: Entorno, ruta: string): Promise<Response | undefined> {
  const cache = await e.caches.open(nombreCache(p.version));
  return cache.match(direccion(e, ruta));
}

/** Lo que el *service worker* contesta a la página cuando le pregunta cómo está. */
export interface EstadoVersion {
  readonly version: string;
  readonly completa: boolean;
}

/** Como `estaCompleta`, pero si falta algo (caché vaciada) intenta guardarlo de nuevo. */
export async function estado(p: Precarga, e: Entorno): Promise<EstadoVersion> {
  let completa = await estaCompleta(p, e);
  if (!completa) {
    completa = await instalar(p, e).then(() => true, () => false);
  }
  return { version: p.version, completa };
}
