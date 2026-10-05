"""Tests del Monte Carlo: reproducibilidad, validez del reparto y concordancia
con el cálculo exacto."""

from math import sqrt
from statistics import NormalDist

import numpy as np
import pytest

from mus.analisis import comparar_exacto_mc, metricas_por_mano
from mus.cartas import parsear_mano as pm
from mus.evaluacion import Lance, resolver_lance
from mus.simulacion import (
    Estimacion,
    generador,
    ganadores,
    ganadores_lance,
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


class TestGanadoresVectorizados:
    def test_desempata_por_posicion(self):
        fuerzas = np.array([[3, 5, 5, 1], [2, 2, 2, 2], [0, 0, 1, 1], [0, 0, 0, 3]])
        np.testing.assert_array_equal(ganadores(fuerzas), [2, 1, 3, 4])

    def test_todas_las_fuerzas_a_cero_no_da_ganador(self):
        """argmax de [0,0,0,0] es 0 (el jugador 1): debe corregirse a 'nadie'."""
        np.testing.assert_array_equal(ganadores(np.zeros((3, 4), dtype=np.int16)), [0, 0, 0])

    def test_nadie_con_pares_ni_juego_en_manos_reales(self, tabla):
        manos = [pm(t) for t in ("R C 7 A", "R C 5 A", "R C 4 A", "A 4 5 6")]
        reparto = np.array([[tabla.indice(m) for m in manos]])
        assert ganadores_lance(tabla, reparto, Lance.PARES)[0] == 0
        assert ganadores_lance(tabla, reparto, Lance.JUEGO)[0] == 0
        assert ganadores_lance(tabla, reparto, Lance.PUNTO)[0] == 1   # 28 > 26 > 25 > 16

    def test_punto_no_se_juega_si_alguien_tiene_juego(self, tabla):
        manos = [pm(t) for t in ("R R 5 5", "A A A A", "A 4 5 6", "R C S A")]  # solo el 4 tiene juego
        reparto = np.array([[tabla.indice(m) for m in manos]])
        assert tabla.fuerza[Lance.PUNTO][reparto].max() > 0   # hay fuerzas de punto...
        assert ganadores_lance(tabla, reparto, Lance.PUNTO)[0] == 0   # ...pero no se juega

    @pytest.mark.parametrize("lance", list(Lance))
    def test_coincide_con_la_resolucion_escalar(self, tabla, lance):
        """Repartos reales: la versión vectorizada da el mismo ganador que
        resolver_lance, con las columnas en orden de juego (0 = mano)."""
        repartos = repartir(2_000, tabla, generador(SEMILLA))
        vectorizado = ganadores_lance(tabla, repartos, lance)
        for fila, g in zip(repartos, vectorizado):
            r = resolver_lance([tabla.manos[i] for i in fila], lance)
            assert g == (r.ganador or 0)
        # sanidad: la muestra incluye repartos en los que el lance no se juega
        if lance is not Lance.GRANDE and lance is not Lance.CHICA:
            assert (vectorizado == 0).any()
