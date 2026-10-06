"""Distribuciones exactas, verificación contra Monte Carlo y exportación.

Cada métrica se define una sola vez como una *máscara* booleana sobre las
manos de la tabla. Su valor exacto es la suma de probabilidades de las manos
marcadas, y su estimación Monte Carlo es la frecuencia de esas mismas manos
en una muestra. Usar la misma definición para ambos garantiza que la
comparación mide el muestreo y los pesos, no dos implementaciones distintas.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from mus.equity import POSICIONES, EquityLance, EquityMano, TablaEquity
from mus.evaluacion import Lance, Pares
from mus.simulacion import Estimacion, generador, muestrear_manos
from mus.tablas import TablaManos


def metricas_por_mano(tabla: TablaManos) -> dict[str, np.ndarray]:
    """Métricas de una mano individual, como máscaras sobre la tabla."""
    rey = tabla.baraja.indice("R")
    metricas = {
        "Al menos un rey": tabla.conteos[:, rey] > 0,
        "Pares (cualquiera)": tabla.jugada_pares > Pares.SIN_PARES,
        "Par": tabla.jugada_pares == Pares.PAR,
        "Medias": tabla.jugada_pares == Pares.MEDIAS,
        "Duples": tabla.jugada_pares == Pares.DUPLES,
        "Juego": tabla.tiene_juego,
    }
    for s in sorted(tabla.reglas.orden_juego):
        metricas[f"Juego {s}"] = tabla.suma == s
    if tabla.reglas.treinta_y_una_real:
        metricas["31 real"] = tabla.fuerza[Lance.JUEGO] == tabla.fuerza[Lance.JUEGO].max()
    metricas["Punto 30"] = tabla.suma == 30
    return metricas


def probabilidad_exacta(tabla: TablaManos, mascara: np.ndarray) -> float:
    """Probabilidad exacta de recibir una mano de las marcadas."""
    return float(tabla.probabilidad[mascara].sum())


def distribucion_exacta(tabla: TablaManos) -> dict[str, float]:
    """Probabilidad exacta de cada métrica de :func:`metricas_por_mano`."""
    return {nombre: probabilidad_exacta(tabla, m) for nombre, m in metricas_por_mano(tabla).items()}


def distribucion_sumas(tabla: TablaManos) -> dict[int, float]:
    """Probabilidad exacta de cada suma posible."""
    return {
        int(s): probabilidad_exacta(tabla, tabla.suma == s) for s in np.unique(tabla.suma)
    }


def comparativa_mano(tabla: TablaManos, indice: int, lance: Lance) -> tuple[float, float, float]:
    """Probabilidad de que otra mano aleatoria sea peor, igual o mejor en un lance.

    Es una referencia de fuerza de la mano frente a una mano cualquiera de un
    mazo completo; **no** es la equity real en la mesa (eso es la Fase 2,
    donde importan las cartas retiradas, los 4 jugadores y la posición).
    """
    f = tabla.fuerza[lance]
    propia = f[indice]
    p = tabla.probabilidad
    return float(p[f < propia].sum()), float(p[f == propia].sum()), float(p[f > propia].sum())


@dataclass(frozen=True)
class FilaComparacion:
    """Una métrica comparada: valor exacto frente a estimación Monte Carlo."""

    metrica: str
    exacto: float
    estimacion: Estimacion

    @property
    def dentro(self) -> bool:
        return self.estimacion.contiene(self.exacto)


def comparar_exacto_mc(
    tabla: TablaManos, n: int, semilla: int | None = None, confianza: float = 0.95
) -> list[FilaComparacion]:
    """Compara cada métrica exacta con su estimación sobre ``n`` manos aleatorias.

    Con un nivel de confianza del 95 %, es normal que alrededor de 1 de cada
    20 métricas quede fuera de su intervalo por puro azar.
    """
    indices = muestrear_manos(n, tabla, generador(semilla))
    frecuencias = np.bincount(indices, minlength=tabla.n_manos)
    return [
        FilaComparacion(
            nombre,
            probabilidad_exacta(tabla, mascara),
            Estimacion(int(frecuencias[mascara].sum()), n, confianza),
        )
        for nombre, mascara in metricas_por_mano(tabla).items()
    ]


# --- Exportación -------------------------------------------------------------


def exportar_tabla_csv(tabla: TablaManos, ruta: str | Path) -> Path:
    """Exporta todas las manos con sus evaluaciones y probabilidades a CSV."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            ["mano", "combinaciones", "probabilidad", "suma", "pares", "puntos_pares",
             "puntos_juego", *(f"fuerza_{l.value}" for l in Lance)]
        )
        for i, mano in enumerate(tabla.manos):
            w.writerow(
                [mano.texto(tabla.baraja), int(tabla.combinaciones[i]),
                 f"{tabla.probabilidad[i]:.8f}", int(tabla.suma[i]),
                 Pares(int(tabla.jugada_pares[i])).name.lower(), int(tabla.puntos_pares[i]),
                 int(tabla.puntos_juego[i]), *(int(tabla.fuerza[l][i]) for l in Lance)]
            )
    return ruta


