"""Tests de los evaluadores de cada lance, con casos límite y desempates."""

import pytest

from mus.cartas import parsear_mano as pm
from mus.evaluacion import (
    Lance,
    Pares,
    clave,
    clave_chica,
    clave_grande,
    clave_juego,
    clave_pares,
    clave_punto,
    jugada_pares,
    mejor_posicion,
    pareja_de,
    puntos_juego,
    resolver_lance,
    resolver_mano,
    suma,
)
from mus.reglas import Puntuacion, ReglasMus, Variante

CUATRO_REYES = ReglasMus(variante=Variante.CUATRO_REYES)
CON_31_REAL = ReglasMus(treinta_y_una_real=True)


def gana(lance, a, b, reglas=ReglasMus()):
    """True si la mano ``a`` es estrictamente mejor que ``b`` en el lance."""
    ca, cb = clave(lance, pm(a, reglas), reglas), clave(lance, pm(b, reglas), reglas)
    if ca is None:
        return False
    return cb is None or ca > cb


def empata(lance, a, b, reglas=ReglasMus()):
    return clave(lance, pm(a, reglas), reglas) == clave(lance, pm(b, reglas), reglas)


class TestGrande:
    @pytest.mark.parametrize("mejor, peor", [
        ("R R R R", "R R R C"),
        ("R A A A", "C C C C"),      # la primera carta decide
        ("R C 5 4", "R C 5 A"),      # decide la última
        ("R R 4 A", "R C C C"),
        ("S 4 4 4", "7 7 7 7"),
    ])
    def test_orden(self, mejor, peor):
        assert gana(Lance.GRANDE, mejor, peor)
        assert not gana(Lance.GRANDE, peor, mejor)

    def test_ocho_reyes_tres_empata_con_rey(self):
        assert empata(Lance.GRANDE, "3 C 5 4", "R C 5 4")

    def test_cuatro_reyes_tres_es_bajo(self):
        assert gana(Lance.GRANDE, "4 A A A", "3 3 3 3", CUATRO_REYES)

    def test_clave_es_cartas_de_mayor_a_menor(self):
        assert clave_grande(pm("5 R A C")) == pm("R C 5 A").rangos


class TestChica:
    @pytest.mark.parametrize("mejor, peor", [
        ("A A A A", "A A A 4"),
        ("A A A R", "A A 4 4"),      # se compara desde la carta más baja
        ("A 4 5 R", "A 4 6 6"),
    ])
    def test_orden(self, mejor, peor):
        assert gana(Lance.CHICA, mejor, peor)
        assert not gana(Lance.CHICA, peor, mejor)

    def test_carta_mas_baja_decide_primero(self):
        assert gana(Lance.CHICA, "A R R R", "4 4 4 4")

    def test_ocho_reyes_dos_es_as(self):
        assert empata(Lance.CHICA, "2 4 5 6", "A 4 5 6")

    def test_cuatro_reyes_dos_gana_a_tres(self):
        assert gana(Lance.CHICA, "A 2 R R", "A 3 4 4", CUATRO_REYES)

    def test_clave_mayor_es_mano_mas_baja(self):
        assert clave_chica(pm("A A A A")) > clave_chica(pm("R R R R"))


