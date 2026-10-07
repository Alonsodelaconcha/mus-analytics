"""Tests de las señas del compañero (Fase 4)."""

from math import comb

import numpy as np
import pytest

from mus.cartas import parsear_mano
from mus.senas import SENAS, combinar, grupos_de_senas, sena
from mus.tablas import construir_tabla

TABLA = construir_tabla()


def cumple(id_sena: str, mano: str) -> bool:
    return bool(sena(id_sena).mascara(TABLA)[TABLA.indice(parsear_mano(mano))])


def senas_de(mano: str) -> set[str]:
    return {s.id for s in SENAS if cumple(s.id, mano)}


@pytest.mark.parametrize("id_sena, manos", [
    ("dos-reyes", 28), ("tres-reyes", 7), ("dos-ases", 28), ("tres-ases", 7), ("medias", 56),
    ("duples", 36), ("31", 25), ("solomillo", 1), ("ciego", 53), ("30-punto", 3),
    ("29-punto", 3),
])
def test_numero_de_manos(id_sena, manos):
    assert sena(id_sena).mascara(TABLA).sum() == manos


@pytest.mark.parametrize("id_sena, k", [("dos-reyes", 2), ("tres-reyes", 3), ("dos-ases", 2),
                                        ("tres-ases", 3)])
def test_probabilidad_exacta_de_reyes_y_ases(id_sena, k):
    # Hipergeométrica: hay 8 reyes (y 8 ases) entre 40 cartas, contando treses y doses.
    exacta = comb(8, k) * comb(32, 4 - k) / comb(40, 4)
    assert TABLA.probabilidad[sena(id_sena).mascara(TABLA)].sum() == pytest.approx(exacta,
                                                                                    abs=1e-12)


def test_treses_y_doses_cuentan_como_reyes_y_ases():
    assert senas_de("3 3 2 2") == senas_de("R R A A") == {"dos-reyes", "dos-ases", "duples"}


@pytest.mark.parametrize("mano, esperadas", [
    ("R R R A", {"tres-reyes", "medias", "31", "solomillo"}),   # sin exclusiones
    ("R R R C", {"tres-reyes", "medias"}),
    ("A A A 4", {"tres-ases", "medias"}),
    ("R R R R", {"duples"}),                                      # cuatro iguales = duples
    ("R R C A", {"dos-reyes", "31"}),
    ("7 7 7 S", {"medias", "31"}),
    ("C C 7 7", {"duples"}),
    ("C C 5 4", set()),                                           # par que no es de reyes ni ases
    ("R C S 4", set()),                                           # juego que no es 31
    ("C S 5 4", {"ciego", "29-punto"}),                           # el ciego incluye 29 y 30
    ("C S 6 4", {"ciego", "30-punto"}),
    ("7 6 5 A", {"ciego"}),
])
def test_senas_de_manos_concretas(mano, esperadas):
    assert senas_de(mano) == esperadas


def test_combinar_es_la_interseccion():
    m = combinar(["dos-reyes", "31"]).mascara(TABLA)
    esperado = sena("dos-reyes").mascara(TABLA) & sena("31").mascara(TABLA)
    np.testing.assert_array_equal(m, esperado)
    assert sorted(TABLA.manos[i].texto(TABLA.baraja) for i in np.flatnonzero(m)) == \
        ["R R 6 5", "R R 7 4", "R R C A", "R R S A"]


def test_sena_desconocida():
    with pytest.raises(ValueError, match="Seña desconocida"):
        sena("cuatro-reyes")
    with pytest.raises(ValueError):
        combinar([])


class TestGrupos:
    GRUPOS = grupos_de_senas(TABLA)

    def test_dieciseis_conjuntos_distintos(self):
        assert len(self.GRUPOS) == 16
        assert len({g.mascara.tobytes() for g in self.GRUPOS}) == 16
        assert {g.id for g in self.GRUPOS} == {s.id for s in SENAS} | {
            "dos-reyes+dos-ases", "dos-reyes+duples", "dos-reyes+31", "dos-ases+duples",
            "medias+31"}

    def test_cada_combinacion_posible_esta_en_su_grupo(self):
        mascaras = {s.id: s.mascara(TABLA) for s in SENAS}
        for g in self.GRUPOS:
            assert g.combinaciones[0] == g.senas  # la canónica es la primera (la más corta)
            for combinacion in g.combinaciones:
                m = np.logical_and.reduce([mascaras[s.id] for s in combinacion])
                np.testing.assert_array_equal(m, g.mascara)
            np.testing.assert_array_equal(g.condicion.mascara(TABLA), g.mascara)

    def test_grupos_que_absorben_otras_senas(self):
        por_id = {g.id: g for g in self.GRUPOS}
        ids = lambda g: {"+".join(s.id for s in c) for c in g.combinaciones}
        assert "tres-reyes+medias" in ids(por_id["tres-reyes"])
        assert {"tres-reyes+31", "medias+solomillo"} <= ids(por_id["solomillo"])
        assert "ciego+30-punto" in ids(por_id["30-punto"])
        assert por_id["solomillo"].mascara.sum() == 1

    def test_ninguna_mano_cumple_cinco_senas(self):
        cumplidas = np.array([s.mascara(TABLA) for s in SENAS]).sum(axis=0)
        assert cumplidas.max() == 4
        assert TABLA.manos[int(cumplidas.argmax())].texto(TABLA.baraja) == "R R R A"
