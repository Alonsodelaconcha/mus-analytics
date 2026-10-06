"""Casos testigo del usuario para validar la Fase 3c (ver docs/casos_testigo.md).

Son la decisión de un jugador real (cortar o dar mus, y el descarte) en manos
concretas. **Solo sirven para validar**: no se usan para ajustar el modelo ni
sus parámetros. Aquí se transcriben como datos para poder comparar; el texto
original, tal cual, está en docs/casos_testigo.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from mus.condiciones import Condicion, con_juego, cuenta, pares_entre, sin_juego, sin_pares
from mus.cortar import DecisionCorte, MesaConCorte, valorar_corte
from mus.evaluacion import Pares


@dataclass(frozen=True)
class CasoTestigo:
    mano: str
    posicion: int
    decision: str
    """"cortar", "mus" o "duda" (el usuario dudaría)."""
    me_quedo: str | None
    """Lo que se quedaría si hay mus (None si corta)."""
    nota: str = ""


CASOS_TESTIGO: tuple[CasoTestigo, ...] = (
    CasoTestigo("R R C S", 1, "cortar", None, "par de reyes, 40"),
    CasoTestigo("R C S A", 1, "cortar", None, "31"),
    CasoTestigo("R R R A", 1, "cortar", None, "medias de reyes, 31"),
    CasoTestigo("R R A A", 1, "cortar", None, "duples"),
    CasoTestigo("A A 4 5", 1, "duda", "A A",
                "seguramente mus para que hable el compañero; si hay mus, A A"),
    CasoTestigo("R C 5 4", 1, "mus", "R"),
    CasoTestigo("C S 6 5", 1, "cortar", None, "31"),
    CasoTestigo("7 7 7 S", 1, "cortar", None, "medias de sietes, 31"),
    CasoTestigo("R R C S", 4, "cortar", None),
    CasoTestigo("R C S A", 4, "cortar", None),
    CasoTestigo("R R R A", 4, "cortar", None),
    CasoTestigo("R R A A", 4, "cortar", None),
    CasoTestigo("A A 4 5", 4, "duda", "A A",
                "preguntaría al compañero: si va flojo, mus y A A; si va bien, corto"),
    CasoTestigo("R C 5 4", 4, "mus", "R"),
    CasoTestigo("C S 6 5", 4, "cortar", None),
    CasoTestigo("7 7 7 S", 4, "cortar", None),
)

COMPANERO_VA_BIEN: Condicion = (
    pares_entre(Pares.MEDIAS) | con_juego([31]) | cuenta("R", 2)
).renombrar("va bien (medias o duples, 31, o dos reyes o más)")
"""Tiene algo fuerte en algún lance: pares, juego o grande."""

COMPANERO_FLOJO: Condicion = (sin_pares() & sin_juego() & cuenta("R", 0, 1)).renombrar(
    "flojo (sin pares, sin juego y como mucho un rey)")
"""No tiene nada en pares, juego ni grande. No es el complementario de "va
bien": quedan manos intermedias (un par, juego que no es 31...)."""


@dataclass(frozen=True)
class ComparacionTestigo:
    caso: CasoTestigo
    modelo: DecisionCorte
    perdida_decision: float | None
    """Tantos que pierde la decisión del usuario frente a la del modelo (None si duda)."""
    perdida_descarte: float | None
    """Si hay mus: tantos que pierde el descarte del usuario frente al del modelo."""


def _opcion_usuario(decision: DecisionCorte, me_quedo: str, baraja) -> int | None:
    objetivo = sorted(baraja.indice(c) for c in me_quedo.split())
    for i, o in enumerate(decision.opciones):
        conservadas = sorted(r for r, k in enumerate(o.opcion.conservadas) for _ in range(k))
        if conservadas == objetivo:
            return i
    return None


def comparar(caso: CasoTestigo, mesa: MesaConCorte, n: int, semilla: int | None = None,
             companero: Condicion | None = None) -> ComparacionTestigo:
    """Decisión del modelo para un caso testigo y lo que pierde (o no) la del usuario."""
    modelo = valorar_corte(caso.mano, caso.posicion, mesa, n, companero=companero,
                           semilla=semilla)
    ventaja = modelo.ventaja_mus.media
    if caso.decision == "cortar":
        perdida = max(ventaja, 0.0)
    elif caso.decision == "mus":
        perdida = max(-ventaja, 0.0)
    else:
        perdida = None
    perdida_descarte = None
    if caso.me_quedo is not None:
        baraja = mesa.tabla_inicial.tabla.baraja
        i = _opcion_usuario(modelo, caso.me_quedo, baraja)
        if i is not None:
            perdida_descarte = -modelo.opciones[i].frente_a_la_mejor.media
    return ComparacionTestigo(caso, modelo, perdida, perdida_descarte)
