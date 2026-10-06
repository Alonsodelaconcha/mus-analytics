"""Tests de la Fase 3b: la mesa después de una ronda de mus."""

import numpy as np
import pytest

import mus.tras_mus as tm
from mus.__main__ import main
from mus.condiciones import con_juego
from mus.descarte import OBJETIVOS, construir_tabla_descartes
from mus.equity import TablaEquity, calcular_tabla_equity, equity
from mus.evaluacion import Lance
from mus.reglas import ReglasDescarte, ReglasMus
from mus.tras_mus import (
    equity_simulada,
    iterar_tras_mus,
    marginales,
    mejor_respuesta,
    no_descartar,
    simular_ronda_mus,
    valorar_opciones_simuladas,
    verificar_mesa,
)

TD = construir_tabla_descartes()
TABLA = TD.tabla
P0 = TABLA.probabilidad
CON_SERVIDO = ReglasMus(descarte=ReglasDescarte(minimo=0))
TD_SERVIDO = construir_tabla_descartes(CON_SERVIDO)


def sintetica(valor_por_mano: np.ndarray, lance: Lance = Lance.JUEGO) -> TablaEquity:
    ceros = np.zeros((TABLA.n_manos, 4, 5))
    tantos = ceros.copy()
    tantos[:, :, list(Lance).index(lance)] = valor_por_mano[:, None]
    return TablaEquity(TABLA, ceros, tantos.copy(), ceros, tantos)


JUEGO = sintetica(TABLA.tiene_juego.astype(float))
POLITICA = mejor_respuesta(TD, JUEGO, OBJETIVOS["tantos"])


class TestPolitica:
    def test_mejor_respuesta_es_pura_y_valida(self):
        assert POLITICA.es_pura
        op = tm._opciones_densas(TD)
        np.testing.assert_allclose(POLITICA.probabilidades.sum(axis=2), 1)
        assert (POLITICA.probabilidades[:, ~op.valida] == 0).all()

    def test_marginal_es_una_distribucion(self):
        q = marginales(POLITICA)
        np.testing.assert_allclose(q.sum(axis=1), 1, atol=1e-12)
        np.testing.assert_allclose(POLITICA.transicion(1).sum(axis=1), 1, atol=1e-12)
        # buscando juego, la mesa tras el mus tiene mucho más juego que el reparto
        assert q[0][TABLA.tiene_juego].sum() > P0[TABLA.tiene_juego].sum() + 0.2

    def test_mezclar_y_comparar(self):
        otra = mejor_respuesta(TD, sintetica(TABLA.suma.astype(float), Lance.PUNTO),
                               OBJETIVOS["tantos"])
        mezcla = POLITICA.mezclar(otra, 0.5)
        assert not mezcla.es_pura
        assert mezcla.diferencia(POLITICA) == pytest.approx(0.5)
        assert POLITICA.cambios(POLITICA).sum() == 0
        assert POLITICA.cambios(otra).sum() > 0

    def test_cartas_pedidas_suman_uno(self):
        for p in (1, 2, 3, 4):
            assert sum(POLITICA.cartas_pedidas(p).values()) == pytest.approx(1)
            assert 0 not in POLITICA.cartas_pedidas(p)  # es obligatorio descartar

    def test_no_descartar(self):
        with pytest.raises(ValueError):
            no_descartar(TD)
        servida = no_descartar(TD_SERVIDO)
        np.testing.assert_allclose(marginales(servida), np.broadcast_to(P0, (4, 330)), atol=1e-15)


