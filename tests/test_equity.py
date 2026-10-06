"""Tests de la equity exacta.

Tres niveles de verificación independientes:
1. Fuerza bruta: todas las ternas de manos, con otra enumeración y otra
   lógica de ganadores (``fuerza_bruta.py``). Debe coincidir a 1e-9.
2. Monte Carlo con intervalo de confianza (también con condiciones).
3. Identidades exactas sobre la tabla completa (cada reparto tiene un único
   ganador, suma cero de tantos, monotonía individual en la posición).

Los tests marcados ``slow`` no se ejecutan por defecto; se lanzan con
``pytest -m slow``.
"""

from math import comb

import numpy as np
import pytest

from fuerza_bruta import equity_fuerza_bruta
from mus.cartas import parsear_mano
from mus.condiciones import con_juego, con_pares, cualquiera, parsear_condicion, sin_juego
from mus.equity import (
    POSICIONES,
    _Contexto,
    calcular_tabla_equity,
    companero_de,
    equity,
    rivales_de,
    simular_equity,
)
from mus.evaluacion import Lance
from mus.tablas import construir_tabla

TABLA = construir_tabla()
# Cada test de Monte Carlo hace ~21 comparaciones (5 lances × 4 métricas + P(condición))
# y hay 3 casos: ~63 en total. Con un 99,9 % por comparación, la probabilidad de que
# alguna falle por azar ronda el 6 % (le pasó a una con 3,5σ). Corrección de Bonferroni:
# se reparte un 0,1 % de error global entre todas las comparaciones.
COMPARACIONES_MC = 63
CONFIANZA_TEST = 1 - 0.001 / COMPARACIONES_MC


def metricas(e):
    return {l: (x.p_se_juega, x.p_gana_individual, x.p_gana_pareja, x.tantos_netos)
            for l, x in e.por_lance.items()}


def test_asientos():
    assert [companero_de(p) for p in POSICIONES] == [3, 4, 1, 2]
    assert [rivales_de(p) for p in POSICIONES] == [(2, 4), (1, 3), (2, 4), (1, 3)]


def test_pesos_suman_los_repartos_fisicos():
    """Los pesos son enteros exactos: C(36,4)·C(32,4)·C(28,4) repartos de las otras manos."""
    ctx = _Contexto(TABLA, TABLA.indice(parsear_mano("R R C 5")))
    unos = np.ones(TABLA.n_manos)
    assert ctx.w1.sum() == comb(36, 4)
    assert ctx.total(unos, unos, ctx.x_fija(unos)) == comb(36, 4) * comb(32, 4) * comb(28, 4)


# --- 1. Fuerza bruta ---------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("mano, posicion", [
    ("R R C 5", 1),   # pares y juego
    ("S 7 6 4", 2),   # sin pares ni juego: entra el punto
])                    # la posición 3 la cubre el test con condiciones
def test_coincide_con_fuerza_bruta(mano, posicion):
    h = TABLA.indice(parsear_mano(mano))
    esperado = equity_fuerza_bruta(TABLA, h, posicion)
    obtenido = metricas(equity(mano, posicion))
    for lance in Lance:
        np.testing.assert_allclose(obtenido[lance], esperado[lance], rtol=0, atol=1e-9,
                                   err_msg=lance.value)


@pytest.mark.slow
def test_coincide_con_fuerza_bruta_con_condiciones():
    """Condición sobre el compañero y sobre un rival a la vez."""
    companero, rival = sin_juego(), con_pares()
    h = TABLA.indice(parsear_mano("A A 4 5"))
    esperado = equity_fuerza_bruta(TABLA, h, 3, {1: companero.mascara(TABLA).astype(float),
                                                 2: rival.mascara(TABLA).astype(float)})
    obtenido = metricas(equity("A A 4 5", 3, companero=companero, rivales={2: rival}))
    for lance in Lance:
        np.testing.assert_allclose(obtenido[lance], esperado[lance], rtol=0, atol=1e-9,
                                   err_msg=lance.value)


# --- 2. Monte Carlo ----------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("mano, posicion, companero, rivales", [
    ("R R C 5", 2, None, None),
    ("A A 4 5", 3, "sin_juego", None),
    ("R C 7 4", 4, "pares>=medias", {1: con_juego()}),
])
def test_coincide_con_monte_carlo(mano, posicion, companero, rivales):
    c = parsear_condicion(companero) if companero else None
    exacto = equity(mano, posicion, companero=c, rivales=rivales)
    mc = simular_equity(mano, posicion, 400_000, companero=c, rivales=rivales,
                        semilla=20261005, confianza=CONFIANZA_TEST)
    assert mc.p_condiciones.contiene(exacto.p_condiciones) or exacto.p_condiciones == 1
    for lance in Lance:
        x, m = exacto.por_lance[lance], mc.por_lance[lance]
        assert m.p_se_juega.contiene(x.p_se_juega), lance
        assert m.p_gana_individual.contiene(x.p_gana_individual), lance
        assert m.p_gana_pareja.contiene(x.p_gana_pareja), lance
        assert m.tantos_netos.contiene(x.tantos_netos), lance