class TestPares:
    @pytest.mark.parametrize("t, jugada", [
        ("R C 5 4", Pares.SIN_PARES),
        ("R R 5 4", Pares.PAR),
        ("R R R 4", Pares.MEDIAS),
        ("R R 4 4", Pares.DUPLES),
        ("5 5 5 5", Pares.DUPLES),
        ("R 3 C 5", Pares.PAR),       # en 8 reyes, R y 3 son pareja
        ("2 A 4 4", Pares.DUPLES),    # y 2 y As también
    ])
    def test_categoria(self, t, jugada):
        assert jugada_pares(pm(t)) == jugada

    def test_cuatro_reyes_tres_y_rey_no_son_pareja(self):
        assert jugada_pares(pm("R 3 C 5", CUATRO_REYES)) == Pares.SIN_PARES

    def test_sin_pares_no_participa(self):
        assert clave_pares(pm("R C 5 4")) is None
        assert gana(Lance.PARES, "A A 4 5", "R C S 7")

    def test_categorias_ordenadas(self):
        assert gana(Lance.PARES, "A A A 4", "R R C S")   # medias > par
        assert gana(Lance.PARES, "A A 4 4", "R R R C")   # duples > medias

    def test_par_solo_cuenta_la_pareja(self):
        assert empata(Lance.PARES, "R R C 5", "R R 7 4")
        assert empata(Lance.PARES, "R R C 5", "R R A 4")
        assert gana(Lance.PARES, "C C 4 A", "S S R C")

    def test_medias_por_rango_del_trio(self):
        assert gana(Lance.PARES, "C C C A", "S S S R")
        assert empata(Lance.PARES, "C C C A", "C C C R")

    def test_duples_cuatro_iguales_vs_dos_parejas(self):
        assert gana(Lance.PARES, "R R R R", "R R C C")
        assert gana(Lance.PARES, "R R 4 4", "5 5 5 5")   # se compara primero la pareja alta
        assert gana(Lance.PARES, "5 5 5 5", "5 5 4 4")   # luego la baja
        assert gana(Lance.PARES, "R R C C", "R R S S")
        assert empata(Lance.PARES, "R R 4 4", "R 3 4 4")


class TestJuego:
    @pytest.mark.parametrize("t, s", [
        ("R C S A", 31), ("7 7 7 S", 31), ("R C 5 7", 32), ("R R R R", 40),
        ("R R 7 S", 37), ("R R 6 S", 36), ("R R 5 S", 35), ("R R 4 S", 34),
        ("R 7 6 S", 33), ("A A A A", 4), ("R R S A", 31),
    ])
    def test_sumas(self, t, s):
        assert suma(pm(t)) == s

    def test_orden_31_32_40_37_36_35_34_33(self):
        manos = ["R C S A", "R C 5 7", "R R R R", "R R 7 S", "R R 6 S", "R R 5 S",
                 "R R 4 S", "R 7 6 S"]
        claves = [clave_juego(pm(m)) for m in manos]
        assert claves == sorted(claves, reverse=True)
        assert len(set(claves)) == len(claves)

    def test_sin_juego_no_participa(self):
        assert clave_juego(pm("R R 7 A")) is None   # 28
        assert clave_juego(pm("R R S A")) is not None               # 31

    def test_todas_las_31_empatan_sin_31_real(self):
        assert empata(Lance.JUEGO, "7 7 7 S", "R C S A")

    def test_31_real_gana_a_otra_31_si_esta_activa(self):
        assert gana(Lance.JUEGO, "7 7 7 S", "R C S A", CON_31_REAL)
        assert gana(Lance.JUEGO, "S 7 7 7", "R R R A", CON_31_REAL)
        assert empata(Lance.JUEGO, "R C S A", "R R R A", CON_31_REAL)
        assert puntos_juego(pm("7 7 7 S"), CON_31_REAL) == 3

    def test_31_real_composicion_configurable(self):
        reglas = ReglasMus(treinta_y_una_real=True, composicion_31_real="7 7 7 R")
        assert gana(Lance.JUEGO, "7 7 7 R", "7 7 7 S", reglas)
        with pytest.raises(ValueError):
            clave_juego(pm("R R R A"), ReglasMus(treinta_y_una_real=True,
                                                 composicion_31_real="7 7 7 7"))

    def test_puntos_juego(self):
        assert puntos_juego(pm("R C S A")) == 3
        assert puntos_juego(pm("R R R R")) == 2
        assert puntos_juego(pm("R R 7 A")) == 0


class TestPunto:
    def test_gana_suma_mas_alta(self):
        assert gana(Lance.PUNTO, "R R 5 5", "R R 7 A")   # 30 > 28
        assert clave_punto(pm("R R 5 5")) == (30,)

    def test_con_juego_no_participa(self):
        assert clave_punto(pm("R C S A")) is None


