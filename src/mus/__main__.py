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

import numpy as np

from mus.analisis import (
    comparar_exacto_mc,
    comparativa_mano,
    distribucion_exacta,
    distribucion_sumas,
    exportar_comparacion_csv,
    exportar_corte_csv,
    exportar_descartes_csv,
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
from mus.calibracion import (
    MANOS_RECOMENDADAS,
    RUTA_DATOS,
    Observacion,
    calibrar,
    curva_hay_mus,
    leer_observaciones,
)
from mus.cartas import parsear_mano
from mus.condiciones import AYUDA_SINTAXIS, parsear_condicion
from mus.cortar import SIMULACIONES_POR_VUELTA as SIMULACIONES_CORTE
from mus.cortar import (
    DecisionCorte,
    MesaConCorte,
    iterar_corte,
    mesa_rivales_razonables,
    valorar_corte,
)
from mus.descarte import (
    OBJETIVOS,
    UMBRAL_EQUIVALENCIA,
    CartasPedidas,
    Objetivo,
    cartas_pedidas,
    texto_conteos,
    evaluar_descartes,
    mejores_descartes,
    objetivo_con_pesos,
    simular_descarte,
)
from mus.equity import POSICIONES, EquityMano, cargar_tabla_equity, equity, simular_equity
from mus.evaluacion import Lance, jugada_pares, puntos_juego, resolver_mano, suma
from mus.reglas import ReglasMus, Variante
from mus.simulacion import Estimacion
from mus.tablas import construir_tabla
from mus.testigos import CASOS_TESTIGO, COMPANERO_FLOJO, COMPANERO_VA_BIEN, comparar
from mus.tras_mus import (
    SIMULACIONES_POR_VUELTA,
    MesaTrasMus,
    iterar_tras_mus,
    simular_ronda_mus,
    valorar_opciones_simuladas,
    verificar_mesa,
)

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
    # Ojo: filas[-0:] sería la lista entera, por eso la cola se calcula con un índice positivo.
    cola = filas[max(args.top, len(filas) - args.cola):] if args.cola > 0 else []
    seleccion = filas[:args.top] + cola
    for i, r in enumerate(seleccion):
        if i == args.top:
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


def _objetivo(args: argparse.Namespace) -> Objetivo:
    return objetivo_con_pesos(args.pesos) if args.pesos else OBJETIVOS[args.objetivo]


def cmd_descarte(args: argparse.Namespace) -> None:
    reglas = _reglas(args)
    te = cargar_tabla_equity(reglas)
    objetivo = _objetivo(args)
    mano = parsear_mano(args.mano, reglas)
    baraja = te.tabla.baraja
    te_servida, mesa = te, None
    if args.tras_mus:
        mesa = _mesa_tras_mus(reglas)
        te = mesa.tabla
    valoraciones, _ = evaluar_descartes(mano, args.posicion, te, objetivo)
    servida = evaluar_descartes(mano, args.posicion, te_servida, objetivo)[1]
    print(f"{mano.texto(baraja)} en posición {args.posicion} ({NOMBRE_POSICION[args.posicion]}); "
          f"objetivo: {objetivo.nombre}")
    if args.tras_mus:
        print("Valoración contra la mesa tras el mus: los cuatro se descartan con la política "
              "del punto fijo (3b). La mano servida (= cortar) se valora contra el reparto "
              "inicial, porque si se corta nadie se descarta. Aún sin efecto de selección (3c).")
    else:
        print("Valoración con la equity del reparto inicial (Fase 2): los rivales aún no se "
              "han descartado. Valores esperados sobre la mano final.")
    cabecera = (f"  {'#':>2}  {'me quedo':<10}{'tiro':<9}{'valor':>8}{'tantos':>8}"
                f"{'P(pares)':>9}{'P(juego)':>9}{'P(31)':>7}   gano: "
                + " ".join(f"{l.value[:6]:>6}" for l in Lance))
    print(cabecera)

    def fila(etiqueta: str, quedo: str, tiro: str, v) -> str:
        return (f"  {etiqueta:>2}  {quedo:<10}{tiro:<9}{v.valor:>8.3f}{v.tantos_netos:>+8.3f}"
                f"{v.p_pares:>9.3f}{v.p_juego:>9.3f}{v.p_31:>7.3f}         "
                + " ".join(f"{g:>6.3f}" for g in v.gana_individual))

    mejor = valoraciones[0]
    equivalentes = [v for v in valoraciones if mejor.valor - v.valor < args.umbral]
    for k, v in enumerate(valoraciones, start=1):
        o = v.opcion
        marca = "≈" if len(equivalentes) > 1 and k <= len(equivalentes) else ""
        print(fila(f"{marca}{k}", texto_conteos(o.conservadas, baraja),
                   texto_conteos(o.descartadas, baraja), v))
    print(fila("", "servida", "(=cortar)", servida) + "   <- referencia, no es opción")
    if len(equivalentes) > 1:
        print(f"\nPrácticamente equivalentes (diferencia < {args.umbral:g}, marcadas con ≈): "
              + "; ".join(v.opcion.texto(baraja) for v in equivalentes)
              + f". Mejora esperada {mejor.valor - servida.valor:+.3f} frente a la mano servida.")
    else:
        segunda = valoraciones[1].valor if len(valoraciones) > 1 else mejor.valor
        print(f"\nRecomendación: {mejor.opcion.texto(baraja)} "
              f"(ventaja {mejor.valor - segunda:.3f} sobre la segunda opción; "
              f"mejora esperada {mejor.valor - servida.valor:+.3f} frente a la mano servida)")

    if args.n and mesa is not None:
        _descarte_simulado(mano, args, mesa, servida_tantos=servida.tantos_netos)
    elif args.n:
        print(f"\nMonte Carlo ({args.n} robos por opción, IC 95 %) del valor de cada opción:")
        valores = objetivo.valores(te, args.posicion)
        for v in valoraciones:
            sim = simular_descarte(mano, v.opcion, args.n, reglas, valores=valores,
                                   semilla=args.semilla)
            dentro = sim.valor.contiene(v.valor) and sim.p_juego.contiene(v.p_juego)
            print(f"  {v.opcion.texto(baraja):<34} exacto {v.valor:8.4f}  MC {sim.valor}  "
                  f"P(juego) {sim.p_juego}  {'ok' if dentro else 'FUERA'}")


def cmd_descarte_tabla(args: argparse.Namespace) -> None:
    reglas = _reglas(args)
    te = cargar_tabla_equity(reglas)
    objetivo = _objetivo(args)
    if args.tras_mus:
        filas = mejores_descartes(_mesa_tras_mus(reglas).tabla, objetivo, te_servida=te)
    else:
        filas = mejores_descartes(te, objetivo)
    ruta = exportar_descartes_csv(filas, te.tabla.baraja, objetivo, args.csv, args.umbral)
    print(f"Guardado en {ruta} ({len(filas)} filas; objetivo: {objetivo.nombre})")
    equivalentes = sum(f.equivalentes(args.umbral) for f in filas)
    print(f"Decisiones prácticamente equivalentes (margen < {args.umbral:g}): "
          f"{equivalentes} de {len(filas)}")
    _imprimir_cartas_pedidas(cartas_pedidas(filas, te.tabla))


def _imprimir_cartas_pedidas(filas: list[CartasPedidas]) -> None:
    print("\nCartas pedidas con el descarte recomendado: manos distintas (sin ponderar) "
          "y % de repartos (ponderado por la probabilidad de cada mano)")
    print(f"  {'posición':<10}" + "".join(f"{f'{k} carta' + ('s' if k > 1 else ''):>20}"
                                          for k in range(1, 5)))
    for f in filas:
        print(f"  {f.posicion:<10}" + "".join(f"{f.manos[k]:>8} manos {100 * f.repartos[k]:>5.1f} %"
                                            for k in range(1, 5)))


def _descarte_simulado(mano, args: argparse.Namespace, mesa: MesaTrasMus,
                       servida_tantos: float) -> None:
    """Valora las opciones simulando la ronda con esta mano fija (sin simplificaciones)."""
    baraja = mesa.tabla.tabla.baraja
    inicio = time.perf_counter()
    resultado = valorar_opciones_simuladas(mano, args.posicion, mesa.politica, args.n,
                                           semilla=args.semilla)
    print(f"\nSimulación de la ronda con esta mano fija ({args.n} repartos, los mismos para "
          f"todas las opciones; {time.perf_counter() - inicio:.0f} s). Tantos netos totales "
          "en paso, IC 95 %. Incluye mis propios descartes y la conjunta real de los rivales:")
    for r in resultado:
        d = r.diferencia_con_la_mejor
        print(f"  {r.opcion.texto(baraja):<34} {r.tantos}   frente a la mejor: "
              f"{d.media:+.4f} [{d.intervalo[0]:+.4f}, {d.intervalo[1]:+.4f}]")
    mejor = resultado[0].tantos
    print(f"  Cortar (nadie se descarta; exacto, Fase 2): {servida_tantos:+.4f}  ->  dar mus "
          f"cambia {mejor.media - servida_tantos:+.4f} [{mejor.intervalo[0] - servida_tantos:+.4f}, "
          f"{mejor.intervalo[1] - servida_tantos:+.4f}]")


def _mesa_tras_mus(reglas: ReglasMus, objetivo: Objetivo = OBJETIVOS["tantos"],
                   informar: bool = False, max_iteraciones: int = 12,
                   simulaciones: int = SIMULACIONES_POR_VUELTA) -> MesaTrasMus:
    """Mesa tras el mus (punto fijo). La primera vez simula varias vueltas
    (~30-60 s cada una); después se cargan de resultados/cache."""
    mesa = iterar_tras_mus(reglas, objetivo, max_iteraciones=max_iteraciones,
                           simulaciones=simulaciones,
                           informar=(lambda s: print(f"  {s}", flush=True)) if informar else None)
    if not informar:
        print(f"(Mesa tras el mus: {'punto fijo' if mesa.convergio else 'SIN CONVERGER'} "
              f"tras {len(mesa.historia)} vueltas.)")
    if not mesa.convergio:
        print("AVISO: la iteración no ha convergido; los resultados usan la última política.")
    return mesa


def cmd_tras_mus(args: argparse.Namespace) -> None:
    reglas = _reglas(args)
    objetivo = _objetivo(args)
    print(f"Mesa tras una ronda de mus. Todos dan mus (sin efecto de selección: 3c); "
          f"política de descarte: {objetivo.nombre}.")
    inicio = time.perf_counter()
    mesa = _mesa_tras_mus(reglas, objetivo, informar=True, max_iteraciones=args.max_iter,
                          simulaciones=args.n)
    print(f"{'Punto fijo alcanzado' if mesa.convergio else 'NO ha convergido'} en "
          f"{len(mesa.historia)} vueltas ({time.perf_counter() - inicio:.0f} s).")

    tabla = mesa.tabla.tabla
    rey = tabla.baraja.indice("R")
    metricas = {
        "pares": tabla.jugada_pares > 0, "medias": tabla.jugada_pares == 2,
        "duples": tabla.jugada_pares == 3, "juego": tabla.tiene_juego,
        "31": tabla.suma == 31, "40": tabla.suma == 40, "punto 30": tabla.suma == 30,
        "al menos 1 rey": tabla.conteos[:, rey] >= 1, "2 reyes o más": tabla.conteos[:, rey] >= 2,
    }
    print("\nDistribución de las manos con que se juegan los lances:")
    print(f"  {'P(...)':<16}{'reparto':>10}" + "".join(f"{f'tras mus {p}':>13}" for p in POSICIONES))
    for nombre, m in metricas.items():
        print(f"  {nombre:<16}{tabla.probabilidad[m].sum():>10.4f}"
              + "".join(f"{mesa.marginales[p - 1][m].sum():>13.4f}" for p in POSICIONES))

    print("\nCartas pedidas (% de repartos, ponderado):")
    for p in POSICIONES:
        pedidas = mesa.politica.cartas_pedidas(p)
        print(f"  posición {p}: " + "   ".join(f"{k}: {100 * v:5.1f} %" for k, v in pedidas.items()))

    inicial = probabilidades_mesa(mesa.tabla_inicial)
    tras = probabilidades_mesa(mesa.tabla, mesa.marginales)
    print("\nMesa (pareja 1-3 = la de la mano), reparto inicial -> tras el mus:")
    print(f"  {'lance':<8}{'se juega':>18}{'gana pareja 1-3':>20}{'tantos pareja 1-3':>22}")
    for l in Lance:
        v = l.value
        print(f"  {v:<8}"
              f"{inicial[f'{v}: se juega']:>8.4f} -> {tras[f'{v}: se juega']:.4f}"
              f"{inicial[f'{v}: gana la pareja 1-3']:>10.4f} -> {tras[f'{v}: gana la pareja 1-3']:.4f}"
              f"{inicial[f'{v}: tantos netos pareja 1-3']:>+12.4f} -> "
              f"{tras[f'{v}: tantos netos pareja 1-3']:+.4f}")
    print(f"  {'total':<8}{'':>38}{inicial['total: tantos netos pareja 1-3']:>+12.4f} -> "
          f"{tras['total: tantos netos pareja 1-3']:+.4f}")

    if args.verificar:
        _verificar_tras_mus(mesa, args.verificar, args.semilla)
    if args.csv:
        print(f"\nEquity tras el mus guardada en {exportar_equity_csv(mesa.tabla, args.csv)}")


def _mesa_con_corte(reglas: ReglasMus, escenario: str = "razonables", informar: bool = False,
                    simulaciones: int = SIMULACIONES_CORTE,
                    factor_corte: float = 1.0) -> MesaConCorte:
    """Mesa con corte. ``escenario``: "razonables" (rivales de nivel 1, con su corte
    escalado por ``factor_corte``) o "equilibrio" (punto fijo corte ↔ descarte).
    La primera vez simula; después usa resultados/cache."""
    if escenario == "razonables":
        mesa = mesa_rivales_razonables(reglas, simulaciones=simulaciones,
                                       factor_corte=factor_corte)
        if not informar:
            print(f"(Mesa: {mesa.escenario}; P(hay mus) = {mesa.p_hay_mus:.3f}.)")
        return mesa
    mesa = iterar_corte(reglas, simulaciones=simulaciones,
                        informar=(lambda s: print(f"  {s}", flush=True)) if informar else None)
    if mesa.historia:
        ultima = mesa.historia[-1]
        resumen = (f"explotabilidad por reparto: corte {ultima.explotabilidad_corte:.4f}, "
                   f"descarte {ultima.explotabilidad_descarte:.4f}")
    else:
        resumen = "sin historial de iteración"
    if not informar:
        print(f"(Mesa con corte: {'equilibrio' if mesa.convergio else 'SIN CONVERGER'} tras "
              f"{len(mesa.historia)} vueltas; {resumen}.)")
    if not mesa.convergio:
        print(f"AVISO: la iteración no ha convergido ({resumen}); se usa la última política.")
    return mesa


def _imprimir_decision(d: DecisionCorte, baraja) -> None:
    v = d.ventaja_mus
    print(f"\n{d.mano} en posición {d.posicion} ({NOMBRE_POSICION[d.posicion]}); {d.informacion}")
    print(f"  Cortar:  {d.cortar}")
    print(f"  Dar mus: {d.mus}  (con el mejor descarte; P(que den mus los que hablan "
          f"después) = {d.p_mus_despues:.3f})")
    print(f"  Dar mus - cortar: {v}  ->  {d.decision.upper()}")
    print("  Si hay mus, cada descarte (valor de dar mus y descartarse así; frente al mejor):")
    for o in d.opciones[:6]:
        f = o.frente_a_la_mejor
        print(f"    {o.opcion.texto(baraja):<34} {o.valor_mus}   {f.media:+.4f} "
              f"[{f.intervalo[0]:+.4f}, {f.intervalo[1]:+.4f}]")


def cmd_cortar(args: argparse.Namespace) -> None:
    reglas = _reglas(args)
    mesa = _mesa_con_corte(reglas, args.escenario, factor_corte=args.factor_corte)
    companero = parsear_condicion(args.companero, reglas) if args.companero else None
    posiciones = [args.posicion] if args.posicion else list(POSICIONES)
    print(f"Tantos netos en paso, IC 95 %. Escenario: {mesa.escenario}. Se simula la mano con "
          "los otros tres repartidos al azar, decidiendo y descartándose con las políticas del "
          "escenario; los que hablan antes han dado mus.")
    for p in posiciones:
        d = valorar_corte(args.mano, p, mesa, args.n, companero=companero, semilla=args.semilla)
        _imprimir_decision(d, mesa.tabla_inicial.tabla.baraja)


def cmd_corte_mesa(args: argparse.Namespace) -> None:
    reglas = _reglas(args)
    print(f"Cortar / dar mus y descarte (una ronda de mus, tantos en paso, sin señas). "
          f"Escenario: {args.escenario}.")
    inicio = time.perf_counter()
    mesa = _mesa_con_corte(reglas, args.escenario, informar=True, simulaciones=args.n)
    if args.escenario == "equilibrio":
        print(f"{'Equilibrio alcanzado' if mesa.convergio else 'NO ha convergido'} en "
              f"{len(mesa.historia)} vueltas ({time.perf_counter() - inicio:.0f} s).")
    print(f"\nP(hay mus) = {mesa.p_hay_mus:.4f}")
    print(f"  {'posición':<10}{'P(le toca hablar)':>20}{'P(corta | habla)':>20}")
    for p in POSICIONES:
        print(f"  {p:<10}{mesa.p_habla(p):>20.4f}{mesa.p_cortar(p):>20.4f}")
    valor = mesa.simulacion.valor_pareja_mano / mesa.simulacion.n
    print(f"\nTantos netos de la pareja 1-3 por mano: {valor:+.4f} (reparto inicial, sin mus: "
          f"{probabilidades_mesa(mesa.tabla_inicial)['total: tantos netos pareja 1-3']:+.4f})")
    if args.csv:
        print(f"Guardado en {exportar_corte_csv(mesa, args.csv)}")


def cmd_testigos(args: argparse.Namespace) -> None:
    reglas = _reglas(args)
    mesas = {e: _mesa_con_corte(reglas, e, factor_corte=args.factor_corte)
             for e in ("razonables", "equilibrio")}
    baraja = mesas["razonables"].tabla_inicial.tabla.baraja
    print(f"\nCasos testigo (docs/casos_testigo.md) frente al modelo; {args.n} repartos por caso, "
          "IC 95 %. Pérdida = tantos por mano que cuesta la decisión del usuario frente a la "
          "del modelo con rivales razonables.\n")
    print(f"  {'mano':<9}{'pos':>4}  {'usuario':<14}| {'rivales razonables: mus - cortar':<46}"
          f"{'pérdida':>8} | {'equilibrio: mus - cortar':<35}| {'descarte usuario / modelo'}")
    for caso in CASOS_TESTIGO:
        c = comparar(caso, mesas["razonables"], args.n, semilla=args.semilla)
        e = comparar(caso, mesas["equilibrio"], args.n, semilla=args.semilla)
        usuario = caso.decision + (f" ({caso.me_quedo})" if caso.me_quedo else "")
        perdida = "-" if c.perdida_decision is None else f"{c.perdida_decision:.3f}"
        modelo_desc = texto_conteos(c.modelo.mejor_descarte.conservadas, baraja)
        desc = (f"{caso.me_quedo or '-'} / {modelo_desc}"
                + (f" (pierde {c.perdida_descarte:.3f})" if c.perdida_descarte else ""))
        print(f"  {caso.mano:<9}{caso.posicion:>4}  {usuario:<14}| {_ventaja(c.modelo):<46}"
              f"{perdida:>8} | {_ventaja(e.modelo):<35}| {desc}")
    print("\nA A 4 5 de postre, preguntando al compañero (rivales razonables):")
    for condicion in (None, COMPANERO_FLOJO, COMPANERO_VA_BIEN):
        d = valorar_corte("A A 4 5", 4, mesas["razonables"], args.n, companero=condicion,
                          semilla=args.semilla)
        nombre = "sin preguntar" if condicion is None else condicion.descripcion
        print(f"  {nombre:<52} {_ventaja(d)}; si hay mus: "
              f"{texto_conteos(d.mejor_descarte.conservadas, baraja)}")


def cmd_calibrar(args: argparse.Namespace) -> None:
    if args.manos is not None:
        observacion = Observacion(args.manos, args.con_mus or 0)
        origen = "datos de la línea de órdenes"
    else:
        observacion = leer_observaciones(args.datos)
        origen = args.datos
    curva = curva_hay_mus(_reglas(args))
    c = calibrar(observacion, curva)
    bajo, alto = c.p_observada.intervalo
    print(f"Partidas reales ({origen}): mus en {observacion.con_mus} de {observacion.manos} manos "
          f"= {100 * c.p_observada.p:.0f} % (IC 95 %: {100 * bajo:.0f}-{100 * alto:.0f} %)")
    print("\nModelo (rivales razonables con su corte ×λ): P(hay mus en la primera ronda)")
    print("  " + "  ".join(f"λ={l:g}: {100 * p:.0f} %" for l, p in curva))
    print(f"\nλ compatible con los datos: {c.lambda_estimada:.2f} "
          f"(intervalo {c.lambda_intervalo[0]:.2f}-{c.lambda_intervalo[1]:.2f}"
          + (", recortado: parte del intervalo de la proporción queda fuera de lo que da el "
             "modelo)" if c.intervalo_recortado else ")"))
    if not c.dentro_del_rango:
        print("AVISO: la proporción observada queda fuera de lo que da el modelo; λ se ha "
              "recortado a 0 o 1.")
    if not c.suficiente:
        print(f"Con {observacion.manos} manos el intervalo es demasiado ancho para decidir: "
              f"conviene llegar a {MANOS_RECOMENDADAS}-50. No se cambia nada.")
    else:
        print(f"Para usarlo: --factor-corte {c.lambda_estimada:.2f} en 'cortar' y 'testigos'. "
              "El valor por defecto (1) no cambia solo.")


def _ventaja(d: DecisionCorte) -> str:
    v = d.ventaja_mus
    return f"{d.decision:<12}{v.media:+.3f} [{v.intervalo[0]:+.3f}, {v.intervalo[1]:+.3f}]"


def _verificar_tras_mus(mesa: MesaTrasMus, n: int, semilla: int | None) -> None:
    if semilla == mesa.semilla:
        raise ValueError("La verificación necesita una semilla distinta de la de la mesa")
    inicio = time.perf_counter()
    sim = simular_ronda_mus(mesa.politica, n, semilla)
    informe = verificar_mesa(mesa, sim)
    print(f"\nVerificación con {n} rondas de mus simuladas de forma independiente "
          f"({time.perf_counter() - inicio:.0f} s; IC 99,9 %):")
    for s, (chi2, gl) in enumerate(informe.chi2_marginales, start=1):
        print(f"  Marginal exacta del asiento {s}: χ² = {chi2:.0f} con {gl} g.l. "
              f"(media esperada {gl}, desviación típica {np.sqrt(2 * gl):.0f})")
    fuera = [c for c in informe.agregadas if not c.dentro]
    print(f"  Magnitudes de mesa dentro del IC: {len(informe.agregadas) - len(fuera)} de "
          f"{len(informe.agregadas)}" + (". Fuera:" if fuera else "."))
    for c in fuera:
        nombre = c.lance.value if c.lance else "total"
        simulado = c.simulado.p if isinstance(c.simulado, Estimacion) else c.simulado.media
        print(f"    asiento {c.asiento} {nombre:<7} {c.metrica:<15} modelo {c.prediccion:+.4f}  "
              f"simulado {c.simulado}  diferencia {c.prediccion - simulado:+.4f}")
    print("  Tantos netos totales mano a mano (manos con ≥ 5000 muestras):")
    for e in informe.por_mano:
        if e.manos_comparadas == 0:
            print(f"    asiento {e.asiento}: ninguna mano con muestras suficientes (aumenta N)")
            continue
        print(f"    asiento {e.asiento}: {e.manos_comparadas} manos, error medio {e.error_medio:.4f}, "
              f"máximo {e.error_maximo:.4f} ({e.mano_error_maximo}), fuera del IC {e.fuera_del_intervalo}")


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

    p = sub.add_parser("tras-mus", help="Mesa tras una ronda de mus: política de descarte en "
                                         "punto fijo, distribución de manos y equity (3b).")
    p.add_argument("--objetivo", choices=list(OBJETIVOS), default="tantos",
                   help="Objetivo con que se descartan los cuatro jugadores.")
    p.add_argument("--pesos", help='Tantos ponderados por lance, ENTRE COMILLAS, p. ej. '
                                   '"grande=2" (sustituye a --objetivo).')
    p.add_argument("--max-iter", type=int, default=12, help="Máximo de vueltas de la iteración.")
    p.add_argument("--n", type=int, default=SIMULACIONES_POR_VUELTA,
                   help="Rondas simuladas por vuelta para estimar la equity tras el mus.")
    p.add_argument("--verificar", type=int, default=0, metavar="N",
                   help="Simular N rondas más, de forma independiente, y compararlas con la "
                        "mesa calculada (0 = no).")
    p.add_argument("--semilla", type=int, default=1,
                   help="Semilla de la verificación (distinta de la de la mesa).")
    p.add_argument("--csv", help="Exportar la equity tras el mus (formato de equity-tabla).")
    p.set_defaults(func=cmd_tras_mus)

    ayuda_escenario = ("razonables: los rivales cortan si les conviene suponiendo que todos "
                       "dan mus (por defecto); equilibrio: punto fijo corte ↔ descarte (en "
                       "este modelo, casi nunca hay mus).")
    p = sub.add_parser("corte-mesa", help="Cortar o dar mus y descarte en la mesa (3c).")
    p.add_argument("--escenario", choices=("razonables", "equilibrio"), default="razonables",
                   help=ayuda_escenario)
    p.add_argument("--n", type=int, default=SIMULACIONES_CORTE,
                   help="Repartos simulados por vuelta.")
    p.add_argument("--csv", help="Exportar, por mano y posición, P(cortar), valor de cortar "
                                 "y ventaja de dar mus.")
    p.set_defaults(func=cmd_corte_mesa)

    p = sub.add_parser("cortar", help="¿Cortar o dar mus con esta mano? (3c)",
                       epilog=AYUDA_SINTAXIS)
    p.add_argument("mano", help='Mano, p. ej. "R R C S".')
    p.add_argument("--posicion", type=int, choices=POSICIONES,
                   help="1 = mano ... 4 = postre (por defecto, las cuatro).")
    p.add_argument("--companero", help="Condición sobre la mano del compañero, ENTRE "
                                       "COMILLAS (p. ej. \"sin_pares, sin_juego\").")
    p.add_argument("--n", type=int, default=300_000, help="Repartos simulados.")
    p.add_argument("--semilla", type=int, default=None)
    p.add_argument("--escenario", choices=("razonables", "equilibrio"), default="razonables",
                   help=ayuda_escenario)
    ayuda_factor = ("Escala la probabilidad de corte de los rivales razonables: 0 = nadie "
                    "corta (como en la 3b), 1 = rivales razonables (por defecto). Las "
                    "decisiones dudosas dependen de cuánto se corta en la mesa.")
    p.add_argument("--factor-corte", type=float, default=1.0, help=ayuda_factor)
    p.set_defaults(func=cmd_cortar)

    p = sub.add_parser("testigos", help="Compara los casos testigo del usuario con el modelo.")
    p.add_argument("--n", type=int, default=300_000, help="Repartos simulados por caso.")
    p.add_argument("--semilla", type=int, default=1)
    p.add_argument("--factor-corte", type=float, default=1.0, help=ayuda_factor)
    p.set_defaults(func=cmd_testigos)

    p = sub.add_parser("calibrar", help="λ compatible con la frecuencia de mus observada en "
                                        "partidas reales (no cambia nada).")
    p.add_argument("--datos", default=str(RUTA_DATOS),
                   help="CSV con columnas sesion,fecha,manos,con_mus,notas.")
    p.add_argument("--manos", type=int, help="Manos observadas (en vez de leer el CSV).")
    p.add_argument("--con-mus", type=int, help="Manos con mus en la primera ronda.")
    p.set_defaults(func=cmd_calibrar)

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

    ayuda_pesos = ('Tantos netos ponderados por lance, ENTRE COMILLAS, p. ej. "grande=2,punto=0" '
                   "(los lances no citados pesan 1). Sustituye a --objetivo.")
    for nombre, ayuda, func in (
        ("descarte", "Valora todas las formas de descartarse de una mano.", cmd_descarte),
        ("descarte-tabla", "Descarte recomendado de todas las manos y posiciones (CSV).",
         cmd_descarte_tabla),
    ):
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("--tras-mus", action="store_true",
                       help="Valorar contra la mesa tras el mus (3b: los rivales también se "
                            "descartan) en vez de contra el reparto inicial.")
        if nombre == "descarte":
            p.add_argument("mano", help='Mano, p. ej. "R R C 5".')
            p.add_argument("--posicion", type=int, choices=POSICIONES, default=1)
            p.add_argument("--n", type=int, default=0,
                           help="Monte Carlo (0 = no). Sin --tras-mus: robos por opción para "
                                "verificar la distribución exacta. Con --tras-mus: repartos "
                                "para simular la ronda con esta mano fija.")
            p.add_argument("--semilla", type=int, default=None)
        else:
            p.add_argument("--csv", required=True)
        p.add_argument("--objetivo", choices=list(OBJETIVOS), default="tantos",
                       help="tantos = tantos netos en paso; grande/chica/pares/juego = "
                            "P(gano yo ese lance).")
        p.add_argument("--pesos", help=ayuda_pesos)
        p.add_argument("--umbral", type=float, default=UMBRAL_EQUIVALENCIA,
                       help="Diferencia de valor por debajo de la cual dos opciones se "
                            f"consideran prácticamente equivalentes (por defecto "
                            f"{UMBRAL_EQUIVALENCIA:g}, en las unidades del objetivo).")
        p.set_defaults(func=func)
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
