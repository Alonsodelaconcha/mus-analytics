"""Simulación Monte Carlo: reparto aleatorio de manos e intervalos de confianza.

El reparto está vectorizado: se barajan muchas copias del mazo a la vez
(``Generator.permuted`` por filas), se toman las primeras cartas y cada grupo
de 4 se convierte en un índice de la tabla sumando ``5**rango`` de sus cartas
(ver :attr:`mus.cartas.Mano.codigo`). No hay bucles de Python por reparto.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from math import sqrt
from statistics import NormalDist

import numpy as np

from mus.cartas import CARTAS_POR_MANO
from mus.evaluacion import JUGADORES, Lance
from mus.tablas import TablaManos, potencias_codigo

TAMANO_LOTE = 250_000
"""Repartos por lote: limita la memoria (lote x 40 cartas) sin perder velocidad."""


def generador(semilla: int | None = None) -> np.random.Generator:
    """Generador aleatorio reproducible (``None`` = semilla del sistema)."""
    return np.random.default_rng(semilla)


def intervalo_wilson(exitos: int, n: int, confianza: float = 0.95) -> tuple[float, float]:
    """Intervalo de Wilson para una proporción.

    Se prefiere al intervalo normal (p ± z·sqrt(p(1-p)/n)) porque no se sale
    de [0, 1] y se comporta bien con proporciones cercanas a 0 o 1, que aquí
    son frecuentes (p. ej. P(juego 40)).
    """
    if n <= 0:
        raise ValueError("n debe ser positivo")
    z = NormalDist().inv_cdf(0.5 + confianza / 2)
    p = exitos / n
    denominador = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / denominador
    radio = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominador
    # En los extremos el límite es exacto; se fija para evitar residuos de redondeo.
    bajo = 0.0 if exitos == 0 else max(0.0, centro - radio)
    alto = 1.0 if exitos == n else min(1.0, centro + radio)
    return bajo, alto


@dataclass(frozen=True)
class Estimacion:
    """Proporción estimada por Monte Carlo con su intervalo de confianza."""

    exitos: int
    n: int
    confianza: float = 0.95

    @property
    def p(self) -> float:
        return self.exitos / self.n

    @property
    def intervalo(self) -> tuple[float, float]:
        return intervalo_wilson(self.exitos, self.n, self.confianza)

    def contiene(self, valor: float) -> bool:
        bajo, alto = self.intervalo
        return bajo <= valor <= alto

    def __str__(self) -> str:
        bajo, alto = self.intervalo
        return f"{self.p:.5f} [{bajo:.5f}, {alto:.5f}]"


def _lotes(n: int, tamano: int) -> Iterator[int]:
    while n > 0:
        m = min(n, tamano)
        yield m
        n -= m


def _extraer(
    n: int, n_manos: int, tabla: TablaManos, rng: np.random.Generator, tamano_lote: int
) -> np.ndarray:
    """``n`` repartos de ``n_manos`` manos sin reemplazo: array (n, n_manos) de índices."""
    mazo = np.array(tabla.baraja.cartas(), dtype=np.int8)
    potencias = potencias_codigo(tabla.baraja)
    cartas_usadas = n_manos * CARTAS_POR_MANO
    resultado = np.empty((n, n_manos), dtype=np.int16)
    inicio = 0
    for m in _lotes(n, tamano_lote):
        barajados = rng.permuted(np.tile(mazo, (m, 1)), axis=1)[:, :cartas_usadas]
        codigos = potencias[barajados].reshape(m, n_manos, CARTAS_POR_MANO).sum(axis=2)
        resultado[inicio:inicio + m] = tabla.indices_de_codigos(codigos)
        inicio += m
    return resultado


def muestrear_manos(
    n: int, tabla: TablaManos, rng: np.random.Generator, tamano_lote: int = TAMANO_LOTE
) -> np.ndarray:
    """``n`` manos independientes de 4 cartas, cada una de un mazo completo."""
    return _extraer(n, 1, tabla, rng, tamano_lote)[:, 0]


def repartir(
    n: int, tabla: TablaManos, rng: np.random.Generator, tamano_lote: int = TAMANO_LOTE
) -> np.ndarray:
    """``n`` repartos completos: array (n, 4) de índices, columna 0 = mano."""
    return _extraer(n, JUGADORES, tabla, rng, tamano_lote)


def ganadores(fuerzas: np.ndarray) -> np.ndarray:
    """Posición ganadora (1-4) de cada reparto a partir de las fuerzas (n, 4).

    ``argmax`` devuelve la *primera* posición con el máximo, que es justo la
    regla de desempate (gana el más cercano a la mano). Devuelve 0 en los
    repartos en que nadie participa (todas las fuerzas 0).

    Ojo con el punto: su fuerza es 0 en las manos con juego, pero el lance
    solo se juega si *nadie* tiene juego. Para resolver lances usa
    :func:`ganadores_lance`, que ya aplica ese filtro.
    """
    ganador = fuerzas.argmax(axis=1) + 1
    ganador[fuerzas.max(axis=1) == 0] = 0
    return ganador


def ganadores_lance(tabla: TablaManos, repartos: np.ndarray, lance: Lance) -> np.ndarray:
    """Posición ganadora (1-4) de un lance en cada reparto; 0 si no se juega.

    ``repartos`` es un array (n, 4) de índices de mano **en orden de juego**
    (columna 0 = mano, columna 3 = postre), como el que devuelve
    :func:`repartir`. Es la versión vectorizada de
    :func:`mus.evaluacion.resolver_lance` y aplica el filtro del punto.
    """
    ganador = ganadores(tabla.fuerza[lance][repartos])
    if lance is Lance.PUNTO:
        ganador[tabla.tiene_juego[repartos].any(axis=1)] = 0
    return ganador