class TestSimulador:
    def test_sin_descartes_la_mesa_es_el_reparto(self):
        sim = simular_ronda_mus(no_descartar(TD_SERVIDO), 100_000, semilla=3)
        assert (sim.cartas_pedidas[:, 0] == 100_000).all()
        for s in range(4):
            esperadas = 100_000 * P0
            chi2 = ((sim.frecuencias[s] - esperadas) ** 2 / esperadas).sum()
            assert chi2 < 329 + 4 * np.sqrt(2 * 329)

    def test_marginal_exacta_frente_a_la_ronda_simulada(self):
        """Lo que roba cada uno es uniforme sobre lo que no ve, aunque los demás
        hayan robado antes: la marginal exacta debe coincidir con la simulación."""
        n = 300_000
        sim = simular_ronda_mus(POLITICA, n, semilla=5)
        q = marginales(POLITICA)
        for s in range(4):
            soporte = q[s] > 0
            esperadas = n * q[s][soporte]
            chi2 = ((sim.frecuencias[s][soporte] - esperadas) ** 2 / esperadas).sum()
            gl = soporte.sum() - 1
            assert chi2 < gl + 4 * np.sqrt(2 * gl), s
            assert sim.frecuencias[s][~soporte].sum() == 0

    def test_un_ganador_por_lance(self):
        sim = simular_ronda_mus(POLITICA, 50_000, semilla=8)
        individual = sim.gana_individual.sum(axis=(0, 1))   # por lance
        se_juega = sim.se_juega[0].sum(axis=0)
        np.testing.assert_allclose(individual, se_juega)
        pareja = sim.gana_pareja[0].sum(axis=0) + sim.gana_pareja[1].sum(axis=0)
        np.testing.assert_allclose(pareja, se_juega)
        np.testing.assert_allclose(sim.tantos[0].sum(axis=0), -sim.tantos[1].sum(axis=0))

    def test_reproducible(self):
        a = simular_ronda_mus(POLITICA, 20_000, semilla=1)
        b = simular_ronda_mus(POLITICA, 20_000, semilla=1)
        np.testing.assert_array_equal(a.frecuencias, b.frecuencias)


class TestEquitySimulada:
    def test_tabla_y_errores(self):
        eq = equity_simulada(simular_ronda_mus(POLITICA, 50_000, semilla=2), JUEGO)
        assert eq.muestras.sum(axis=0).tolist() == [50_000] * 4
        assert np.isfinite(eq.error_tantos).all() and (eq.error_tantos >= 0).all()
        sin_muestras = eq.muestras == 0
        # las manos que no han salido toman el valor de respaldo
        np.testing.assert_array_equal(eq.tabla.tantos_netos[sin_muestras],
                                      JUEGO.tantos_netos[sin_muestras])

    def test_verificacion_con_simulacion_independiente(self):
        respaldo = JUEGO
        eq = equity_simulada(simular_ronda_mus(POLITICA, 300_000, semilla=21), respaldo)
        mesa = tm.MesaTrasMus(ReglasMus(), OBJETIVOS["tantos"], POLITICA, marginales(POLITICA),
                              eq, respaldo, (), True, 300_000, 21)
        informe = verificar_mesa(mesa, simular_ronda_mus(POLITICA, 300_000, semilla=22),
                                 confianza=1 - 0.001 / 84, min_muestras=3000)
        assert all(c.dentro for c in informe.agregadas)
        assert all(e.fuera_del_intervalo <= 2 for e in informe.por_mano)


class TestValorarOpciones:
    def test_servida_coincide_con_la_equity_exacta(self):
        """Si nadie se descarta, el valor de quedarse servido es la equity exacta de la Fase 2."""
        resultado = valorar_opciones_simuladas("R R C S", 1, no_descartar(TD_SERVIDO), 100_000,
                                               semilla=4, confianza=0.999)
        servida = next(r for r in resultado if r.opcion.n_descartes == 0)
        exacta = equity("R R C S", 1).tantos_netos
        assert servida.tantos.contiene(exacta)

    def test_numeros_aleatorios_comunes(self):
        """Con opciones parecidas (quedarse R R C o R R S), la diferencia se estima
        con mucha más precisión que cada valor por separado: los mismos repartos
        afectan igual a las dos."""
        resultado = valorar_opciones_simuladas("R R C S", 1, POLITICA, 50_000, semilla=6)
        assert resultado[0].diferencia_con_la_mejor.media == 0
        segunda = resultado[1]
        ancho = lambda e: e.intervalo[1] - e.intervalo[0]
        assert ancho(segunda.diferencia_con_la_mejor) < ancho(segunda.tantos) / 2
        medias = [r.tantos.media for r in resultado]
        assert medias == sorted(medias, reverse=True)