def exportar_comparacion_csv(filas: list[FilaComparacion], ruta: str | Path) -> Path:
    """Exporta una comparación exacto vs. Monte Carlo a CSV."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metrica", "exacto", "estimado", "ic_bajo", "ic_alto", "n", "dentro"])
        for fila in filas:
            bajo, alto = fila.estimacion.intervalo
            w.writerow([fila.metrica, f"{fila.exacto:.6f}", f"{fila.estimacion.p:.6f}",
                        f"{bajo:.6f}", f"{alto:.6f}", fila.estimacion.n, fila.dentro])
    return ruta


# --- Equity (Fase 2) ---------------------------------------------------------


def exportar_equity_csv(te: TablaEquity, ruta: str | Path) -> Path:
    """Tabla de equity en formato largo: una fila por (mano, posición, lance)."""
    ruta = _preparar(ruta)
    tabla = te.tabla
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mano", "probabilidad_mano", "posicion", "lance", "p_se_juega",
                    "p_gana_individual", "p_gana_pareja", "p_gana_rival", "tantos_netos"])
        for i, mano in enumerate(tabla.manos):
            for p in POSICIONES:
                for lance in Lance:
                    e = te.de(i, p, lance)
                    w.writerow([mano.texto(tabla.baraja), f"{tabla.probabilidad[i]:.8f}", p,
                                lance.value, f"{e.p_se_juega:.6f}", f"{e.p_gana_individual:.6f}",
                                f"{e.p_gana_pareja:.6f}", f"{e.p_gana_rival:.6f}",
                                f"{e.tantos_netos:.6f}"])
    return ruta


def exportar_equity_json(te: TablaEquity, ruta: str | Path) -> Path:
    """Tabla de equity en JSON compacto (pensado para la web de la Fase 4).

    Estructura: ``equity[métrica][lance][i_mano] = [pos1, pos2, pos3, pos4]``.
    """
    ruta = _preparar(ruta)
    tabla = te.tabla
    metricas = {"p_se_juega": te.se_juega, "p_gana_individual": te.gana_individual,
                "p_gana_pareja": te.gana_pareja, "tantos_netos": te.tantos_netos}
    datos = {
        "variante": tabla.reglas.variante.value,
        "reglas": repr(tabla.reglas),
        "posiciones": list(POSICIONES),
        "lances": [l.value for l in Lance],
        "manos": [m.texto(tabla.baraja) for m in tabla.manos],
        "probabilidad_mano": [round(float(p), 8) for p in tabla.probabilidad],
        "equity": {
            nombre: {lance.value: np.round(array[:, :, l], 6).tolist()
                     for l, lance in enumerate(Lance)}
            for nombre, array in metricas.items()
        },
    }
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    return ruta


@dataclass(frozen=True)
class FilaRanking:
    puesto: int
    mano: str
    probabilidad_mano: float
    equity: EquityLance
    percentil: float
    """Probabilidad de recibir una mano con menor equity individual (0-1)."""


def ranking(te: TablaEquity, lance: Lance, posicion: int) -> list[FilaRanking]:
    """Manos ordenadas por equity individual en un lance y posición.

    Los empates de equity individual se desempatan por equity de pareja.
    """
    l = list(Lance).index(lance)
    ind = te.gana_individual[:, posicion - 1, l]
    par = te.gana_pareja[:, posicion - 1, l]
    orden = np.lexsort((-par, -ind))
    prob = te.tabla.probabilidad
    filas = []
    for puesto, i in enumerate(orden, start=1):
        percentil = float(prob[ind < ind[i]].sum())
        filas.append(FilaRanking(puesto, te.tabla.manos[i].texto(te.tabla.baraja),
                                 float(prob[i]), te.de(int(i), posicion, lance), percentil))
    return filas


def exportar_rankings_csv(te: TablaEquity, ruta: str | Path) -> Path:
    """Todos los rankings (lance × posición) en un único CSV largo."""
    ruta = _preparar(ruta)
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["lance", "posicion", "puesto", "mano", "probabilidad_mano",
                    "p_gana_individual", "p_gana_pareja", "tantos_netos", "percentil"])
        for lance in Lance:
            for p in POSICIONES:
                for r in ranking(te, lance, p):
                    w.writerow([lance.value, p, r.puesto, r.mano, f"{r.probabilidad_mano:.8f}",
                                f"{r.equity.p_gana_individual:.6f}",
                                f"{r.equity.p_gana_pareja:.6f}",
                                f"{r.equity.tantos_netos:.6f}", f"{r.percentil:.6f}"])
    return ruta


def probabilidades_mesa(te: TablaEquity) -> dict[str, float]:
    """Probabilidades de mesa, exactas, promediando la tabla de equity.

    P(el jugador en la posición p gana) = Σ_manos P(mano)·P(gana | mano, p).
    """
    prob = te.tabla.probabilidad[:, None]
    resultado: dict[str, float] = {}
    for l, lance in enumerate(Lance):
        se_juega = float((prob[:, 0] * te.se_juega[:, 0, l]).sum())
        resultado[f"{lance.value}: se juega"] = se_juega
        for p in POSICIONES:
            resultado[f"{lance.value}: gana el jugador {p}"] = float(
                (prob[:, 0] * te.gana_individual[:, p - 1, l]).sum())
        resultado[f"{lance.value}: gana la pareja 1-3"] = float(
            (prob[:, 0] * te.gana_pareja[:, 0, l]).sum())
        resultado[f"{lance.value}: tantos netos pareja 1-3"] = float(
            (prob[:, 0] * te.tantos_netos[:, 0, l]).sum())
    resultado["total: tantos netos pareja 1-3"] = float(
        (prob[:, 0] * te.tantos_netos[:, 0, :].sum(axis=1)).sum())
    return resultado


def graficar_posicion(te: TablaEquity, ruta: str | Path) -> Path:
    """Equity individual de cada mano siendo mano (pos. 1) frente a postre (pos. 4)."""
    plt = _pyplot()
    ruta = _preparar(ruta)
    lances = [Lance.GRANDE, Lance.CHICA, Lance.PARES, Lance.JUEGO]
    fig, ejes = plt.subplots(1, 4, figsize=(16, 4.3))
    for ax, lance in zip(ejes, lances):
        l = list(Lance).index(lance)
        x, y = te.gana_individual[:, 0, l], te.gana_individual[:, 3, l]
        ax.plot([0, 1], [0, 1], color="#bdc3c7", lw=1)
        ax.scatter(x, y, s=10, alpha=0.6, color="#2c3e50")
        ax.set(title=lance.value.capitalize(), xlabel="P(gana) siendo mano",
               ylabel="P(gana) siendo postre", xlim=(0, 1), ylim=(0, 1), aspect="equal")
    fig.suptitle("Equity individual por mano: posición 1 frente a posición 4 "
                 "(bajo la diagonal = la posición pesa)")
    fig.tight_layout()
    fig.savefig(ruta, dpi=120)
    plt.close(fig)
    return ruta


def graficar_condicion(sin: EquityMano, con: EquityMano, ruta: str | Path) -> Path:
    """Compara la equity de pareja de una mano sin información y con una condición."""
    plt = _pyplot()
    ruta = _preparar(ruta)
    lances = list(Lance)
    x = np.arange(len(lances))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))
    for ax, attr, titulo in ((ax1, "p_gana_pareja", "P(gana la pareja)"),
                             (ax2, "tantos_netos", "Tantos netos esperados (en paso)")):
        ax.bar(x - 0.2, [getattr(sin.por_lance[l], attr) for l in lances], 0.4,
               label="sin información", color="#95a5a6")
        ax.bar(x + 0.2, [getattr(con.por_lance[l], attr) for l in lances], 0.4,
               label=con.descripcion_condiciones, color="#c0392b")
        ax.set_xticks(x, [l.value for l in lances])
        ax.set_title(titulo)
        ax.axhline(0, color="black", lw=0.8)
    ax1.legend()
    fig.suptitle(f"{sin.texto_mano} en posición {sin.posicion}")
    fig.tight_layout()
    fig.savefig(ruta, dpi=120)
    plt.close(fig)
    return ruta


def _preparar(ruta: str | Path) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return ruta


def _pyplot():
    import matplotlib

    matplotlib.use("Agg")  # sin ventana: solo se guarda el fichero
    import matplotlib.pyplot as plt

    return plt


def graficar_distribucion(tabla: TablaManos, ruta: str | Path) -> Path:
    """Gráfica de la distribución exacta de sumas y de jugadas de pares."""
    plt = _pyplot()
    ruta = _preparar(ruta)
    sumas = distribucion_sumas(tabla)
    pares = {p.name.replace("_", " ").capitalize(): probabilidad_exacta(tabla, tabla.jugada_pares == p)
             for p in Pares}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5), gridspec_kw={"width_ratios": [3, 1]})
    colores = ["#c0392b" if s >= 31 else "#7f8c8d" for s in sumas]
    ax1.bar(list(sumas), list(sumas.values()), color=colores)
    ax1.set(title=f"Suma de la mano ({tabla.reglas.variante.value}); en rojo, con juego",
            xlabel="Suma", ylabel="Probabilidad")
    ax2.bar(list(pares), list(pares.values()), color="#2c3e50")
    ax2.set(title="Pares", ylabel="Probabilidad")
    ax2.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(ruta, dpi=120)
    plt.close(fig)
    return ruta
