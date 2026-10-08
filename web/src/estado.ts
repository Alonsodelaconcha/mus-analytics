/**
 * Hooks de React para los datos asíncronos y las preferencias guardadas.
 */

import { useEffect, useState } from "react";

export type Recurso<T> =
  | { readonly estado: "inactivo" }
  | { readonly estado: "cargando" }
  | { readonly estado: "listo"; readonly valor: T }
  | { readonly estado: "error"; readonly error: string };

type Resultado<T> =
  | { readonly promesa: Promise<T>; readonly estado: "listo"; readonly valor: T }
  | { readonly promesa: Promise<T>; readonly estado: "error"; readonly error: string };

/**
 * Estado de una promesa. Se guarda junto con la promesa de la que viene, así
 * que si la promesa cambia (otra mesa, otras señas) se vuelve a "cargando" y
 * nunca se enseña un resultado de la anterior.
 */
export function usePromesa<T>(promesa: Promise<T> | null): Recurso<T> {
  const [resultado, setResultado] = useState<Resultado<T> | null>(null);
  useEffect(() => {
    if (promesa === null) return;
    let vigente = true;
    promesa.then(
      (valor) => {
        if (vigente) setResultado({ promesa, estado: "listo", valor });
      },
      (error: unknown) => {
        if (vigente) setResultado({ promesa, estado: "error", error: mensaje(error) });
      },
    );
    return () => {
      vigente = false;
    };
  }, [promesa]);
  if (promesa === null) return { estado: "inactivo" };
  if (resultado?.promesa !== promesa) return { estado: "cargando" };
  return resultado.estado === "listo"
    ? { estado: "listo", valor: resultado.valor }
    : { estado: "error", error: resultado.error };
}

export function mensaje(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Una preferencia que se recuerda en este móvil (p. ej. el tipo de mesa). Si
 * el navegador no deja guardar (modo privado), funciona igual sin recordar.
 */
export function usePreferencia<T extends string>(
  clave: string,
  inicial: T,
  valida: (v: string) => v is T,
): [T, (v: T) => void] {
  const [valor, setValor] = useState<T>(() => {
    try {
      const guardado = localStorage.getItem(clave);
      return guardado !== null && valida(guardado) ? guardado : inicial;
    } catch {
      return inicial;
    }
  });
  const cambiar = (v: T): void => {
    setValor(v);
    try {
      localStorage.setItem(clave, v);
    } catch {
      // Sin almacenamiento: la preferencia dura hasta cerrar la página.
    }
  };
  return [valor, cambiar];
}