# --- 3. Identidades sobre la tabla completa ----------------------------------


@pytest.fixture(scope="module")
def tabla_equity():
    return calcular_tabla_equity()


@pytest.mark.slow
class TestIdentidades:
    def test_cada_reparto_tiene_un_unico_ganador(self, tabla_equity):
        """Σ_p Σ_H P(H)·P(gana | H, p) = P(el lance se juega)."""
        p = TABLA.probabilidad
        for l in range(len(Lance)):
            se_juega = (p[:, None] * tabla_equity.se_juega[:, :, l]).sum(axis=0)
            assert np.allclose(se_juega, se_juega[0])  # no depende de la posición
            ganan = (p[:, None] * tabla_equity.gana_individual[:, :, l]).sum()
            assert ganan == pytest.approx(se_juega[0], abs=1e-12)

    def test_parejas(self, tabla_equity):
        p = TABLA.probabilidad[:, None, None]
        par = (p * tabla_equity.gana_pareja).sum(axis=0)       # (posiciones, lances)
        se_juega = (p * tabla_equity.se_juega).sum(axis=0)
        np.testing.assert_allclose(par[0], par[2], atol=1e-12)  # pareja 1-3 vista desde 1 y 3
        np.testing.assert_allclose(par[1], par[3], atol=1e-12)
        np.testing.assert_allclose(par[0] + par[1], se_juega[0], atol=1e-12)

    def test_tantos_suma_cero(self, tabla_equity):
        p = TABLA.probabilidad[:, None, None]
        tantos = (p * tabla_equity.tantos_netos).sum(axis=0)
        np.testing.assert_allclose(tantos[0] + tantos[1], 0, atol=1e-12)

    def test_juego_o_punto(self, tabla_equity):
        p = TABLA.probabilidad
        juego = (p * tabla_equity.se_juega[:, 0, list(Lance).index(Lance.JUEGO)]).sum()
        punto = (p * tabla_equity.se_juega[:, 0, list(Lance).index(Lance.PUNTO)]).sum()
        assert juego + punto == pytest.approx(1, abs=1e-12)

    def test_monotonia_individual_en_la_posicion(self, tabla_equity):
        """Con la misma mano, ganar individualmente nunca es más fácil más lejos de la mano."""
        g = tabla_equity.gana_individual
        assert (g[:, :-1, :] >= g[:, 1:, :] - 1e-12).all()

    def test_tabla_coincide_con_equity(self, tabla_equity):
        i = TABLA.indice(parsear_mano("C C 7 A"))
        e = equity("C C 7 A", 2)
        for lance in Lance:
            assert tabla_equity.de(i, 2, lance) == e.por_lance[lance]


def test_la_pareja_no_es_monotona_en_la_posicion():
    """Con A A A A (la peor grande) la pareja depende del compañero. En posición 3
    el compañero es la mano y gana los empates; en posición 1 va tercero y los
    pierde frente al segundo. Por eso a la pareja le va mejor con el héroe en 3."""
    en_1 = equity("A A A A", 1).por_lance[Lance.GRANDE]
    en_3 = equity("A A A A", 3).por_lance[Lance.GRANDE]
    assert en_3.p_gana_pareja > en_1.p_gana_pareja
    assert en_1.p_gana_individual >= en_3.p_gana_individual  # la individual sí es monótona


# --- Semántica de las condiciones ---------------------------------------------


def test_companero_con_mejores_pares_anula_los_mios():
    e = equity("R R C 5", 1, companero=parsear_condicion("pares>=medias"))
    assert e.por_lance[Lance.PARES].p_gana_individual == 0
    assert e.por_lance[Lance.PARES].p_gana_pareja > equity("R R C 5", 1).por_lance[
        Lance.PARES].p_gana_pareja


def test_condicion_trivial_no_cambia_nada():
    assert metricas(equity("R R C 5", 2, companero=cualquiera())) == metricas(equity("R R C 5", 2))


def test_condicion_imposible():
    with pytest.raises(ValueError, match="imposibles"):
        equity("R R R R", 1, companero=parsear_condicion("reyes>=5"))


def test_rival_en_asiento_no_rival():
    with pytest.raises(ValueError):
        equity("R R C 5", 1, rivales={3: con_pares()})


def test_tantos_fijos_de_grande():
    """En grande (1 tanto) los tantos netos son P(ganamos) − P(ganan ellos)."""
    x = equity("R C 7 4", 2).por_lance[Lance.GRANDE]
    assert x.tantos_netos == pytest.approx(2 * x.p_gana_pareja - 1, abs=1e-12)


def test_con_juego_no_hay_punto():
    x = equity("R C S A", 1).por_lance[Lance.PUNTO]
    assert (x.p_se_juega, x.p_gana_pareja, x.tantos_netos) == (0, 0, 0)
