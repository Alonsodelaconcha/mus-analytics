"""Tests de las condiciones sobre la mano de otro jugador."""

import numpy as np
import pytest

from mus.condiciones import (
    con_juego,
    con_pares,
    cualquiera,
    cuenta,
    manos,
    pares_entre,
    parsear_condicion,
    sin_juego,
    sin_pares,
)
from mus.evaluacion import Pares
from mus.reglas import ReglasMus, Variante
from mus.tablas import construir_tabla

T = construir_tabla()
CUATRO_REYES = ReglasMus(variante=Variante.CUATRO_REYES)
REY = T.baraja.indice("R")
AS = T.baraja.indice("A")


def mascara(texto, tabla=T):
    return parsear_condicion(texto, tabla.reglas).mascara(tabla)


@pytest.mark.parametrize("texto, esperada", [
    ("sin_pares", T.jugada_pares == Pares.SIN_PARES),
    ("con_pares", T.jugada_pares > 0),
    ("pares", T.jugada_pares > 0),
    ("pares>=medias", T.jugada_pares >= Pares.MEDIAS),
    ("pares=duples", T.jugada_pares == Pares.DUPLES),
    ("pares<par", T.jugada_pares == Pares.SIN_PARES),
    ("sin_juego", T.suma < 31),
    ("juego", T.suma >= 31),
    ("juego=31", T.suma == 31),
    ("juego!=31", (T.suma >= 31) & (T.suma != 31)),
    ("suma>=28", T.suma >= 28),
    ("reyes>=2", T.conteos[:, REY] >= 2),
    ("ases<=1", T.conteos[:, AS] <= 1),
    ("caballos=0", T.conteos[:, T.baraja.indice("C")] == 0),
    ("cualquiera", np.ones(330, dtype=bool)),
])
def test_clausulas(texto, esperada):
    np.testing.assert_array_equal(mascara(texto), esperada)


def test_varias_clausulas_se_combinan_con_y():
    np.testing.assert_array_equal(mascara("con_pares, reyes>=2"),
                                  (T.jugada_pares > 0) & (T.conteos[:, REY] >= 2))
    np.testing.assert_array_equal(mascara(" Pares >= Medias ,SIN_JUEGO "),
                                  (T.jugada_pares >= 2) & (T.suma < 31))


def test_reyes_incluye_treses_en_ocho_reyes():
    from mus.cartas import parsear_mano
    i = T.indice(parsear_mano("3 3 C 5"))
    assert mascara("reyes=2")[i]


def test_treses_solo_en_cuatro_reyes():
    with pytest.raises(ValueError, match="treses"):
        parsear_condicion("treses>=1")
    t4 = construir_tabla(CUATRO_REYES)
    np.testing.assert_array_equal(mascara("treses>=1", t4),
                                  t4.conteos[:, t4.baraja.indice("3")] >= 1)


@pytest.mark.parametrize("texto", ["pares>=trio", "juego>31", "reyes>=dos", "foo=1", "",
                                   "reyes", "pares>="])
def test_errores(texto):
    with pytest.raises(ValueError):
        parsear_condicion(texto)


def test_operadores_logicos():
    a, b = con_pares(), con_juego()
    np.testing.assert_array_equal((a & b).mascara(T), a.mascara(T) & b.mascara(T))
    np.testing.assert_array_equal((a | b).mascara(T), a.mascara(T) | b.mascara(T))
    np.testing.assert_array_equal((~a).mascara(T), sin_pares().mascara(T))
    np.testing.assert_array_equal((~b).mascara(T), sin_juego().mascara(T))
    assert str(a & b) == "con pares y con juego"


def test_constructores():
    np.testing.assert_array_equal(pares_entre(Pares.MEDIAS).mascara(T), mascara("pares>=medias"))
    np.testing.assert_array_equal(cuenta("R", 2).mascara(T), mascara("reyes>=2"))
    np.testing.assert_array_equal(con_juego([31, 40]).mascara(T), np.isin(T.suma, [31, 40]))
    assert manos("R R R R", "3 3 R R").mascara(T).sum() == 1
    assert cualquiera().mascara(T).all()
