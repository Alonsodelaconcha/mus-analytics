"""Interfaz de línea de comandos: ``python -m mus <comando> ...``.

Ejemplos::

    python -m mus evaluar "R R C 5"
    python -m mus resolver "R R C 5" "7 7 7 S" "A A 4 5" "C C S S"
    python -m mus distribucion
    python -m mus verificar --n 1000000 --semilla 42 --csv resultados/verificacion.csv
    python -m mus tabla --csv resultados/manos.csv
    python -m mus grafica --salida resultados/distribucion.png
    python -m mus --variante 4reyes distribucion

    python -m mus equity "R R C 5" --posicion 1
    python -m mus equity "R R C 5" --posicion 1 --companero "pares>=medias" --n 1000000
    python -m mus equity "A A 4 5"                       # las cuatro posiciones
    python -m mus ranking --lance grande --posicion 4 --top 15
    python -m mus mesa
    python -m mus equity-tabla --csv resultados/equity.csv --json resultados/equity.json
    python -m mus grafica-posicion --salida resultados/posicion.png
    python -m mus grafica-condicion "R R C 5" --companero "sin_pares" --salida resultados/c.png

Las condiciones van SIEMPRE entre comillas: en PowerShell (y en cualquier
shell) los caracteres > y < redirigen la salida a un fichero.
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
    exportar_equity_csv,
    exportar_equity_json,
    exportar_rankings_csv,
    exportar_tabla_csv,
    graficar_condicion,
    graficar_distribucion,
    graficar_posicion,
    probabilidades_mesa,
    ranking,
)
from mus.cartas import parsear_mano
from mus.condiciones import AYUDA_SINTAXIS, parsear_condicion
from mus.equity import POSICIONES, EquityMano, cargar_tabla_equity, equity, simular_equity
from mus.evaluacion import Lance, jugada_pares, puntos_juego, resolver_mano, suma
from mus.reglas import ReglasMus, Variante
from mus.tablas import construir_tabla

NOMBRE_POSICION = {1: "mano", 2: "segundo", 3: "tercero", 4: "postre"}


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


def _imprimir_equity(e: EquityMano) -> None:
    print(f"\n{e.texto_mano} en posición {e.posicion} ({NOMBRE_POSICION[e.posicion]}); "
          f"información: {e.descripcion_condiciones}"
          + (f"  [P(se cumple) = {e.p_condiciones:.4f}]" if e.p_condiciones < 1 else ""))
    print(f"  {'lance':<8}{'se juega':>10}{'gano yo':>10}{'pareja':>10}{'rivales':>10}"
          f"{'tantos':>10}")
    for l, x in e.por_lance.items():
        print(f"  {l.value:<8}{x.p_se_juega:>10.4f}{x.p_gana_individual:>10.4f}"
              f"{x.p_gana_pareja:>10.4f}{x.p_gana_rival:>10.4f}{x.tantos_netos:>+10.3f}")
    print(f"  {'total':<48}{e.tantos_netos:>+10.3f}")


def cmd_equity(args: argparse.Namespace) -> None:
    reglas = _reglas(args)
    companero = parsear_condicion(args.companero, reglas) if args.companero else None
    posiciones = [args.posicion] if args.posicion else list(POSICIONES)
    print("Probabilidades exactas sobre el reparto inicial (sin mus ni descartes); "
          "tantos netos en paso, a favor - en contra.")
    for p in posiciones:
        e = equity(args.mano, p, reglas, companero=companero)
        _imprimir_equity(e)
        if args.n:
            mc = simular_equity(args.mano, p, args.n, reglas, companero=companero,
                                semilla=args.semilla)
            print(f"  Monte Carlo: {mc.n_aceptados} repartos válidos de {mc.n_simulados}, "
                  "IC 95 %")
            for l, m in mc.por_lance.items():
                x = e.por_lance[l]
                dentro = (m.p_gana_individual.contiene(x.p_gana_individual)
                          and m.p_gana_pareja.contiene(x.p_gana_pareja)
                          and m.tantos_netos.contiene(x.tantos_netos))
                print(f"  {l.value:<8}yo {m.p_gana_individual}  pareja {m.p_gana_pareja}  "
                      f"tantos {m.tantos_netos}  {'ok' if dentro else 'FUERA'}")


def cmd_equity_tabla(args: argparse.Namespace) -> None:
    inicio = time.perf_counter()
    te = cargar_tabla_equity(_reglas(args))
    print(f"Tabla de equity lista en {time.perf_counter() - inicio:.1f} s "
          "(se guarda en resultados/cache; la primera vez tarda ~1 min)")
    if args.csv:
        print(f"Guardado en {exportar_equity_csv(te, args.csv)}")
    if args.json:
        print(f"Guardado en {exportar_equity_json(te, args.json)}")
    if args.rankings:
        print(f"Guardado en {exportar_rankings_csv(te, args.rankings)}")


def cmd_ranking(args: argparse.Namespace) -> None:
    te = cargar_tabla_equity(_reglas(args))
    lance = Lance(args.lance)
    filas = ranking(te, lance, args.posicion)
    print(f"Ranking de {lance.value} en posición {args.posicion} "
          f"({NOMBRE_POSICION[args.posicion]}), por P(gano yo):")
    print(f"  {'#':>4}  {'mano':<10}{'gano yo':>10}{'pareja':>10}{'tantos':>10}{'percentil':>11}")
    seleccion = filas[:args.top] + ([] if args.top >= len(filas) else filas[-args.cola:])
    for i, r in enumerate(seleccion):
        if i == args.top and args.cola:
            print("  ...")
        print(f"  {r.puesto:>4}  {r.mano:<10}{r.equity.p_gana_individual:>10.4f}"
              f"{r.equity.p_gana_pareja:>10.4f}{r.equity.tantos_netos:>+10.3f}"
              f"{r.percentil:>11.3f}")


def cmd_mesa(args: argparse.Namespace) -> None:
    for nombre, p in probabilidades_mesa(cargar_tabla_equity(_reglas(args))).items():
        print(f"  {nombre:<38}{p:>10.5f}")


def cmd_grafica_posicion(args: argparse.Namespace) -> None:
    print(f"Guardado en {graficar_posicion(cargar_tabla_equity(_reglas(args)), args.salida)}")


def cmd_grafica_condicion(args: argparse.Namespace) -> None:
    reglas = _reglas(args)
    sin = equity(args.mano, args.posicion, reglas)
    con = equity(args.mano, args.posicion, reglas,
                 companero=parsear_condicion(args.companero, reglas))
    print(f"Guardado en {graficar_condicion(sin, con, args.salida)}")


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mus", description="Motor de estadísticas del mus.",
        epilog="Las condiciones (--companero) van SIEMPRE entre comillas, p. ej. "
               "--companero \"pares>=medias\": sin ellas, > y < redirigen la salida "
               "en PowerShell y en cualquier shell.")
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

    ayuda_companero = ("Condición sobre la mano del compañero, ENTRE COMILLAS. "
                       + AYUDA_SINTAXIS)
    p = sub.add_parser("equity", help="Equity exacta de una mano por lance y posición.",
                       epilog=AYUDA_SINTAXIS)
    p.add_argument("mano", help='Mano, p. ej. "R R C 5".')
    p.add_argument("--posicion", type=int, choices=POSICIONES,
                   help="1 = mano ... 4 = postre (por defecto, las cuatro).")
    p.add_argument("--companero", help=ayuda_companero)
    p.add_argument("--n", type=int, default=0,
                   help="Repartos Monte Carlo para verificar (0 = solo exacto).")
    p.add_argument("--semilla", type=int, default=None, help="Semilla del Monte Carlo.")
    p.set_defaults(func=cmd_equity)

    p = sub.add_parser("equity-tabla",
                       help="Equity de todas las manos y posiciones (CSV, JSON, rankings).")
    p.add_argument("--csv", help="CSV largo: mano, posición, lance, métricas.")
    p.add_argument("--json", help="JSON compacto para la web.")
    p.add_argument("--rankings", help="CSV con todos los rankings.")
    p.set_defaults(func=cmd_equity_tabla)

    p = sub.add_parser("ranking", help="Ranking de manos por equity en un lance y posición.")
    p.add_argument("--lance", required=True, choices=[l.value for l in Lance])
    p.add_argument("--posicion", type=int, choices=POSICIONES, default=1)
    p.add_argument("--top", type=int, default=20, help="Mejores manos a mostrar.")
    p.add_argument("--cola", type=int, default=5, help="Peores manos a mostrar.")
    p.set_defaults(func=cmd_ranking)

    p = sub.add_parser("mesa", help="Probabilidades exactas de mesa por lance y posición.")
    p.set_defaults(func=cmd_mesa)

    p = sub.add_parser("grafica-posicion", help="Equity siendo mano frente a postre.")
    p.add_argument("--salida", required=True)
    p.set_defaults(func=cmd_grafica_posicion)

    p = sub.add_parser("grafica-condicion",
                       help="Efecto de una condición del compañero sobre una mano.",
                       epilog=AYUDA_SINTAXIS)
    p.add_argument("mano")
    p.add_argument("--posicion", type=int, choices=POSICIONES, default=1)
    p.add_argument("--companero", required=True, help=ayuda_companero)
    p.add_argument("--salida", required=True)
    p.set_defaults(func=cmd_grafica_condicion)
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
