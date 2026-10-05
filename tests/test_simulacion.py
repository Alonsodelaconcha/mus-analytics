"""Tests del Monte Carlo: reproducibilidad, validez del reparto y concordancia
con el cálculo exacto."""

from math import sqrt
from statistics import NormalDist

import numpy as np
import pytest

from mus.analisis import comparar_exacto_mc, metricas_por_mano
from mus.simulacion import (
    Estimacion,
    generador,
    ganadores,
    intervalo_wilson,
    muestrear_manos,
    repartir,
)
from mus.tablas import construir_tabla

SEMILLA = 20261005
CONFIANZA_TEST = 0.999  # muchas métricas: un nivel alto evita falsos fallos por azar


@pytest.fixture(scope="module")
def tabla():
    return construir_tabla()


class TestIntervalo:
    def test_valor_conocido(self):
        bajo, alto = intervalo_wilson(50, 100)
        assert bajo == pytest.approx(0.4038, abs=1e-4)
        assert alto == pytest.approx(0.5962, abs=1e-4)

    def test_extremos_dentro_de_0_1(self):
        assert intervalo_wilson(0, 10)[0] == 0.0
        assert intervalo_wilson(10, 10)[1] == 1.0
        assert intervalo_wilson(0, 10)[1] > 0

    def test_se_estrecha_con_n(self):
        a = intervalo_wilson(300, 1000)
        b = intervalo_wilson(30000, 100000)
        assert b[1] - b[0] < a[1] - a[0]

    def test_estimacion(self):
        e = Estimacion(30, 100)
        assert e.p == 0.3 and e.contiene(0.3) and not e.contiene(0.6)


class TestReparto:
    def test_reproducible_con_semilla(self, tabla):
        a = repartir(1000, tabla, generador(1))
        b = repartir(1000, tabla, generador(1))
        c = repartir(1000, tabla, generador(2))
        np.testing.assert_array_equal(a, b)
        assert not np.array_equal(a, c)

    def test_independiente_del_tamano_de_lote(self, tabla):
        """El lote solo afecta a la memoria; con la misma semilla y el mismo
        lote el resultado es idéntico, y con otro lote sigue siendo válido."""
        a = repartir(1000, tabla, generador(3), tamano_lote=1000)
        b = repartir(1000, tabla, generador(3), tamano_lote=1000)
        np.testing.assert_array_equal(a, b)
        assert repartir(1000, tabla, generador(3), tamano_lote=7).shape == (1000, 4)

    def test_repartos_respetan_la_baraja(self, tabla):
        indices = repartir(50_000, tabla, generador(SEMILLA))
        conteos = tabla.conteos[indices].sum(axis=1)  # (n, rangos): cartas de la mesa
        assert (conteos.sum(axis=1) == 16).all()
        assert (conteos <= np.array(tabla.baraja.copias)).all()

    def test_repartos_agotan_rangos_a_veces(self, tabla):
        """Sanidad: alguna mesa debe tener los 8 reyes (si no, sobraría una copia)."""
        indices = repartir(200_000, tabla, generador(SEMILLA))
        rey = tabla.baraja.indice("R")
        assert tabla.conteos[indices, rey].sum(axis=1).max() == 8


class TestExactoVsMonteCarlo:
    def test_metricas_de_una_mano(self, tabla):
        filas = comparar_exacto_mc(tabla, 400_000, SEMILLA, CONFIANZA_TEST)
        fuera = [(f.metrica, f.exacto, str(f.estimacion)) for f in filas if not f.dentro]
        assert not fuera

    @pytest.mark.parametrize("posicion", [0, 1, 2, 3])
    def test_cada_posicion_del_reparto_tiene_la_distribucion_exacta(self, tabla, posicion):
        indices = repartir(100_000, tabla, generador(SEMILLA + posicion))[:, posicion]
        for nombre, mascara in metricas_por_mano(tabla).items():
            exacto = tabla.probabilidad[mascara].sum()
            e = Estimacion(int(mascara[indices].sum()), len(indices), CONFIANZA_TEST)
            assert e.contiene(exacto), (nombre, exacto, str(e))

    def test_bondad_de_ajuste_de_las_330_manos(self, tabla):
        """Chi-cuadrado sobre las 330 frecuencias a la vez.

        Sin SciPy, el cuantil se aproxima con Wilson-Hilferty, muy preciso
        para 329 grados de libertad.
        """
        n = 1_000_000
        observadas = np.bincount(muestrear_manos(n, tabla, generador(SEMILLA)), minlength=330)
        esperadas = n * tabla.probabilidad
        chi2 = ((observadas - esperadas) ** 2 / esperadas).sum()
        gl = tabla.n_manos - 1
        z = NormalDist().inv_cdf(CONFIANZA_TEST)
        critico = gl * (1 - 2 / (9 * gl) + z * sqrt(2 / (9 * gl))) ** 3
        assert chi2 < critico


def test_ganadores_desempata_por_posicion():
    fuerzas = np.array([[3, 5, 5, 1], [2, 2, 2, 2], [0, 0, 0, 0], [0, 0, 1, 1]])
    np.testing.assert_array_equal(ganadores(fuerzas), [2, 1, 0, 3])
