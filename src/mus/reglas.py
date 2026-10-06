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


class Rebarajado(str, Enum):
    """Qué cartas se barajan para seguir robando cuando se agota el mazo."""

    DESCARTES_ANTERIORES = "descartes_anteriores"
    """Los descartes de las rondas anteriores, no los de la ronda en curso (por defecto)."""

    TODOS_LOS_DESCARTES = "todos_los_descartes"
    """Todos los descartes hechos hasta ese momento, incluidos los de la ronda en curso."""


@dataclass(frozen=True)
class ReglasDescarte:
    """Reglas del mus (descartes).

    Atributos:
        minimo, maximo: cartas que hay que descartar si hay mus. Por defecto
            de 1 a 4: quedarse servido equivale a cortar.
        rebarajado: qué se baraja cuando se agota el mazo (solo puede pasar a
            partir de la segunda ronda: en la primera se piden como mucho 16
            cartas y quedan 24).
        limite_rondas: rondas de mus permitidas (``None`` = sin límite).

    Se roba siempre en orden desde la mano.
    """

    minimo: int = 1
    maximo: int = 4
    rebarajado: Rebarajado = Rebarajado.DESCARTES_ANTERIORES
    limite_rondas: int | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.minimo <= self.maximo <= 4:
            raise ValueError("Debe cumplirse 0 <= minimo <= maximo <= 4")
        if self.limite_rondas is not None and self.limite_rondas < 1:
            raise ValueError("limite_rondas debe ser positivo o None")


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
        descarte: reglas del mus (cuántas cartas se descartan, mazo agotado).
    """

    variante: Variante = Variante.OCHO_REYES
    orden_juego: tuple[int, ...] = (31, 32, 40, 37, 36, 35, 34, 33)
    treinta_y_una_real: bool = False
    composicion_31_real: str = "7 7 7 S"
    puntuacion: Puntuacion = field(default_factory=Puntuacion)
    tantos_partida: int = 40
    descarte: ReglasDescarte = field(default_factory=ReglasDescarte)

    def __post_init__(self) -> None:
        if len(set(self.orden_juego)) != len(self.orden_juego):
            raise ValueError("orden_juego tiene sumas repetidas")
        if 31 not in self.orden_juego:
            raise ValueError("orden_juego debe contener la 31")
        if any(s < 31 or s > 40 for s in self.orden_juego):
            raise ValueError("Las sumas de orden_juego deben estar entre 31 y 40")


REGLAS_POR_DEFECTO = ReglasMus()
