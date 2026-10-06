"""Tests de las tablas precalculadas.

La verificación más fuerte es por fuerza bruta: se recorren las C(40,4) =
91 390 manos físicas (cartas distinguibles) sin pasar por la fórmula de
combinaciones ni por los evaluadores, y se comparan con la tabla.
"""

from collections import Counter
from functools import cmp_to_key
from itertools import combinations

import numpy as np
import pytest

from mus.cartas import BASE_CODIGO
from mus.evaluacion import Lance, clave
from mus.reglas import ReglasMus, Variante
from mus.tablas import construir_tabla, fuerzas_densas

REGLAS = [ReglasMus(), ReglasMus(variante=Variante.CUATRO_REYES), ReglasMus(treinta_y_una_real=True)]


def manos_fisicas(tabla):
    """Itera las 91 390 manos físicas como tuplas de rangos."""
    cartas = tabla.baraja.cartas()
    for combo in combinations(range(len(cartas)), 4):
        yield tuple(cartas[c] for c in combo)


@pytest.mark.slow
@pytest.mark.parametrize("reglas", REGLAS[:2], ids=["8reyes", "4reyes"])
def test_combinaciones_coinciden_con_fuerza_bruta(reglas):
    tabla = construir_tabla(reglas)
    conteo = Counter(sum(BASE_CODIGO**r for r in mano) for mano in manos_fisicas(tabla))
    esperado = np.array([conteo[c] for c in tabla.codigos])
    assert set(conteo) == set(tabla.codigos.tolist())
    np.testing.assert_array_equal(tabla.combinaciones, esperado)


@pytest.mark.slow
def test_probabilidades_por_fuerza_bruta_independiente():
    """P(pares), P(juego) y P(rey) contando cartas, sin usar los evaluadores."""
    tabla = construir_tabla()
    valores, rey = tabla.baraja.valores, tabla.baraja.indice("R")
    total = pares = juego = con_rey = 0
    for mano in manos_fisicas(tabla):
        total += 1
        pares += max(Counter(mano).values()) >= 2
        juego += sum(valores[r] for r in mano) >= 31
        con_rey += rey in mano
    assert total == 91390
    p = tabla.probabilidad
    assert pares / total == pytest.approx(p[tabla.jugada_pares > 0].sum(), abs=1e-12)
    assert juego / total == pytest.approx(p[tabla.tiene_juego].sum(), abs=1e-12)
    assert con_rey / total == pytest.approx(p[tabla.conteos[:, rey] > 0].sum(), abs=1e-12)


@pytest.mark.slow
@pytest.mark.parametrize("reglas", REGLAS, ids=["8reyes", "4reyes", "31real"])
@pytest.mark.parametrize("lance", list(Lance))
def test_fuerza_conserva_el_orden_de_las_claves(reglas, lance):
    """Para todo par de manos, comparar fuerzas equivale a comparar claves."""
    tabla = construir_tabla(reglas)
    claves = [clave(lance, m, reglas) for m in tabla.manos]
    f = tabla.fuerza[lance]
    for i, ci in enumerate(claves):
        for j, cj in enumerate(claves):
            if ci is None or cj is None:
                esperado = (ci is not None) - (cj is not None)
            else:
                esperado = (ci > cj) - (ci < cj)
            assert np.sign(int(f[i]) - int(f[j])) == esperado


def test_fuerzas_densas():
    np.testing.assert_array_equal(fuerzas_densas([(3,), None, (1,), (3,)]), [2, 0, 1, 2])


def test_numero_de_fuerzas_distintas():
    tabla = construir_tabla()
    distintas = {l: len(np.unique(tabla.fuerza[l][tabla.fuerza[l] > 0])) for l in Lance}
    assert distintas[Lance.GRANDE] == distintas[Lance.CHICA] == 330   # todas distintas
    assert distintas[Lance.JUEGO] == 8                                # 31,32,40,37..33
    # par: 8 rangos; medias: 8; duples: C(8,2) dos parejas + 8 cuatro iguales
    assert distintas[Lance.PARES] == 8 + 8 + 28 + 8


def test_indices_de_codigos():
    tabla = construir_tabla()
    np.testing.assert_array_equal(tabla.indices_de_codigos(tabla.codigos), np.arange(330))
    with pytest.raises(ValueError):
        tabla.indices_de_codigos(np.array([1]))  # una sola carta no es una mano


def test_tabla_cacheada_e_inmutable():
    assert construir_tabla() is construir_tabla(ReglasMus())
    with pytest.raises(ValueError):
        construir_tabla().probabilidad[0] = 1.0
