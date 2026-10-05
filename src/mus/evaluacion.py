"""Evaluación de los lances y resolución de una mano entre 4 jugadores.

Diseño: cada lance tiene una función ``clave_*`` que convierte una mano en una
tupla de enteros comparable, de forma que **una clave mayor es una jugada
mejor**. ``None`` significa que la mano no participa en el lance (sin pares,
sin juego o, en punto, con juego). Comparar dos manos se reduce a comparar
sus claves, y los empates de clave se resuelven por posición.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, IntEnum
from functools import lru_cache

from mus.cartas import Mano, baraja_de, parsear_mano
from mus.reglas import REGLAS_POR_DEFECTO, ReglasMus

Clave = tuple[int, ...]

JUGADORES = 4


class Lance(Enum):
    """Los cinco lances, en orden de juego."""

    GRANDE = "grande"
    CHICA = "chica"
    PARES = "pares"
    JUEGO = "juego"
    PUNTO = "punto"


class Pares(IntEnum):
    """Categorías de pares, de peor a mejor."""

    SIN_PARES = 0
    PAR = 1
    MEDIAS = 2
    DUPLES = 3


# --- Claves por lance --------------------------------------------------------


def clave_grande(mano: Mano) -> Clave:
    """Cartas de mayor a menor: se comparan una a una."""
    return mano.rangos


def clave_chica(mano: Mano) -> Clave:
    """Cartas de menor a mayor, negadas: la mano más baja tiene la clave mayor."""
    return tuple(-r for r in reversed(mano.rangos))


def jugada_pares(mano: Mano) -> Pares:
    """Categoría de pares de la mano."""
    clave = clave_pares(mano)
    return Pares.SIN_PARES if clave is None else Pares(clave[0])


def clave_pares(mano: Mano) -> Clave | None:
    """Clave ``(categoría, rango_alto, rango_bajo)`` o ``None`` sin pares.

    - Par: solo cuenta el rango de la pareja; las cartas sueltas no importan.
    - Medias: rango del trío.
    - Duples: pareja alta y luego pareja baja. Cuatro iguales son duples de
      ese rango con pareja alta = pareja baja (RRRR > RRCC; RR44 > 5555).

    En par y medias se repite el rango para que todas las claves tengan la
    misma longitud; no altera ninguna comparación.
    """
    grupos = [(r, k) for r, k in enumerate(mano.conteos) if k >= 2]
    if not grupos:
        return None
    grupos.sort(reverse=True)  # rango más alto primero
    if len(grupos) == 2:
        return (Pares.DUPLES, grupos[0][0], grupos[1][0])
    rango, k = grupos[0]
    categoria = {2: Pares.PAR, 3: Pares.MEDIAS, 4: Pares.DUPLES}[k]
    return (categoria, rango, rango)


def suma(mano: Mano, reglas: ReglasMus = REGLAS_POR_DEFECTO) -> int:
    """Suma de valores de la mano para juego y punto."""
    valores = baraja_de(reglas).valores
    return sum(valores[r] * k for r, k in enumerate(mano.conteos))


@lru_cache(maxsize=None)
def _mano_31_real(reglas: ReglasMus) -> Mano:
    mano = parsear_mano(reglas.composicion_31_real, reglas)
    if suma(mano, reglas) != 31:
        raise ValueError(f"La 31 real {reglas.composicion_31_real!r} no suma 31")
    return mano


def es_31_real(mano: Mano, reglas: ReglasMus = REGLAS_POR_DEFECTO) -> bool:
    """True si la regla de 31 real está activa y la mano tiene esa composición."""
    return reglas.treinta_y_una_real and mano == _mano_31_real(reglas)


def clave_juego(mano: Mano, reglas: ReglasMus = REGLAS_POR_DEFECTO) -> Clave | None:
    """Prioridad de la suma según ``reglas.orden_juego``, o ``None`` sin juego.

    La 31 real (si está activa) recibe una prioridad por encima de todas.
    """
    s = suma(mano, reglas)
    if s < 31:
        return None
    orden = reglas.orden_juego
    if es_31_real(mano, reglas):
        return (len(orden) + 1,)
    if s not in orden:
        raise ValueError(f"La suma {s} tiene juego pero no aparece en orden_juego {orden}")
    return (len(orden) - orden.index(s),)


def clave_punto(mano: Mano, reglas: ReglasMus = REGLAS_POR_DEFECTO) -> Clave | None:
    """Suma de la mano si no tiene juego; ``None`` si lo tiene."""
    s = suma(mano, reglas)
    return None if s >= 31 else (s,)


def clave(lance: Lance, mano: Mano, reglas: ReglasMus = REGLAS_POR_DEFECTO) -> Clave | None:
    """Clave de la mano para cualquier lance."""
    match lance:
        case Lance.GRANDE:
            return clave_grande(mano)
        case Lance.CHICA:
            return clave_chica(mano)
        case Lance.PARES:
            return clave_pares(mano)
        case Lance.JUEGO:
            return clave_juego(mano, reglas)
        case Lance.PUNTO:
            return clave_punto(mano, reglas)


# --- Puntuación de jugadas ---------------------------------------------------


def puntos_pares(mano: Mano, reglas: ReglasMus = REGLAS_POR_DEFECTO) -> int:
    """Tantos que vale la jugada de pares de la mano (0 sin pares)."""
    p = reglas.puntuacion
    return {
        Pares.SIN_PARES: 0,
        Pares.PAR: p.par,
        Pares.MEDIAS: p.medias,
        Pares.DUPLES: p.duples,
    }[jugada_pares(mano)]


def puntos_juego(mano: Mano, reglas: ReglasMus = REGLAS_POR_DEFECTO) -> int:
    """Tantos que vale el juego de la mano (0 sin juego)."""
    s = suma(mano, reglas)
    if s < 31:
        return 0
    p = reglas.puntuacion
    if es_31_real(mano, reglas):
        return p.juego_31_real
    return p.juego_31 if s == 31 else p.juego_otro


# --- Resolución entre jugadores ----------------------------------------------


def pareja_de(posicion: int) -> int:
    """Pareja de una posición (1-4): pareja 1 = (1, 3), pareja 2 = (2, 4)."""
    return 1 if posicion % 2 == 1 else 2


def mejor_posicion(claves: Sequence[Clave | None]) -> int | None:
    """Posición (1-based) de la mejor clave; ``None`` si nadie participa.

    Las claves van en orden de juego (mano primero). Como solo se sustituye
    al ganador con una clave *estrictamente* mayor, los empates los gana el
    jugador más cercano a la mano.
    """
    mejor: int | None = None
    for i, c in enumerate(claves):
        if c is not None and (mejor is None or c > claves[mejor]):
            mejor = i
    return None if mejor is None else mejor + 1


@dataclass(frozen=True)
class ResultadoLance:
    """Resultado de un lance cobrado en paso (sin envites).

    Atributos:
        lance: lance resuelto.
        se_juega: False si nadie participa (sin pares, sin juego) o, en punto,
            si alguien tiene juego.
        ganador: posición ganadora (1-4) o ``None``.
        pareja: pareja ganadora (1 o 2) o ``None``.
        tantos: tantos que cobra la pareja ganadora.
    """

    lance: Lance
    se_juega: bool
    ganador: int | None
    pareja: int | None
    tantos: int


def resolver_lance(
    manos: Sequence[Mano], lance: Lance, reglas: ReglasMus = REGLAS_POR_DEFECTO
) -> ResultadoLance:
    """Resuelve un lance entre 4 manos dadas en orden de juego (1 = mano).

    En pares y juego, la pareja ganadora cobra las jugadas de ambos
    compañeros. El punto solo se juega si nadie tiene juego.
    """
    if len(manos) != JUGADORES:
        raise ValueError(f"Se necesitan {JUGADORES} manos")
    if lance is Lance.PUNTO and any(suma(m, reglas) >= 31 for m in manos):
        return ResultadoLance(lance, False, None, None, 0)

    ganador = mejor_posicion([clave(lance, m, reglas) for m in manos])
    if ganador is None:
        return ResultadoLance(lance, False, None, None, 0)

    pareja = pareja_de(ganador)
    companeros = [m for pos, m in enumerate(manos, start=1) if pareja_de(pos) == pareja]
    p = reglas.puntuacion
    match lance:
        case Lance.GRANDE:
            tantos = p.grande
        case Lance.CHICA:
            tantos = p.chica
        case Lance.PARES:
            tantos = sum(puntos_pares(m, reglas) for m in companeros)
        case Lance.JUEGO:
            tantos = sum(puntos_juego(m, reglas) for m in companeros)
        case Lance.PUNTO:
            tantos = p.punto
    return ResultadoLance(lance, True, ganador, pareja, tantos)


def resolver_mano(
    manos: Sequence[Mano], reglas: ReglasMus = REGLAS_POR_DEFECTO
) -> dict[Lance, ResultadoLance]:
    """Resuelve los cinco lances de una mano completa jugada en paso."""
    return {lance: resolver_lance(manos, lance, reglas) for lance in Lance}
