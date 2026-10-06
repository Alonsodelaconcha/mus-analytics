"""Tablas de lookup de todas las manos distintas.

Se evalúa cada una de las 330 manos (715 en 4 reyes) una sola vez con las
funciones de :mod:`mus.evaluacion` y se guardan los resultados en arrays de
NumPy indexados por número de mano. A partir de aquí, el cálculo exacto y el
Monte Carlo trabajan con índices de mano y nunca vuelven a evaluar.

La pieza clave es la *fuerza* por lance: un entero denso (1 = la peor clave,
crece hacia las mejores, 0 = no participa) que conserva exactamente el orden
de las claves. Así, decidir quién gana un lance es un ``argmax`` vectorizado.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from mus.cartas import BASE_CODIGO, Baraja, Mano, baraja_de, enumerar_manos
from mus.evaluacion import (
    Clave,
    Lance,
    clave,
    jugada_pares,
    puntos_juego,
    puntos_pares,
    suma,
)
from mus.reglas import REGLAS_POR_DEFECTO, ReglasMus


def fuerzas_densas(claves: Sequence[Clave | None]) -> np.ndarray:
    """Convierte claves en enteros densos que conservan su orden.

    ``None`` se convierte en 0; la clave distinta más baja en 1, y así
    sucesivamente. Dos manos con la misma clave reciben la misma fuerza.
    """
    distintas = sorted({c for c in claves if c is not None})
    posicion = {c: i + 1 for i, c in enumerate(distintas)}
    return np.array([0 if c is None else posicion[c] for c in claves], dtype=np.int16)


@dataclass(frozen=True, eq=False)
class TablaManos:
    """Todas las manos distintas con sus evaluaciones precalculadas.

    Todos los arrays tienen una fila por mano, en el mismo orden que
    ``manos`` (ordenadas por código).

    Atributos:
        reglas, baraja: configuración con que se construyó la tabla.
        manos: manos distintas.
        codigos: código de cada mano (creciente, para ``searchsorted``).
        conteos: matriz (manos x rangos) de conteos.
        combinaciones: manos físicas de 40 cartas que dan cada mano.
        probabilidad: probabilidad exacta de recibir cada mano.
        fuerza: fuerza densa de cada mano en cada lance (0 = no participa).
        suma: suma para juego y punto.
        jugada_pares: categoría :class:`mus.evaluacion.Pares`.
        puntos_pares, puntos_juego: tantos de cada jugada.
    """

    reglas: ReglasMus
    baraja: Baraja
    manos: tuple[Mano, ...]
    codigos: np.ndarray
    conteos: np.ndarray
    combinaciones: np.ndarray
    probabilidad: np.ndarray
    fuerza: dict[Lance, np.ndarray]
    suma: np.ndarray
    jugada_pares: np.ndarray
    puntos_pares: np.ndarray
    puntos_juego: np.ndarray

    @property
    def n_manos(self) -> int:
        return len(self.manos)

    @property
    def tiene_juego(self) -> np.ndarray:
        return self.suma >= 31

    def valor_jugada(self, lance: Lance) -> np.ndarray | None:
        """Tantos de la jugada de cada mano en pares o juego; ``None`` en el resto.

        En pares y juego la pareja ganadora cobra la suma de las jugadas de
        ambos; en grande, chica y punto cobra unos tantos fijos.
        """
        return {Lance.PARES: self.puntos_pares, Lance.JUEGO: self.puntos_juego}.get(lance)

    def tantos_fijos(self, lance: Lance) -> int:
        """Tantos fijos de grande, chica o punto."""
        p = self.reglas.puntuacion
        fijos = {Lance.GRANDE: p.grande, Lance.CHICA: p.chica, Lance.PUNTO: p.punto}
        if lance not in fijos:
            raise ValueError(f"{lance.value} no tiene tantos fijos: usa valor_jugada")
        return fijos[lance]

    def indice(self, mano: Mano) -> int:
        """Índice de una mano en la tabla."""
        return int(self.indices_de_codigos(np.array([mano.codigo]))[0])

    def indices_de_codigos(self, codigos: np.ndarray) -> np.ndarray:
        """Convierte códigos de mano en índices de la tabla (vectorizado).

        Raises:
            ValueError: si algún código no corresponde a una mano válida.
        """
        idx = np.searchsorted(self.codigos, codigos)
        idx_seguro = np.minimum(idx, self.n_manos - 1)
        if not np.array_equal(self.codigos[idx_seguro], codigos):
            raise ValueError("Hay códigos que no corresponden a ninguna mano válida")
        return idx


def construir_tabla(reglas: ReglasMus = REGLAS_POR_DEFECTO) -> TablaManos:
    """Construye (y cachea por reglas) la tabla de todas las manos."""
    # La caché va en una función aparte que siempre recibe las reglas como
    # argumento posicional: lru_cache trataría f() y f(ReglasMus()) como
    # claves distintas y construiría la tabla dos veces.
    return _construir_tabla(reglas)


@lru_cache(maxsize=None)
def _construir_tabla(reglas: ReglasMus) -> TablaManos:
    baraja = baraja_de(reglas)
    manos = tuple(enumerar_manos(reglas))
    combinaciones = np.array([baraja.combinaciones(m) for m in manos], dtype=np.int64)
    tabla = TablaManos(
        reglas=reglas,
        baraja=baraja,
        manos=manos,
        codigos=np.array([m.codigo for m in manos], dtype=np.int64),
        conteos=np.array([m.conteos for m in manos], dtype=np.int8),
        combinaciones=combinaciones,
        probabilidad=combinaciones / combinaciones.sum(),
        fuerza={lance: fuerzas_densas([clave(lance, m, reglas) for m in manos]) for lance in Lance},
        suma=np.array([suma(m, reglas) for m in manos], dtype=np.int8),
        jugada_pares=np.array([jugada_pares(m) for m in manos], dtype=np.int8),
        puntos_pares=np.array([puntos_pares(m, reglas) for m in manos], dtype=np.int8),
        puntos_juego=np.array([puntos_juego(m, reglas) for m in manos], dtype=np.int8),
    )
    for array in (tabla.codigos, tabla.conteos, tabla.combinaciones, tabla.probabilidad,
                  tabla.suma, tabla.jugada_pares, tabla.puntos_pares, tabla.puntos_juego,
                  *tabla.fuerza.values()):
        array.flags.writeable = False  # la tabla está cacheada: que nadie la modifique
    return tabla


def potencias_codigo(baraja: Baraja) -> np.ndarray:
    """``5**rango`` por rango: el código de una mano es la suma sobre sus cartas."""
    return BASE_CODIGO ** np.arange(baraja.n_rangos, dtype=np.int64)
