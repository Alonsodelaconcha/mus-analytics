"""Interfaz de línea de comandos: ``python -m mus <comando> ...``.

Ejemplos::

    python -m mus evaluar "R R C 5"
    python -m mus resolver "R R C 5" "7 7 7 S" "A A 4 5" "C C S S"
    python -m mus distribucion
    python -m mus verificar --n 1000000 --semilla 42 --csv resultados/verificacion.csv
    python -m mus tabla --csv resultados/manos.csv
    python -m mus grafica --salida resultados/distribucion.png
    python -m mus --variante 4reyes distribucion
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence

from mus.analisis import (
    comparar_exacto_mc,
    comparativa_mano,
    distribucion_exacta,
    distribucion_sumas,
    exportar_comparacion_csv,
    exportar_tabla_csv,
    graficar_distribucion,
)
from mus.cartas import parsear_mano
from mus.evaluacion import Lance, jugada_pares, puntos_juego, resolver_mano, suma
from mus.reglas import ReglasMus, Variante
from mus.tablas import construir_tabla


def _reglas(args: argparse.Namespace) -> ReglasMus:
    return ReglasMus(variante=Variante(args.variante), treinta_y_una_real=args.treinta_y_una_real)


def cmd_evaluar(args: argparse.Namespace) -> None:
    reglas = _reglas(args)
    tabla = construir_tabla(reglas)
    mano = parsear_mano(args.mano, reglas)
    i = tabla.indice(mano)
    s = suma(mano, reglas)
    print(f"Mano: {mano.texto(tabla.baraja)}   ({tabla.combinaciones[i]} combinaciones, "
          f"P = {tabla.probabilidad[i]:.5f})")
    print(f"Pares: {jugada_pares(mano).name.lower()}   Suma: {s}   "
          + (f"Juego ({puntos_juego(mano, reglas)} tantos)" if s >= 31 else "Sin juego"))
    print("\nFrente a una mano aleatoria de un mazo completo (no es la equity en la mesa):")
    print(f"  {'lance':<8}{'peor':>9}{'igual':>9}{'mejor':>9}")
    for lance in Lance:
        if lance is Lance.PUNTO and s >= 31:
            continue
        peor, igual, mejor = comparativa_mano(tabla, i, lance)
        print(f"  {lance.value:<8}{peor:>9.3f}{igual:>9.3f}{mejor:>9.3f}")


def cmd_resolver(args: argparse.Namespace) -> None:
    reglas = _reglas(args)
    manos = [parsear_mano(t, reglas) for t in args.manos]
    baraja = construir_tabla(reglas).baraja
    for pos, m in enumerate(manos, start=1):
        print(f"  Jugador {pos} (pareja {1 if pos % 2 else 2}): {m.texto(baraja)}")
    print()
    for lance, r in resolver_mano(manos, reglas).items():
        if r.se_juega:
            print(f"  {lance.value:<7} gana el jugador {r.ganador} -> pareja {r.pareja} "
                  f"cobra {r.tantos}")
        else:
            print(f"  {lance.value:<7} no se juega")


def cmd_distribucion(args: argparse.Namespace) -> None:
    tabla = construir_tabla(_reglas(args))
    print(f"Variante {tabla.reglas.variante.value}: {tabla.n_manos} manos distintas, "
          f"{tabla.combinaciones.sum()} combinaciones de 4 cartas\n")
    for nombre, p in distribucion_exacta(tabla).items():
        print(f"  {nombre:<20}{p:>10.6f}")
    print("\n  Distribución de sumas:")
    for s, p in distribucion_sumas(tabla).items():
        print(f"    {s:>3}{p:>10.6f}")


def cmd_verificar(args: argparse.Namespace) -> None:
    tabla = construir_tabla(_reglas(args))
    inicio = time.perf_counter()
    filas = comparar_exacto_mc(tabla, args.n, args.semilla, args.confianza)
    segundos = time.perf_counter() - inicio
    print(f"Monte Carlo: {args.n} manos, semilla {args.semilla}, IC {args.confianza:.0%} "
          f"(Wilson), {segundos:.1f} s\n")
    print(f"  {'métrica':<20}{'exacto':>10}{'estimado':>10}   {'intervalo':<22}")
    for f in filas:
        bajo, alto = f.estimacion.intervalo
        marca = "ok" if f.dentro else "FUERA"
        print(f"  {f.metrica:<20}{f.exacto:>10.5f}{f.estimacion.p:>10.5f}   "
              f"[{bajo:.5f}, {alto:.5f}]  {marca}")
    fuera = sum(not f.dentro for f in filas)
    print(f"\n{len(filas) - fuera}/{len(filas)} métricas dentro del intervalo "
          f"(se esperan ~{(1 - args.confianza) * len(filas):.1f} fuera por azar).")
    if args.csv:
        print(f"Guardado en {exportar_comparacion_csv(filas, args.csv)}")


def cmd_tabla(args: argparse.Namespace) -> None:
    tabla = construir_tabla(_reglas(args))
    print(f"Guardado en {exportar_tabla_csv(tabla, args.csv)} ({tabla.n_manos} manos)")


def cmd_grafica(args: argparse.Namespace) -> None:
    print(f"Guardado en {graficar_distribucion(construir_tabla(_reglas(args)), args.salida)}")


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mus", description="Motor de estadísticas del mus.")
    parser.add_argument("--variante", choices=[v.value for v in Variante],
                        default=Variante.OCHO_REYES.value, help="Baraja (por defecto 8reyes).")
    parser.add_argument("--31-real", dest="treinta_y_una_real", action="store_true",
                        help="Activa la 31 real (7 7 7 S gana a cualquier otra 31).")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("evaluar", help="Evalúa una mano en cada lance.")
    p.add_argument("mano", help='Mano, p. ej. "R R C 5".')
    p.set_defaults(func=cmd_evaluar)

    p = sub.add_parser("resolver", help="Resuelve los lances entre 4 manos (en paso).")
    p.add_argument("manos", nargs=4, help="Manos en orden de juego: mano, 2, 3, postre.")
    p.set_defaults(func=cmd_resolver)

    p = sub.add_parser("distribucion", help="Distribución exacta de jugadas.")
    p.set_defaults(func=cmd_distribucion)

    p = sub.add_parser("verificar", help="Compara el cálculo exacto con Monte Carlo.")
    p.add_argument("--n", type=int, default=1_000_000, help="Manos simuladas.")
    p.add_argument("--semilla", type=int, default=None, help="Semilla para reproducir.")
    p.add_argument("--confianza", type=float, default=0.95, help="Nivel del intervalo.")
    p.add_argument("--csv", help="Ruta para exportar los resultados.")
    p.set_defaults(func=cmd_verificar)

    p = sub.add_parser("tabla", help="Exporta las manos distintas con sus evaluaciones.")
    p.add_argument("--csv", required=True, help="Ruta del CSV.")
    p.set_defaults(func=cmd_tabla)

    p = sub.add_parser("grafica", help="Gráfica de la distribución exacta.")
    p.add_argument("--salida", required=True, help="Ruta de la imagen (p. ej. .png).")
    p.set_defaults(func=cmd_grafica)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = crear_parser().parse_args(argv)
    try:
        args.func(args)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
