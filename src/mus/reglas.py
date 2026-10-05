"""Configuración de reglas del mus.

Todas las reglas que varían según la zona se concentran en :class:`ReglasMus`,
un objeto inmutable (y por tanto *hashable*) que se pasa a todas las funciones
del motor. Ser hashable permite cachear las tablas precalculadas por reglas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Variante(str, Enum):
    """Variante de baraja."""

    OCHO_REYES = "8reyes"
    """Los treses cuentan como Reyes y los doses como Ases (8 Reyes, 8 Ases)."""

    CUATRO_REYES = "4reyes"
    """Cada carta vale lo que es: 4 Reyes, 4 Treses, 4 Doses, 4 Ases."""


@dataclass(frozen=True)
class Puntuacion:
    """Tantos que vale cada lance cuando se cobra sin envite (en paso).

    En pares y juego, la pareja ganadora cobra las jugadas de **ambos**
    compañeros; la perdedora no cobra nada.
    """

    grande: int = 1
    chica: int = 1
    par: int = 1
    medias: int = 2
    duples: int = 3
    juego_31: int = 3
    juego_otro: int = 2
    juego_31_real: int = 3
    punto: int = 1


@dataclass(frozen=True)
class ReglasMus:
    """Reglas configurables de una partida de mus.

    Atributos:
        variante: baraja de 8 reyes (por defecto) o de 4 reyes.
        orden_juego: sumas con juego ordenadas de mejor a peor.
        treinta_y_una_real: si está activa, la composición
            ``composicion_31_real`` gana a cualquier otra 31.
        composicion_31_real: cartas de la 31 real, en la misma notación que
            acepta :func:`mus.cartas.parsear_mano`.
        puntuacion: tantos de cada jugada.
        tantos_partida: tantos necesarios para ganar un juego.
    """

    variante: Variante = Variante.OCHO_REYES
    orden_juego: tuple[int, ...] = (31, 32, 40, 37, 36, 35, 34, 33)
    treinta_y_una_real: bool = False
    composicion_31_real: str = "7 7 7 S"
    puntuacion: Puntuacion = field(default_factory=Puntuacion)
    tantos_partida: int = 40

    def __post_init__(self) -> None:
        if len(set(self.orden_juego)) != len(self.orden_juego):
            raise ValueError("orden_juego tiene sumas repetidas")
        if 31 not in self.orden_juego:
            raise ValueError("orden_juego debe contener la 31")
        if any(s < 31 or s > 40 for s in self.orden_juego):
            raise ValueError("Las sumas de orden_juego deben estar entre 31 y 40")


REGLAS_POR_DEFECTO = ReglasMus()
