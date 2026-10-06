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


@dataclass(frozen=True)
class EstimacionMedia:
    """Media estimada por Monte Carlo con intervalo normal (TCL).

    Para medias de variables acotadas como los tantos de un lance, con n
    grande el intervalo normal es adecuado.
    """

    media: float
    desviacion: float
    n: int
    confianza: float = 0.95

    @classmethod
    def de_muestra(cls, valores: np.ndarray, confianza: float = 0.95) -> EstimacionMedia:
        if len(valores) < 2:
            raise ValueError("Se necesitan al menos 2 valores")
        return cls(float(valores.mean()), float(valores.std(ddof=1)), len(valores), confianza)

    @property
    def intervalo(self) -> tuple[float, float]:
        z = NormalDist().inv_cdf(0.5 + self.confianza / 2)
        radio = z * self.desviacion / sqrt(self.n)
        return self.media - radio, self.media + radio

    def contiene(self, valor: float) -> bool:
        bajo, alto = self.intervalo
        return bajo <= valor <= alto

    def __str__(self) -> str:
        bajo, alto = self.intervalo
        return f"{self.media:+.4f} [{bajo:+.4f}, {alto:+.4f}]"


def _extraer(
    n: int, n_manos: int, tabla: TablaManos, rng: np.random.Generator, tamano_lote: int,
    mazo: np.ndarray | None = None,
) -> np.ndarray:
    """``n`` repartos de ``n_manos`` manos sin reemplazo: array (n, n_manos) de índices.

    ``mazo`` permite repartir de un mazo incompleto (rangos de las cartas que
    quedan); por defecto, la baraja entera.
    """
    if mazo is None:
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


def repartir_con_mano(
    n: int, tabla: TablaManos, rng: np.random.Generator, indice_mano: int, posicion: int,
    tamano_lote: int = TAMANO_LOTE,
) -> np.ndarray:
    """``n`` repartos con la mano ``indice_mano`` fija en ``posicion`` (1-4).

    Las otras tres manos salen de las 36 cartas restantes. Devuelve un array
    (n, 4) en orden de juego, como :func:`repartir`.
    """
    if not 1 <= posicion <= JUGADORES:
        raise ValueError("La posición debe estar entre 1 y 4")
    restantes = np.array(tabla.baraja.copias) - tabla.conteos[indice_mano]
    mazo = np.repeat(np.arange(tabla.baraja.n_rangos), restantes).astype(np.int8)
    otras = _extraer(n, JUGADORES - 1, tabla, rng, tamano_lote, mazo)
    return np.insert(otras, posicion - 1, indice_mano, axis=1)


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


def tantos_lance(
    tabla: TablaManos, repartos: np.ndarray, lance: Lance, ganador: np.ndarray
) -> np.ndarray:
    """Tantos que cobra en paso la pareja ganadora de cada reparto (0 si nadie gana).

    En pares y juego son las jugadas de los dos compañeros de la pareja
    ganadora; en el resto, los tantos fijos del lance.
    """
    valor = tabla.valor_jugada(lance)
    if valor is None:
        tantos = np.full(len(repartos), tabla.tantos_fijos(lance), dtype=np.int64)
    else:
        v = valor[repartos].astype(np.int64)
        pareja1, pareja2 = v[:, 0] + v[:, 2], v[:, 1] + v[:, 3]
        tantos = np.where(ganador % 2 == 1, pareja1, pareja2)
    return np.where(ganador > 0, tantos, 0)