class TestIteracion:
    @pytest.fixture
    def tablas(self, monkeypatch):
        """Sustituye las tablas de equity por unas sintéticas y rápidas."""
        llamadas = []
        monkeypatch.setattr(tm, "cargar_tabla_equity", lambda reglas, directorio=None: JUEGO)

        def falsa(politica, n, semilla, respaldo, directorio):
            llamadas.append(politica)
            tabla = self.fabrica(len(llamadas))
            muestras = np.full((330, 4), 1000.0)
            return tm.EquitySimulada(tabla, muestras, np.zeros((330, 4)))

        monkeypatch.setattr(tm, "_equity_de_politica", falsa)
        return llamadas

    def test_converge_si_la_tabla_no_depende_de_la_politica(self, tablas):
        self.fabrica = lambda llamada: JUEGO
        mesa = iterar_tras_mus()
        assert mesa.convergio and len(mesa.historia) == 1
        assert mesa.historia[0].cambios == 0 and mesa.historia[0].ganancia_media == 0
        assert mesa.politica.es_pura

    def test_amortigua_si_oscila(self, tablas):
        """Una tabla que se alterna entre dos objetivos hace oscilar la mejor
        respuesta: la iteración debe detectar el ciclo y amortiguar."""
        punto = sintetica(TABLA.suma.astype(float) * (~TABLA.tiene_juego), Lance.PUNTO)
        self.fabrica = lambda llamada: punto if llamada % 2 else JUEGO
        mesa = iterar_tras_mus(max_iteraciones=6)
        assert any(i.amortiguacion < 1 for i in mesa.historia)
        assert not mesa.politica.es_pura


class TestCLI:
    def test_tras_mus(self, monkeypatch, capsys):
        import mus.__main__ as cli
        eq = equity_simulada(simular_ronda_mus(POLITICA, 30_000, semilla=1), JUEGO)
        mesa = tm.MesaTrasMus(ReglasMus(), OBJETIVOS["tantos"], POLITICA, marginales(POLITICA),
                              eq, JUEGO, (), True, 30_000, 99)
        monkeypatch.setattr(cli, "iterar_tras_mus", lambda *a, **k: mesa)
        assert main(["tras-mus", "--verificar", "20000", "--semilla", "1"]) == 0
        salida = capsys.readouterr().out
        assert "Punto fijo alcanzado" in salida
        assert "Cartas pedidas" in salida and "Verificación con 20000" in salida
        # con la misma semilla que la mesa, la verificación no sería independiente
        assert main(["tras-mus", "--verificar", "1000", "--semilla", "99"]) == 1
        assert "semilla distinta" in capsys.readouterr().err

    def test_descarte_tras_mus_simulado(self, monkeypatch, capsys):
        import mus.__main__ as cli
        eq = equity_simulada(simular_ronda_mus(POLITICA, 30_000, semilla=1), JUEGO)
        mesa = tm.MesaTrasMus(ReglasMus(), OBJETIVOS["tantos"], POLITICA, marginales(POLITICA),
                              eq, JUEGO, (), True, 30_000, 99)
        monkeypatch.setattr(cli, "iterar_tras_mus", lambda *a, **k: mesa)
        monkeypatch.setattr(cli, "cargar_tabla_equity", lambda reglas: JUEGO)
        assert main(["descarte", "R R C S", "--tras-mus", "--n", "5000", "--semilla", "3"]) == 0
        salida = capsys.readouterr().out
        assert "mano fija" in salida and "dar mus cambia" in salida


def test_pesos_por_asiento_generalizan_las_condiciones():
    """Una condición booleana y el mismo filtro como pesos 0/1 dan la misma equity."""
    mascara = con_juego().mascara(TABLA).astype(float)
    pesos = np.ones((4, 330))
    pesos[2] = mascara  # compañero de la posición 1
    por_condicion = equity("A A 4 5", 1, companero=con_juego())
    por_pesos = equity("A A 4 5", 1, pesos=pesos)
    for lance in Lance:
        a, b = por_condicion.por_lance[lance], por_pesos.por_lance[lance]
        assert a.tantos_netos == pytest.approx(b.tantos_netos, abs=1e-12)


# --- Con tablas de equity reales (lentos) -------------------------------------------


@pytest.mark.slow
def test_simulador_sin_descartes_reproduce_la_fase_2():
    """Con la política de quedarse servido, la tabla simulada debe reproducir las
    probabilidades de mesa exactas de la Fase 2."""
    te = calcular_tabla_equity()
    servida = no_descartar(TD_SERVIDO)
    sim = simular_ronda_mus(servida, 1_000_000, semilla=2)
    mesa = tm.MesaTrasMus(CON_SERVIDO, OBJETIVOS["tantos"], servida,
                          np.broadcast_to(P0, (4, 330)).copy(), tm.EquitySimulada(
                              te, np.full((330, 4), np.inf), np.zeros((330, 4))),
                          te, (), True, 0, 0)
    informe = verificar_mesa(mesa, sim, confianza=1 - 0.001 / 84)
    fuera = [(c.asiento, c.lance, c.metrica) for c in informe.agregadas if not c.dentro]
    assert not fuera
