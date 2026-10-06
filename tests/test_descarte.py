"""Tests de la Fase 3a: descarte de una mano aislada."""

from collections import Counter
from fractions import Fraction
from itertools import combinations

import numpy as np
import pytest

from mus.__main__ import main
from mus.cartas import Mano
from mus.cartas import parsear_mano as pm
from mus.descarte import (
    OBJETIVOS,
    construir_tabla_descartes,
    distribucion_tras_descarte,
    evaluar_descartes,
    mejores_descartes,
    objetivo_con_pesos,
    opciones_descarte,
    simular_descarte,
)
from mus.equity import TablaEquity, calcular_tabla_equity
from mus.evaluacion import Lance
from mus.reglas import ReglasDescarte, ReglasMus, Variante
from mus.tablas import construir_tabla

TABLA = construir_tabla()
B = TABLA.baraja


def opcion(mano: str, me_quedo: str):
    """La opción de ``mano`` que conserva exactamente ``me_quedo`` ("" = tirar todo)."""
    conservadas = [0] * B.n_rangos
    for carta in me_quedo.split():
        conservadas[B.indice(carta)] += 1
    for o in opciones_descarte(pm(mano)):
        if list(o.conservadas) == conservadas:
            return o
    raise LookupError(me_quedo)


def tabla_equity_sintetica(valor_por_mano: np.ndarray, lance: Lance = Lance.JUEGO) -> TablaEquity:
    """TablaEquity cuyo único valor no nulo es ``valor_por_mano`` en un lance."""
    ceros = np.zeros((TABLA.n_manos, 4, 5))
    tantos = ceros.copy()
    tantos[:, :, list(Lance).index(lance)] = valor_por_mano[:, None]
    return TablaEquity(TABLA, ceros, tantos.copy(), ceros, tantos)


# --- Opciones ------------------------------------------------------------------


@pytest.mark.parametrize("mano, n", [("R C 5 4", 15), ("R R C 5", 11), ("R R C C", 8),
                                     ("R R R C", 7), ("R R R R", 4)])
def test_numero_de_opciones_distintas(mano, n):
    assert len(opciones_descarte(pm(mano))) == n


def test_opciones_son_particiones_de_la_mano():
    mano = pm("R R C 5")
    for o in opciones_descarte(mano):
        assert tuple(c + d for c, d in zip(o.conservadas, o.descartadas)) == mano.conteos
        assert 1 <= o.n_descartes <= 4  # nunca quedarse servido: eso es cortar


def test_reglas_de_descarte_configurables():
    mano = pm("R C 5 4")
    assert len(opciones_descarte(mano, ReglasMus(descarte=ReglasDescarte(minimo=2)))) == 11
    assert len(opciones_descarte(mano, ReglasMus(descarte=ReglasDescarte(maximo=2)))) == 10
    assert len(opciones_descarte(mano, ReglasMus(descarte=ReglasDescarte(minimo=0)))) == 16
    with pytest.raises(ValueError):
        ReglasDescarte(minimo=3, maximo=2)


def test_texto_de_una_opcion():
    assert opcion("R R C 5", "R R").texto(B) == "me quedo R R, tiro C 5"
    assert opcion("R R C 5", "").texto(B) == "me quedo -, tiro R R C 5"


# --- Distribución exacta ---------------------------------------------------------


def test_valores_calculados_a_mano():
    """R C 5 4 tirando el 4: R C 5 suma 25 y se roba 1 de las 36 no vistas."""
    d = distribucion_tras_descarte(TABLA, pm("R C 5 4"), opcion("R C 5 4", "R C 5"))
    assert d.sum() == pytest.approx(1)
    # juego si sale 6, 7, S, C o R: 4 + 4 + 4 + 3 + 7 = 22 de 36 (un C y un R están en mi mano)
    assert d[TABLA.tiene_juego].sum() == pytest.approx(22 / 36)
    assert d[TABLA.suma == 31].sum() == pytest.approx(4 / 36)       # un 6
    assert d[TABLA.indice(pm("R C 5 4"))] == pytest.approx(3 / 36)  # otro 4: quedan 3


def test_con_r_r_c_siempre_hay_juego():
    d = distribucion_tras_descarte(TABLA, pm("R R C 5"), opcion("R R C 5", "R R C"))
    assert d[TABLA.tiene_juego].sum() == pytest.approx(1)
    assert d[TABLA.suma == 31].sum() == pytest.approx(8 / 36)  # los 8 ases siguen sin ver


def fuerza_bruta(mano: str):
    """Distribución de la mano final recorriendo los robos de cartas físicas."""
    m = pm(mano)
    no_vistas = [r for r, n in enumerate(np.array(B.copias) - np.array(m.conteos))
                 for _ in range(n)]
    resultado = {}
    for o in opciones_descarte(m):
        cuenta = Counter()
        for robo in combinations(range(len(no_vistas)), o.n_descartes):
            final = list(o.conservadas)
            for c in robo:
                final[no_vistas[c]] += 1
            cuenta[tuple(final)] += 1
        total = sum(cuenta.values())
        resultado[o] = {k: Fraction(v, total) for k, v in cuenta.items()}
    return resultado


@pytest.mark.parametrize("mano", ["R R C 5", "A 4 5 6"])
def test_coincide_con_fuerza_bruta(mano):
    for o, esperado in fuerza_bruta(mano).items():
        d = distribucion_tras_descarte(TABLA, pm(mano), o)
        for conteos, p in esperado.items():
            assert d[TABLA.indice(Mano(conteos))] == pytest.approx(float(p), abs=1e-15)
        assert np.count_nonzero(d) == len(esperado)


