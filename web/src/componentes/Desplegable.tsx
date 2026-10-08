import { type ReactNode, useId, useState } from "react";

/** Un bloque que se abre y se cierra al tocar su título. */
export function Desplegable({
  titulo,
  resumen,
  children,
  abiertoInicial = false,
  clase = "",
}: {
  titulo: ReactNode;
  resumen?: ReactNode;
  children: ReactNode;
  abiertoInicial?: boolean;
  clase?: string;
}) {
  const [abierto, setAbierto] = useState(abiertoInicial);
  const id = useId();
  return (
    <div className={`desplegable ${clase}`}>
      <button type="button" className="desplegable__boton" aria-expanded={abierto}
        aria-controls={id} onClick={() => { setAbierto(!abierto); }}>
        <span className="desplegable__titulo">{titulo}</span>
        {resumen !== undefined && <span className="desplegable__resumen">{resumen}</span>}
        <span className="desplegable__flecha" aria-hidden="true">{abierto ? "▲" : "▼"}</span>
      </button>
      {abierto && <div className="desplegable__contenido" id={id}>{children}</div>}
    </div>
  );
}
