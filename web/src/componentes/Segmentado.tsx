import { useId } from "react";

export interface OpcionSegmentada<T> {
  readonly valor: T;
  readonly texto: string;
}

/** Grupo de botones de los que solo uno está activo (posición, tipo de mesa...). */
export function Segmentado<T extends string | number>({
  etiqueta,
  opciones,
  valor,
  onCambio,
  pequeno = false,
  etiquetaOculta = false,
  clase = "",
}: {
  etiqueta: string;
  opciones: readonly OpcionSegmentada<T>[];
  valor: T | null;
  onCambio: (valor: T) => void;
  pequeno?: boolean;
  /** La etiqueta solo para lectores de pantalla (cuando las opciones ya se explican solas). */
  etiquetaOculta?: boolean;
  /** Clases de más, para una variante de aspecto. */
  clase?: string;
}) {
  const id = useId();
  return (
    <div className={`segmentado${pequeno ? " segmentado--pequeno" : ""}${clase === "" ? "" : ` ${clase}`}`} role="group"
      aria-labelledby={id}>
      <span className={etiquetaOculta ? "solo-lector" : "segmentado__etiqueta"} id={id}>{etiqueta}</span>
      <div className="segmentado__opciones">
        {opciones.map((o) => (
          <button key={o.valor} type="button" className="segmentado__opcion"
            aria-pressed={o.valor === valor} onClick={() => { onCambio(o.valor); }}>
            {o.texto}
          </button>
        ))}
      </div>
    </div>
  );
}
