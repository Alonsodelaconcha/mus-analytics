"""Señas del compañero (Fase 4).

Regla de la mesa del usuario (confirmada el 2026-10-07):

- Las señas son **libres**: el compañero puede hacer una, varias o ninguna.
- Cada seña significa "tengo **al menos** esto". Si hace varias, cumple todas:
  se combinan con "y".
- **No hacer una seña no informa de nada**: el compañero puede tener la
  jugada y no haberla pasado. Por eso nunca se condiciona a la ausencia de
  una seña.

Cada seña es, por tanto, una :class:`mus.condiciones.Condicion` sobre la mano
del compañero, y un conjunto de señas es la conjunción de sus condiciones.
Como la equity condicionada solo depende del conjunto de manos que cumplen la
condición, muchas combinaciones dan exactamente lo mismo (p. ej. "tres reyes"
y "tres reyes + medias"). :func:`grupos_de_senas` agrupa las combinaciones
posibles por su conjunto de manos: en 8 reyes hay 16 conjuntos distintos.

En 8 reyes los treses son reyes y los doses, ases, a todos los efectos.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations

import numpy as np

from mus.condiciones import (
    Condicion,
    con_juego,
    cuenta,
    pares_entre,
    sin_juego,
    sin_pares,
    suma_entre,
)
from mus.evaluacion import Pares
from mus.tablas import TablaManos


@dataclass(frozen=True)
class Sena:
    """Una seña: qué cartas indica y con qué gesto se hace."""

    id: str
    nombre: str
    cartas: str
    """Qué tiene el compañero, en lenguaje llano."""
    gesto: str
    condicion: Condicion

    def mascara(self, tabla: TablaManos) -> np.ndarray:
        return self.condicion.mascara(tabla)


def _sin_jugada() -> Condicion:
    return sin_pares() & sin_juego()


SENAS: tuple[Sena, ...] = (
    Sena("dos-reyes", "Dos reyes", "Exactamente dos reyes",
         "Morderse el labio inferior", cuenta("R", 2, 2)),
    Sena("tres-reyes", "Tres reyes", "Exactamente tres reyes (también el solomillo)",
         "Morderse el lateral del labio inferior", cuenta("R", 3, 3)),
    Sena("dos-ases", "Dos ases", "Exactamente dos ases",
         "Sacar la punta de la lengua", cuenta("A", 2, 2)),
    Sena("tres-ases", "Tres ases", "Exactamente tres ases",
         "Sacar la lengua de lado", cuenta("A", 3, 3)),
    Sena("medias", "Medias", "Tres cartas iguales, también de reyes o de ases",
         "Torcer la boca cerrada hacia un lado", pares_entre(Pares.MEDIAS, Pares.MEDIAS)),
    Sena("duples", "Duples", "Dos parejas o cuatro iguales",
         "Levantar las cejas", pares_entre(Pares.DUPLES, Pares.DUPLES)),
    Sena("31", "31", "Suma exactamente 31",
         "Guiñar un ojo", con_juego([31])),
    Sena("solomillo", "Solomillo", "Tres reyes y un as",
         "Dar un beso simulado", cuenta("R", 3, 3) & cuenta("A", 1, 1)),
    Sena("ciego", "Ciego", "Sin pares ni juego",
         "Cerrar los ojos", _sin_jugada()),
    Sena("30-punto", "30 al punto", "Sin pares ni juego, suma 30",
         "Levantar ambos hombros", _sin_jugada() & suma_entre(30, 30)),
    Sena("29-punto", "29 al punto", "Sin pares ni juego, suma 29",
         "Levantar un hombro", _sin_jugada() & suma_entre(29, 29)),
)
"""Las señas de la mesa del usuario, en el orden de la chuleta.

"Medias" es la categoría de pares del juego: exactamente tres iguales (cuatro
iguales son duples). "Dos" y "tres" reyes o ases son exactamente dos o tres.
"""

_POR_ID = {s.id: s for s in SENAS}


def sena(id_sena: str) -> Sena:
    """Seña por su identificador (p. ej. ``"dos-reyes"``)."""
    try:
        return _POR_ID[id_sena]
    except KeyError:
        raise ValueError(f"Seña desconocida: {id_sena!r}. Válidas: {', '.join(_POR_ID)}") from None


def combinar(senas: Iterable[Sena | str]) -> Condicion:
    """Condición de que el compañero cumpla **todas** las señas dadas."""
    lista = [sena(s) if isinstance(s, str) else s for s in senas]
    if not lista:
        raise ValueError("Hace falta al menos una seña")
    condicion = lista[0].condicion
    for s in lista[1:]:
        condicion = condicion & s.condicion
    return condicion.renombrar("señas: " + " + ".join(s.nombre for s in lista))


@dataclass(frozen=True, eq=False)
class GrupoSenas:
    """Combinaciones de señas que dejan exactamente el mismo conjunto de manos.

    Atributos:
        senas: la combinación canónica (la de menos señas y, a igualdad, la
            primera en el orden de :data:`SENAS`).
        combinaciones: todas las combinaciones posibles que dan este conjunto.
        mascara: manos del compañero compatibles con las señas.
    """

    senas: tuple[Sena, ...]
    combinaciones: tuple[tuple[Sena, ...], ...]
    mascara: np.ndarray

    @property
    def id(self) -> str:
        return "+".join(s.id for s in self.senas)

    @property
    def condicion(self) -> Condicion:
        return combinar(self.senas)


def grupos_de_senas(tabla: TablaManos, senas: Sequence[Sena] = SENAS) -> list[GrupoSenas]:
    """Todos los conjuntos de manos distintos que pueden dejar las señas libres.

    Se recorren las combinaciones de 1, 2, 3... señas hasta que ninguna mano
    cumple tantas a la vez. Las combinaciones imposibles (ninguna mano las
    cumple) se omiten.
    """
    mascaras = np.array([s.mascara(tabla) for s in senas])
    grupos: dict[bytes, list[tuple[Sena, ...]]] = {}
    maximo = int(mascaras.sum(axis=0).max())  # señas que cumple a la vez la mano que más cumple
    for k in range(1, maximo + 1):
        for combinacion in combinations(range(len(senas)), k):
            m = mascaras[list(combinacion)].all(axis=0)
            if m.any():
                grupos.setdefault(m.tobytes(), []).append(tuple(senas[i] for i in combinacion))
    return [GrupoSenas(combos[0], tuple(combos), np.frombuffer(clave, dtype=bool).copy())
            for clave, combos in grupos.items()]
