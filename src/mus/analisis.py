"""Distribuciones exactas, verificación contra Monte Carlo y exportación.

Cada métrica se define una sola vez como una *máscara* booleana sobre las
manos de la tabla. Su valor exacto es la suma de probabilidades de las manos
marcadas, y su estimación Monte Carlo es la frecuencia de esas mismas manos
en una muestra. Usar la misma definición para ambos garantiza que la
comparación mide el muestreo y los pesos, no dos implementaciones distintas.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

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


def graficar_distribucion(tabla: TablaManos, ruta: str | Path) -> Path:
    """Gráfica de la distribución exacta de sumas y de jugadas de pares."""
    import matplotlib

    matplotlib.use("Agg")  # sin ventana: solo se guarda el fichero
    import matplotlib.pyplot as plt

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
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
