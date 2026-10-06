"""Condiciones sobre la mano de otro jugador (información del compañero o de los rivales).

Una :class:`Condicion` es un predicado sobre una mano, evaluado de golpe como
una máscara booleana sobre todas las manos de la tabla. No es una lista
cerrada de señas: las señas de cada zona se definen después combinando
condiciones atómicas con ``&`` (y), ``|`` (o) y ``~`` (no).

Ejemplos::

    con_pares() & cuenta("R", minimo=2)      # pares y al menos dos reyes
    pares_entre(Pares.MEDIAS)                # medias o duples
    con_juego([31])                          # la 31
    parsear_condicion("pares>=medias, reyes>=2")
"""

from __future__ import annotations

import operator
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np

from mus.cartas import baraja_de, parsear_mano
from mus.evaluacion import Pares
from mus.reglas import REGLAS_POR_DEFECTO, ReglasMus
from mus.tablas import TablaManos


@dataclass(frozen=True)
class Condicion:
    """Predicado sobre una mano, con una descripción legible."""

    descripcion: str
    _funcion: Callable[[TablaManos], np.ndarray] = field(repr=False, compare=False)

    def mascara(self, tabla: TablaManos) -> np.ndarray:
        """Array booleano con una entrada por mano de la tabla."""
        m = np.asarray(self._funcion(tabla), dtype=bool)
        if m.shape != (tabla.n_manos,):
            raise ValueError(f"La condición {self.descripcion!r} no da una máscara por mano")
        return m

    def __and__(self, otra: Condicion) -> Condicion:
        return Condicion(f"{self.descripcion} y {otra.descripcion}",
                         lambda t: self.mascara(t) & otra.mascara(t))

    def __or__(self, otra: Condicion) -> Condicion:
        return Condicion(f"({self.descripcion} o {otra.descripcion})",
                         lambda t: self.mascara(t) | otra.mascara(t))

    def __invert__(self) -> Condicion:
        return Condicion(f"no ({self.descripcion})", lambda t: ~self.mascara(t))

    def renombrar(self, descripcion: str) -> Condicion:
        """La misma condición con otra descripción."""
        return Condicion(descripcion, self._funcion)

    def __str__(self) -> str:
        return self.descripcion


# --- Condiciones atómicas ----------------------------------------------------


def cualquiera() -> Condicion:
    """Sin información: cualquier mano."""
    return Condicion("cualquiera", lambda t: np.ones(t.n_manos, dtype=bool))


def pares_entre(minimo: Pares = Pares.PAR, maximo: Pares = Pares.DUPLES) -> Condicion:
    """Jugada de pares entre ``minimo`` y ``maximo`` (incluidos)."""
    nombre = (minimo.name.lower() if minimo == maximo
              else f"pares entre {minimo.name.lower()} y {maximo.name.lower()}")
    return Condicion(nombre, lambda t: (t.jugada_pares >= minimo) & (t.jugada_pares <= maximo))


def con_pares() -> Condicion:
    return Condicion("con pares", lambda t: t.jugada_pares > Pares.SIN_PARES)


def sin_pares() -> Condicion:
    return Condicion("sin pares", lambda t: t.jugada_pares == Pares.SIN_PARES)


def con_juego(sumas: Iterable[int] | None = None) -> Condicion:
    """Con juego; si se dan ``sumas``, solo esas (p. ej. ``[31]``)."""
    if sumas is None:
        return Condicion("con juego", lambda t: t.tiene_juego)
    sumas = sorted(set(sumas))
    return Condicion(f"juego {'/'.join(map(str, sumas))}",
                     lambda t: np.isin(t.suma, sumas) & t.tiene_juego)


def sin_juego() -> Condicion:
    return Condicion("sin juego", lambda t: ~t.tiene_juego)


def suma_entre(minimo: int, maximo: int) -> Condicion:
    """Suma de la mano (para juego o punto) entre ``minimo`` y ``maximo``."""
    return Condicion(f"suma entre {minimo} y {maximo}",
                     lambda t: (t.suma >= minimo) & (t.suma <= maximo))


def cuenta(simbolo: str, minimo: int = 0, maximo: int = 4) -> Condicion:
    """Entre ``minimo`` y ``maximo`` cartas del rango ``simbolo`` (p. ej. ``"R"``).

    En 8 reyes, ``cuenta("R", 2)`` cuenta reyes y treses juntos.
    """
    def mascara(t: TablaManos) -> np.ndarray:
        n = t.conteos[:, t.baraja.indice(simbolo)]
        return (n >= minimo) & (n <= maximo)
    return Condicion(f"{minimo}-{maximo} cartas {simbolo}", mascara)