class TestReglas:
    def test_orden_juego_invalido(self):
        with pytest.raises(ValueError):
            ReglasMus(orden_juego=(32, 40))
        with pytest.raises(ValueError):
            ReglasMus(orden_juego=(31, 31, 32))


class TestResolucion:
    def test_pareja_de(self):
        assert [pareja_de(p) for p in (1, 2, 3, 4)] == [1, 2, 1, 2]

    def test_empate_gana_el_mas_cercano_a_la_mano(self):
        assert mejor_posicion([(1,), (5,), (5,), (2,)]) == 2
        assert mejor_posicion([(5,), (5,), (5,), (5,)]) == 1
        assert mejor_posicion([None, None, (1,), (1,)]) == 3
        assert mejor_posicion([None] * 4) is None

    def test_empate_en_grande_gana_la_mano(self):
        manos = [pm(t) for t in ("R C 5 4", "R C 5 4", "A A A A", "3 C 5 4")]
        assert resolver_lance(manos, Lance.GRANDE).ganador == 1
        manos = [pm(t) for t in ("A A A A", "R C 5 4", "A A A A", "3 C 5 4")]
        assert resolver_lance(manos, Lance.GRANDE).ganador == 2

    def test_pares_cobra_las_jugadas_de_ambos_companeros(self):
        manos = [pm(t) for t in ("R R C 5", "S 7 7 7", "A A 4 5", "C C S S")]
        r = resolver_lance(manos, Lance.PARES)
        assert (r.ganador, r.pareja, r.tantos) == (4, 2, 3 + 2)

    def test_pareja_perdedora_no_cobra_sus_pares(self):
        manos = [pm(t) for t in ("R R R R", "S S 4 5", "A 4 5 6", "C 7 6 5")]
        r = resolver_lance(manos, Lance.PARES)
        assert (r.ganador, r.pareja, r.tantos) == (1, 1, 3)

    def test_juego_cobra_ambos_y_31_gana_a_40(self):
        manos = [pm(t) for t in ("R R C 5", "S 7 7 7", "A A 4 5", "C C S S")]
        r = resolver_lance(manos, Lance.JUEGO)
        assert (r.ganador, r.pareja, r.tantos) == (2, 2, 3 + 2)

    def test_punto_no_se_juega_si_alguien_tiene_juego(self):
        manos = [pm(t) for t in ("R R C 5", "A A 4 5", "A A A A", "A 4 5 6")]
        assert not resolver_lance(manos, Lance.PUNTO).se_juega

    def test_punto_sin_juego(self):
        manos = [pm(t) for t in ("A A 4 5", "R R 5 4", "R R 5 5", "R R 5 5")]
        r = resolver_lance(manos, Lance.PUNTO)
        assert (r.se_juega, r.ganador, r.pareja, r.tantos) == (True, 3, 1, 1)
        assert not resolver_lance(manos, Lance.JUEGO).se_juega

    def test_nadie_con_pares(self):
        manos = [pm(t) for t in ("R C S 7", "R C S 6", "R C S 5", "A 4 5 6")]
        assert not resolver_lance(manos, Lance.PARES).se_juega

    def test_puntuacion_configurable(self):
        reglas = ReglasMus(puntuacion=Puntuacion(duples=5, medias=4))
        manos = [pm(t) for t in ("R R C 5", "S 7 7 7", "A A 4 5", "C C S S")]
        assert resolver_lance(manos, Lance.PARES, reglas).tantos == 5 + 4

    def test_resolver_mano_completa(self):
        manos = [pm(t) for t in ("R R C 5", "S 7 7 7", "A A 4 5", "C C S S")]
        res = resolver_mano(manos)
        assert {l: r.ganador for l, r in res.items()} == {
            Lance.GRANDE: 1, Lance.CHICA: 3, Lance.PARES: 4, Lance.JUEGO: 2, Lance.PUNTO: None,
        }

    def test_requiere_cuatro_manos(self):
        with pytest.raises(ValueError):
            resolver_lance([pm("R R R R")] * 3, Lance.GRANDE)
