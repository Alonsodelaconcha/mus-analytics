"""Baraja, rangos y representación canónica de las manos.

Como el palo no importa, una mano se representa por cuántas cartas tiene de
cada rango (un vector de conteos). Esa representación es canónica: dos manos
con las mismas cartas, recibidas en cualquier orden, son el mismo objeto.

Los rangos se numeran de 0 (el más bajo, el As) hacia arriba, de modo que un
número de rango mayor significa una carta mejor para la grande.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations_with_replacement
from math import comb, prod

from mus.reglas import REGLAS_POR_DEFECTO, ReglasMus, Variante

CARTAS_POR_MANO = 4
BASE_CODIGO = CARTAS_POR_MANO + 1
"""Base del código numérico de una mano: cada conteo está entre 0 y 4."""


@dataclass(frozen=True)
class Baraja:
    """Rangos efectivos de una variante, de menor a mayor.

    Atributos:
        simbolos: símbolo de cada rango (``A``, ``4``, ..., ``S``, ``C``, ``R``).
        copias: número de cartas de cada rango en la baraja.
        valores: valor de cada rango para juego y punto.
        alias: otros símbolos aceptados al leer una mano y el rango al que
            equivalen (por ejemplo, en 8 reyes el ``3`` es un ``R``).
    """

    simbolos: tuple[str, ...]
    copias: tuple[int, ...]
    valores: tuple[int, ...]
    alias: tuple[tuple[str, str], ...]

    @property
    def n_rangos(self) -> int:
        return len(self.simbolos)

    @property
    def total_cartas(self) -> int:
        return sum(self.copias)

    def indice(self, token: str) -> int:
        """Rango correspondiente a un símbolo (admite alias, sin distinguir mayúsculas)."""
        t = token.strip().upper()
        t = dict(self.alias).get(t, t)
        try:
            return self.simbolos.index(t)
        except ValueError:
            validos = ", ".join(self.simbolos + tuple(a for a, _ in self.alias))
            raise ValueError(f"Carta desconocida: {token!r}. Válidas: {validos}") from None

    def cartas(self) -> tuple[int, ...]:
        """Las 40 cartas de la baraja como rangos (con repeticiones)."""
        return tuple(r for r, n in enumerate(self.copias) for _ in range(n))

    def admite(self, mano: Mano) -> bool:
        """True si la baraja tiene cartas suficientes para formar la mano."""
        return len(mano.conteos) == self.n_rangos and all(
            k <= n for k, n in zip(mano.conteos, self.copias)
        )

    def combinaciones(self, mano: Mano) -> int:
        """Número de manos físicas (con palo) que dan esta mano: prod C(n_r, k_r)."""
        return prod(comb(n, k) for n, k in zip(self.copias, mano.conteos))


_ALIAS_NUMERICOS = (("1", "A"), ("10", "S"), ("11", "C"), ("12", "R"))

_BARAJAS: dict[Variante, Baraja] = {
    Variante.OCHO_REYES: Baraja(
        simbolos=("A", "4", "5", "6", "7", "S", "C", "R"),
        copias=(8, 4, 4, 4, 4, 4, 4, 8),
        valores=(1, 4, 5, 6, 7, 10, 10, 10),
        alias=_ALIAS_NUMERICOS + (("2", "A"), ("3", "R")),
    ),
    Variante.CUATRO_REYES: Baraja(
        simbolos=("A", "2", "3", "4", "5", "6", "7", "S", "C", "R"),
        copias=(4,) * 10,
        valores=(1, 2, 3, 4, 5, 6, 7, 10, 10, 10),
        alias=_ALIAS_NUMERICOS,
    ),
}


def baraja_de(reglas: ReglasMus = REGLAS_POR_DEFECTO) -> Baraja:
    """Baraja asociada a la variante de las reglas."""
    return _BARAJAS[reglas.variante]


@dataclass(frozen=True)
class Mano:
    """Mano de 4 cartas representada por sus conteos por rango.

    ``conteos[r]`` es el número de cartas de rango ``r``. Es inmutable y
    hashable, así que se puede usar como clave de diccionario.
    """

    conteos: tuple[int, ...]

    def __post_init__(self) -> None:
        if sum(self.conteos) != CARTAS_POR_MANO or min(self.conteos) < 0:
            raise ValueError(f"Una mano debe tener {CARTAS_POR_MANO} cartas: {self.conteos}")

    @classmethod
    def desde_rangos(cls, rangos: tuple[int, ...] | list[int], n_rangos: int) -> Mano:
        """Construye la mano a partir de una lista de rangos en cualquier orden."""
        conteos = [0] * n_rangos
        for r in rangos:
            conteos[r] += 1
        return cls(tuple(conteos))

    @property
    def rangos(self) -> tuple[int, ...]:
        """Rangos de las 4 cartas, de mayor a menor."""
        return tuple(
            r for r in reversed(range(len(self.conteos))) for _ in range(self.conteos[r])
        )

    @property
    def codigo(self) -> int:
        """Entero único de la mano: conteos leídos como número en base 5.

        Tiene una propiedad útil para vectorizar: es la suma de ``5**rango``
        de cada carta, así que se calcula sumando sin contar nada.
        """
        return sum(k * BASE_CODIGO**r for r, k in enumerate(self.conteos))

    def texto(self, baraja: Baraja) -> str:
        """Representación legible, de mayor a menor (p. ej. ``"R R C 5"``)."""
        return " ".join(baraja.simbolos[r] for r in self.rangos)


def parsear_mano(texto: str, reglas: ReglasMus = REGLAS_POR_DEFECTO) -> Mano:
    """Lee una mano escrita como ``"R R C 5"``, ``"R,R,C,5"`` o ``"RRC5"``.

    Acepta los símbolos de la baraja, sus alias numéricos (``1``, ``10``,
    ``11``, ``12``) y, en 8 reyes, ``3`` como Rey y ``2`` como As.

    Raises:
        ValueError: si hay cartas desconocidas, no son 4 o la baraja no tiene
            suficientes copias de alguna.
    """
    baraja = baraja_de(reglas)
    tokens = [t for t in re.split(r"[\s,;]+", texto.strip()) if t]
    if len(tokens) == 1 and len(tokens[0]) == CARTAS_POR_MANO:
        tokens = list(tokens[0])
    if len(tokens) != CARTAS_POR_MANO:
        raise ValueError(f"Se esperaban {CARTAS_POR_MANO} cartas y hay {len(tokens)}: {texto!r}")
    mano = Mano.desde_rangos([baraja.indice(t) for t in tokens], baraja.n_rangos)
    if not baraja.admite(mano):
        raise ValueError(f"La baraja no tiene cartas suficientes para {texto!r}")
    return mano


def enumerar_manos(reglas: ReglasMus = REGLAS_POR_DEFECTO) -> list[Mano]:
    """Todas las manos distintas posibles (330 en 8 reyes, 715 en 4 reyes).

    Son los multiconjuntos de 4 rangos que la baraja puede formar, ordenados
    por su código.
    """
    baraja = baraja_de(reglas)
    manos = (
        Mano.desde_rangos(c, baraja.n_rangos)
        for c in combinations_with_replacement(range(baraja.n_rangos), CARTAS_POR_MANO)
    )
    return sorted((m for m in manos if baraja.admite(m)), key=lambda m: m.codigo)
