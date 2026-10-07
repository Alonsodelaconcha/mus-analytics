"""Calibración de λ (cuánto cortan los rivales) con partidas reales.

El escenario de "rivales razonables" de la Fase 3c tiene un parámetro, λ
(``factor_corte``), que escala cuánto cortan los demás: λ = 0 es "nadie corta"
y λ = 1 los rivales razonables. Las decisiones dudosas dependen de él. La forma
de fijarlo es medir en partidas reales en qué proporción de manos hay mus en la
primera ronda y buscar el λ con el que el modelo da esa misma proporción.

Los datos se apuntan en ``datos/mus_real.csv`` (una fila por sesión). Este
módulo **no cambia nada**: informa del λ compatible con los datos y de su
incertidumbre. Con pocas manos el intervalo es tan ancho que no sirve; se
recomienda decidir con al menos :data:`MANOS_RECOMENDADAS`.

Limitación: λ resume en un número cómo cortan los jugadores. Los jugadores
reales no cortan exactamente como "rivales razonables escalados"; dependen
también del marcador, las señas y el estilo. Es una calibración gruesa.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from mus.reglas import REGLAS_POR_DEFECTO, ReglasMus
from mus.simulacion import Estimacion

RUTA_DATOS = Path("datos/mus_real.csv")
MANOS_RECOMENDADAS = 40
LAMBDAS = tuple(round(0.1 * i, 1) for i in range(11))


@dataclass(frozen=True)
class Observacion:
    """Manos observadas en partidas reales y en cuántas hubo mus en la primera ronda."""

    manos: int
    con_mus: int

    def __post_init__(self) -> None:
        if self.manos <= 0 or not 0 <= self.con_mus <= self.manos:
            raise ValueError("Hace falta 0 <= manos con mus <= manos, y al menos una mano")

    def estimacion(self, confianza: float = 0.95) -> Estimacion:
        return Estimacion(self.con_mus, self.manos, confianza)


def leer_observaciones(ruta: str | Path = RUTA_DATOS) -> Observacion:
    """Suma las sesiones del CSV (columnas ``manos`` y ``con_mus``)."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise ValueError(f"No existe {ruta}: créalo con columnas sesion,fecha,manos,con_mus,notas")
    manos = con_mus = 0
    with ruta.open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            manos += int(fila["manos"])
            con_mus += int(fila["con_mus"])
    return Observacion(manos, con_mus)


def curva_hay_mus(reglas: ReglasMus = REGLAS_POR_DEFECTO,
                  lambdas: tuple[float, ...] = LAMBDAS) -> list[tuple[float, float]]:
    """P(hay mus en la primera ronda) del modelo para cada λ (decreciente en λ).

    La primera vez simula cada λ (~15 s cada uno); después sale de la caché.
    """
    from mus.cortar import mesa_rivales_razonables

    return [(l, mesa_rivales_razonables(reglas, factor_corte=l).p_hay_mus) for l in lambdas]


def lambda_para(p: float, curva: list[tuple[float, float]]) -> tuple[float, bool]:
    """λ con el que el modelo da P(hay mus) = p, interpolando la curva.

    Returns:
        (λ, dentro): ``dentro`` es False si p queda fuera del rango del modelo y
        λ se ha recortado a 0 o a 1.
    """
    lambdas = [l for l, _ in curva]
    ps = [q for _, q in curva]
    if p >= ps[0]:
        return lambdas[0], p <= ps[0]
    if p <= ps[-1]:
        return lambdas[-1], p >= ps[-1]
    for (l0, p0), (l1, p1) in zip(curva, curva[1:]):
        if p1 <= p <= p0:
            return l0 + (l1 - l0) * (p0 - p) / (p0 - p1), True
    raise ValueError("La curva debe ser decreciente en λ")


@dataclass(frozen=True)
class Calibracion:
    observacion: Observacion
    p_observada: Estimacion
    lambda_estimada: float
    lambda_intervalo: tuple[float, float]
    dentro_del_rango: bool
    """False si la proporción observada queda fuera de lo que el modelo puede dar
    (más mus que con λ = 0, o menos que con λ = 1)."""
    intervalo_recortado: bool
    """True si algún extremo del intervalo de λ se ha recortado a 0 o 1."""

    @property
    def suficiente(self) -> bool:
        return self.observacion.manos >= MANOS_RECOMENDADAS


def calibrar(observacion: Observacion, curva: list[tuple[float, float]],
             confianza: float = 0.95) -> Calibracion:
    """λ compatible con la proporción de mus observada, con su intervalo.

    El intervalo de λ sale de invertir el intervalo de Wilson de la proporción:
    más mus observado corresponde a un λ menor.
    """
    p = observacion.estimacion(confianza)
    bajo, alto = p.intervalo
    lam, dentro = lambda_para(p.p, curva)
    (desde, dentro_alto), (hasta, dentro_bajo) = lambda_para(alto, curva), lambda_para(bajo, curva)
    return Calibracion(observacion, p, lam, (desde, hasta), dentro,
                       not (dentro_alto and dentro_bajo))
