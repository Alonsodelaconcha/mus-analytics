"""Tests de la baraja, el parseo y la enumeración de manos."""

from math import comb

import pytest

from mus.cartas import Mano, baraja_de, enumerar_manos, parsear_mano
from mus.reglas import ReglasMus, Variante

CUATRO_REYES = ReglasMus(variante=Variante.CUATRO_REYES)


def texto(t: str, reglas: ReglasMus = ReglasMus()) -> str:
    return parsear_mano(t, reglas).texto(baraja_de(reglas))


class TestParseo:
    def test_formatos_equivalentes(self):
        esperada = parsear_mano("R R C 5")
        for t in ("RRC5", "r,r,c,5", "5 C R R", "12 12 11 5", "R;R;C;5"):
            assert parsear_mano(t) == esperada

    def test_ocho_reyes_tres_es_rey_y_dos_es_as(self):
        assert parsear_mano("3 3 2 2") == parsear_mano("R R A A")
        assert texto("3 2 1 12") == "R R A A"

    def test_cuatro_reyes_tres_y_dos_son_cartas_propias(self):
        assert texto("3 2 1 12", CUATRO_REYES) == "R 3 2 A"

    def test_ocho_reyes_admite_cinco_o_mas_reyes_fisicos_por_mano(self):
        # 8 reyes permite R R R R (p. ej. dos reyes y dos treses)
        assert parsear_mano("R 3 R 3") == parsear_mano("R R R R")

    def test_baraja_rechaza_manos_de_otra_variante(self):
        # Con 4 cartas por mano nunca se superan las copias (todo rango tiene >= 4),
        # pero una mano de 8 rangos no es válida en una baraja de 10.
        assert not baraja_de(CUATRO_REYES).admite(parsear_mano("R R C 5"))

    @pytest.mark.parametrize("t", ["R R C", "R R C 5 5", "R R C 8", "R R C X", ""])
    def test_entradas_invalidas(self, t):
        with pytest.raises(ValueError):
            parsear_mano(t)

    def test_mano_debe_tener_cuatro_cartas(self):
        with pytest.raises(ValueError):
            Mano((1, 1, 1, 0, 0, 0, 0, 0))


class TestEnumeracion:
    def test_330_manos_en_ocho_reyes(self):
        manos = enumerar_manos()
        assert len(manos) == 330 == comb(8 + 4 - 1, 4)
        assert len(set(manos)) == 330

    def test_715_manos_en_cuatro_reyes(self):
        assert len(enumerar_manos(CUATRO_REYES)) == 715 == comb(10 + 4 - 1, 4)

    @pytest.mark.parametrize("reglas", [ReglasMus(), CUATRO_REYES])
    def test_combinaciones_suman_c_40_4(self, reglas):
        baraja = baraja_de(reglas)
        assert baraja.total_cartas == 40
        assert sum(baraja.combinaciones(m) for m in enumerar_manos(reglas)) == comb(40, 4)

    def test_combinaciones_de_casos_concretos(self):
        b = baraja_de()
        assert b.combinaciones(parsear_mano("R R R R")) == comb(8, 4)  # 70
        assert b.combinaciones(parsear_mano("R R C 5")) == comb(8, 2) * 4 * 4  # 448
        assert b.combinaciones(parsear_mano("C C C C")) == 1

    def test_codigo_unico(self):
        codigos = [m.codigo for m in enumerar_manos()]
        assert len(set(codigos)) == len(codigos)
        assert codigos == sorted(codigos)