def test_tabla_completa_de_descartes():
    td = construir_tabla_descartes()
    assert sum(len(o) for o in td.opciones) == 3546
    for matriz in td.transicion:
        np.testing.assert_allclose(matriz.sum(axis=1), 1, atol=1e-12)


def test_variante_cuatro_reyes():
    td = construir_tabla_descartes(ReglasMus(variante=Variante.CUATRO_REYES))
    assert len(td.opciones) == 715
    for matriz in td.transicion[::50]:
        np.testing.assert_allclose(matriz.sum(axis=1), 1, atol=1e-12)


def test_monte_carlo_de_los_robos():
    """Frecuencias de manos finales frente a la distribución exacta (χ²)."""
    mano, o = pm("R C 5 4"), opcion("R C 5 4", "R")
    exacta = distribucion_tras_descarte(TABLA, mano, o)
    n = 200_000
    sim = simular_descarte(mano, o, n, semilla=7)
    soporte = exacta > 0
    assert sim.frecuencias[~soporte].sum() == 0
    esperadas = n * exacta[soporte]
    chi2 = ((sim.frecuencias[soporte] - esperadas) ** 2 / esperadas).sum()
    gl = soporte.sum() - 1
    assert chi2 < gl + 4 * np.sqrt(2 * gl)  # ~ cuantil 99,99 % de una χ² con gl grados


# --- Objetivos y valoración ---------------------------------------------------------


def test_pesos():
    o = objetivo_con_pesos("grande=2, punto=0")
    assert o.pesos == (2.0, 1.0, 1.0, 1.0, 0.0) and o.metrica == "tantos"
    assert objetivo_con_pesos("").pesos == OBJETIVOS["tantos"].pesos
    for malo in ("grnde=2", "grande=dos", "grande"):
        with pytest.raises(ValueError):
            objetivo_con_pesos(malo)


def test_la_valoracion_es_la_esperanza_sobre_la_mano_final():
    """Con una tabla sintética que vale 1 si la mano tiene juego, el valor de cada
    opción es P(juego), y con R C S A lo mejor es quedarse R C S (30: juego seguro)."""
    te = tabla_equity_sintetica(TABLA.tiene_juego.astype(float))
    valoraciones, servida = evaluar_descartes("R C S A", 1, te)
    for v in valoraciones:
        assert v.valor == pytest.approx(v.p_juego)
    assert valoraciones[0].opcion.texto(B) == "me quedo R C S, tiro A"
    assert valoraciones[0].valor == pytest.approx(1)
    assert [v.valor for v in valoraciones] == sorted((v.valor for v in valoraciones), reverse=True)
    assert servida.opcion is None and servida.valor == 1  # R C S A ya tiene juego


def test_mejores_descartes_tabla_sintetica():
    te = tabla_equity_sintetica(TABLA.tiene_juego.astype(float))
    filas = mejores_descartes(te)
    assert len(filas) == 330 * 4
    assert all(f.margen >= 0 for f in filas)
    fila = next(f for f in filas if f.mano == "R C 5 4" and f.posicion == 1)
    assert fila.valor == pytest.approx(max(v.p_juego for v in evaluar_descartes("R C 5 4", 1, te)[0]))


class TestCLI:
    @pytest.fixture(autouse=True)
    def tabla_rapida(self, monkeypatch):
        import mus.__main__ as cli
        te = tabla_equity_sintetica(TABLA.tiene_juego.astype(float))
        monkeypatch.setattr(cli, "cargar_tabla_equity", lambda reglas: te)

    def test_descarte(self, capsys):
        assert main(["descarte", "R C S A", "--posicion", "2", "--n", "5000", "--semilla", "1"]) == 0
        salida = capsys.readouterr().out
        assert "Recomendación: me quedo R C S, tiro A" in salida
        assert "Monte Carlo" in salida

    def test_pesos_invalidos(self, capsys):
        assert main(["descarte", "R C S A", "--pesos", "grnde=2"]) == 1
        assert "Peso no válido" in capsys.readouterr().err

    def test_descarte_tabla(self, tmp_path, capsys):
        assert main(["descarte-tabla", "--csv", str(tmp_path / "d.csv")]) == 0
        lineas = (tmp_path / "d.csv").read_text(encoding="utf-8").splitlines()
        assert len(lineas) == 1 + 330 * 4


# --- Con la tabla de equity real (lentos) --------------------------------------------


@pytest.fixture(scope="module")
def te_real():
    return calcular_tabla_equity()


@pytest.mark.slow
@pytest.mark.parametrize("mano, objetivo, me_quedo", [
    ("R R 4 A", "grande", "R R"),
    ("A A 4 R", "chica", "A A 4"),
    ("R R C 5", "pares", "R R"),
    ("R R C 5", "tantos", "R R C"),
])
def test_recomendaciones_evidentes(te_real, mano, objetivo, me_quedo):
    mejor = evaluar_descartes(mano, 1, te_real, OBJETIVOS[objetivo])[0][0]
    assert mejor.opcion == opcion(mano, me_quedo)


@pytest.mark.slow
@pytest.mark.parametrize("mano, posicion", [("R R C 5", 1), ("A 4 5 6", 4)])
def test_valor_coincide_con_monte_carlo(te_real, mano, posicion):
    valores = OBJETIVOS["tantos"].valores(te_real, posicion)
    valoraciones, _ = evaluar_descartes(mano, posicion, te_real)
    confianza = 1 - 0.001 / (2 * 15)  # Bonferroni: hasta 15 opciones × 2 manos
    for v in valoraciones:
        sim = simular_descarte(mano, v.opcion, 200_000, valores=valores, semilla=11,
                               confianza=confianza)
        assert sim.valor.contiene(v.valor), v.opcion.texto(B)