def manos(*textos: str) -> Condicion:
    """Una de las manos dadas, p. ej. ``manos("R R R R", "R R R C")``."""
    def mascara(t: TablaManos) -> np.ndarray:
        objetivo = {parsear_mano(x, t.reglas) for x in textos}
        return np.array([m in objetivo for m in t.manos])
    return Condicion("mano en {" + ", ".join(textos) + "}", mascara)


# --- Sintaxis de texto (CLI) -------------------------------------------------

_OPERADORES: dict[str, Callable] = {
    ">=": operator.ge, "<=": operator.le, "!=": operator.ne, "==": operator.eq,
    "=": operator.eq, ">": operator.gt, "<": operator.lt,
}

NOMBRES_RANGO = {
    "reyes": "R", "caballos": "C", "sotas": "S", "sietes": "7", "seises": "6",
    "cincos": "5", "cuatros": "4", "treses": "3", "doses": "2", "ases": "A",
}

_CATEGORIAS_PARES = {"sin_pares": Pares.SIN_PARES, "par": Pares.PAR,
                     "medias": Pares.MEDIAS, "duples": Pares.DUPLES}

_PALABRAS = {
    "sin_pares": sin_pares, "con_pares": con_pares, "pares": con_pares,
    "sin_juego": sin_juego, "con_juego": con_juego, "juego": con_juego,
    "cualquiera": cualquiera,
}

_CLAUSULA = re.compile(r"^([a-z_]+)\s*(>=|<=|!=|==|=|>|<)\s*([a-z0-9_]+)$")

AYUDA_SINTAXIS = (
    "Cláusulas separadas por comas (se combinan con 'y'): sin_pares, con_pares, "
    "sin_juego, con_juego, pares>=medias, pares=duples, juego=31, suma>=28, "
    "reyes>=2, ases<=1, caballos=0 ... Operadores: = != > >= < <=. "
    "En PowerShell y otras terminales, ponla SIEMPRE entre comillas "
    "(\"pares>=medias\"): sin ellas, > y < redirigen la salida."
)


def _comparacion(nombre: str, op: str, valor: int, campo: Callable[[TablaManos], np.ndarray]
                 ) -> Condicion:
    return Condicion(f"{nombre}{op}{valor}", lambda t: _OPERADORES[op](campo(t), valor))


def _clausula(texto: str, reglas: ReglasMus) -> Condicion:
    t = texto.strip().lower()
    if t in _PALABRAS:
        return _PALABRAS[t]()
    coincidencia = _CLAUSULA.match(t)
    if not coincidencia:
        raise ValueError(f"Cláusula no válida: {texto!r}. {AYUDA_SINTAXIS}")
    nombre, op, valor = coincidencia.groups()

    if nombre == "pares":
        if valor not in _CATEGORIAS_PARES:
            raise ValueError(f"Categoría de pares desconocida: {valor!r} "
                             f"(usa {', '.join(_CATEGORIAS_PARES)})")
        categoria = _CATEGORIAS_PARES[valor]
        return _comparacion(nombre, op, categoria, lambda tb: tb.jugada_pares.astype(int)) \
            .renombrar(f"pares{op}{valor}")
    if not valor.isdigit():
        raise ValueError(f"Se esperaba un número en {texto!r}")
    n = int(valor)
    if nombre == "juego":
        if op not in ("=", "==", "!="):
            raise ValueError("El juego no se ordena por su suma: usa juego=N o juego!=N")
        c = con_juego([n])
        return c if op != "!=" else (con_juego() & ~c).renombrar(f"juego!={n}")
    if nombre == "suma":
        return _comparacion(nombre, op, n, lambda tb: tb.suma.astype(int))
    if nombre in NOMBRES_RANGO:
        simbolo = NOMBRES_RANGO[nombre]
        if simbolo not in baraja_de(reglas).simbolos:
            raise ValueError(f"En la variante {reglas.variante.value} no hay {nombre} propios "
                             "(en 8 reyes los treses son reyes y los doses, ases)")
        return _comparacion(nombre, op, n,
                            lambda tb: tb.conteos[:, tb.baraja.indice(simbolo)].astype(int))
    raise ValueError(f"Campo desconocido: {nombre!r}. {AYUDA_SINTAXIS}")


def parsear_condicion(texto: str, reglas: ReglasMus = REGLAS_POR_DEFECTO) -> Condicion:
    """Convierte ``"pares>=medias, reyes>=2"`` en una :class:`Condicion`.

    Ver :data:`AYUDA_SINTAXIS` para la sintaxis completa.
    """
    clausulas = [c for c in texto.split(",") if c.strip()]
    if not clausulas:
        raise ValueError("Condición vacía")
    resultado = _clausula(clausulas[0], reglas)
    for c in clausulas[1:]:
        resultado = resultado & _clausula(c, reglas)
    return resultado
