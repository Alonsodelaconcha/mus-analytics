"""Tests de la Fase 3c: cortar o dar mus, con el efecto de selección."""

import numpy as np
import pytest

import mus.cortar as mc
from mesas_prueba import CORTA_CON_JUEGO, DESCARTE, JUEGO, TABLA, mesa_de
from mus.__main__ import main
from mus.cartas import parsear_mano
from mus.cortar import (
    PoliticaCorte,
    SimulacionCorte,
    iterar_corte,
    simular_corte,
    valorar_corte,
)
from mus.descarte import OBJETIVOS, objetivo_con_pesos
from mus.equity import equity
from mus.testigos import CASOS_TESTIGO, COMPANERO_FLOJO, COMPANERO_VA_BIEN, comparar
from mus.tras_mus import valorar_opciones_simuladas


class TestPoliticaCorte:
    def test_nunca(self):
        nunca = PoliticaCorte.nunca(330)
        iniciales = np.array([[0, 1, 2, 3], [329, 5, 6, 7]])
        np.testing.assert_array_equal(nunca.no_cortan(iniciales), 1)
        assert not nunca.principal().any()

    def test_mezclar(self):
        mezcla = PoliticaCorte.nunca(330).mezclar(CORTA_CON_JUEGO, 0.25)
        np.testing.assert_allclose(mezcla.probabilidades, 0.25 * CORTA_CON_JUEGO.probabilidades)
        assert mezcla.huella() != CORTA_CON_JUEGO.huella()

    def test_objetivo_debe_ser_de_tantos(self):
        with pytest.raises(ValueError):
            simular_corte(PoliticaCorte.nunca(330), DESCARTE, 10, objetivo=OBJETIVOS["grande"])


class TestSimulacion:
    def test_sin_cortes_siempre_hay_mus(self):
        sim = simular_corte(PoliticaCorte.nunca(330), DESCARTE, 30_000, semilla=2)
        assert sim.hay_mus == pytest.approx(30_000)
        np.testing.assert_allclose(sim.alcance.sum(axis=1), 30_000)
        np.testing.assert_allclose(sim.hay_mus_por_mano.sum(axis=1), 30_000)

    def test_la_mano_siempre_habla(self):
        sim = simular_corte(CORTA_CON_JUEGO, DESCARTE, 30_000, semilla=3)
        assert sim.alcance[0].sum() == pytest.approx(30_000)
        assert sim.alcance[3].sum() < sim.alcance[2].sum() < sim.alcance[1].sum() < 30_000
        assert 0 < sim.hay_mus < sim.alcance[3].sum()

    @pytest.mark.parametrize("mano, posicion", [("R R C S", 2), ("A A 4 5", 4)])
    def test_valor_de_cortar_frente_al_motor_exacto(self, mano, posicion):
        """Cortar = jugar con las manos iniciales, sabiendo que los anteriores dieron
        mus: es la equity exacta de la Fase 2 con esos asientos ponderados por
        P(dar mus). Verifica los pesos de selección de la simulación."""
        sim = simular_corte(CORTA_CON_JUEGO, DESCARTE, 400_000, semilla=4)
        h = TABLA.indice(parsear_mano(mano))
        v, e = sim.valor_cortar()
        pesos = np.ones((4, 330))
        pesos[:posicion - 1] = 1 - CORTA_CON_JUEGO.probabilidades[:posicion - 1]
        exacto = equity(mano, posicion, pesos=pesos).tantos_netos
        assert abs(v[posicion - 1, h] - exacto) < 4 * e[posicion - 1, h]

    def test_pesos_por_lance(self):
        solo_juego = objetivo_con_pesos("grande=0,chica=0,pares=0,punto=0")
        sim = simular_corte(PoliticaCorte.nunca(330), DESCARTE, 20_000, semilla=5,
                            objetivo=solo_juego)
        v, _ = sim.valor_cortar()
        h = TABLA.indice(parsear_mano("A A 4 5"))  # sin juego: con solo juego, nunca cobra
        assert v[0, h] <= 0


class TestValorarCorte:
    def test_postre_sin_cortes_coincide_con_la_3b(self):
        """Si nadie corta, dar mus de postre vale lo de la 3b: mejor descarte simulado
        con la mano fija menos la equity exacta de cortar."""
        mesa = mesa_de(PoliticaCorte.nunca(330))
        d = valorar_corte("R R C S", 4, mesa, 100_000, semilla=6)
        assert d.p_mus_despues == 1
        cortar = equity("R R C S", 4).tantos_netos
        assert d.cortar.contiene(cortar) or abs(d.cortar.media - cortar) < 0.05
        mus_3b = valorar_opciones_simuladas("R R C S", 4, DESCARTE, 100_000, semilla=6)[0]
        assert abs(d.mus.media - mus_3b.tantos.media) < 0.05

    def test_decision(self):
        mesa = mesa_de(PoliticaCorte.nunca(330))
        d = valorar_corte("R C 5 4", 1, mesa, 50_000, semilla=7)
        bajo, alto = d.ventaja_mus.intervalo
        assert d.decision == ("mus" if bajo > 0 else "cortar" if alto < 0 else "indiferente")
        assert d.opciones[0].frente_a_la_mejor.media == 0
        medias = [o.valor_mus.media for o in d.opciones]
        assert medias == sorted(medias, reverse=True)

    @pytest.mark.parametrize("posicion", [1, 3, 4])
    def test_valores_si_hay_mus(self, posicion):
        """Si hay mus, la diferencia con el mejor descarte es la de dar mus dividida
        por P(que den mus los que hablan después): E_w[d·X] / E_w[d]."""
        mesa = mesa_de(CORTA_CON_JUEGO)
        d = valorar_corte("R C 5 4", posicion, mesa, 20_000, semilla=8)
        assert d.opciones[0].si_hay_mus_frente_a_la_mejor.media == 0
        for o in d.opciones:
            assert o.si_hay_mus_frente_a_la_mejor.media == pytest.approx(
                o.frente_a_la_mejor.media / d.p_mus_despues, abs=1e-9)
            if posicion == 4:  # nadie habla después: dar mus = jugar tras el mus
                assert d.p_mus_despues == 1
                assert o.si_hay_mus.media == pytest.approx(o.valor_mus.media, abs=1e-9)
        medias = [o.si_hay_mus.media for o in d.opciones]
        assert medias == sorted(medias, reverse=True)  # el mismo orden que dar mus

    def test_condicion_imposible(self):
        mesa = mesa_de(CORTA_CON_JUEGO)
        from mus.condiciones import con_juego
        # de postre, el compañero (asiento 2) dio mus: con esta política no tiene juego
        with pytest.raises(ValueError):
            valorar_corte("A A 4 5", 4, mesa, 5_000, companero=con_juego(), semilla=1)


class TestIteracion:
    def test_amortiguacion_y_convergencia(self, monkeypatch):
        """Con una ventaja fija (cortar siempre es mejor por 0,1), la política se acerca
        a la mejor respuesta con pesos 1/(t+1) y la explotabilidad baja como 1/(t+1)."""
        def simulada(corte, descarte, n, semilla, objetivo, directorio):
            uno = np.ones((4, 330))
            return SimulacionCorte(n=1000, alcance=uno * 1000 / 330, alcance_cuadrado=uno,
                                   cortar=uno, cortar_cuadrado=uno,
                                   ventaja=-0.1 * uno * 1000 / 330, ventaja_cuadrado=uno * 1e-6,
                                   hay_mus_por_mano=uno, mesa=mc.simular_corte(
                                       PoliticaCorte.nunca(330), DESCARTE, 10, semilla=1).mesa,
                                   hay_mus=10.0, valor_pareja_mano=0.0)
        monkeypatch.setattr(mc, "_simulacion_cacheada", simulada)
        monkeypatch.setattr(mc, "cargar_tabla_equity", lambda reglas, directorio=None: JUEGO)
        mesa = iterar_corte(max_iteraciones=5, tolerancia=1e-9)
        e = [i.explotabilidad_corte for i in mesa.historia]
        assert [i.amortiguacion for i in mesa.historia] == [1 / (t + 1) for t in range(1, 6)]
        assert e[0] == pytest.approx(0.4) and e[1] == pytest.approx(0.2)  # 4 asientos × 0,1
        assert e == sorted(e, reverse=True) and not mesa.convergio
        mesa = iterar_corte(max_iteraciones=5, tolerancia=0.15)
        assert mesa.convergio and len(mesa.historia) == 3


class TestTestigos:
    def test_casos(self):
        assert len(CASOS_TESTIGO) == 16
        assert {c.posicion for c in CASOS_TESTIGO} == {1, 4}

    def test_condiciones_del_companero(self):
        flojo, bien = COMPANERO_FLOJO.mascara(TABLA), COMPANERO_VA_BIEN.mascara(TABLA)
        assert flojo.any() and bien.any() and not (flojo & bien).any()
        assert bien[TABLA.indice(parsear_mano("R R 5 4"))]       # dos reyes
        assert flojo[TABLA.indice(parsear_mano("C 6 5 4"))]      # nada

    def test_comparar(self):
        mesa = mesa_de(PoliticaCorte.nunca(330))
        caso = next(c for c in CASOS_TESTIGO if c.mano == "R C 5 4" and c.posicion == 1)
        c = comparar(caso, mesa, 20_000, semilla=1)
        assert c.perdida_decision >= 0 and c.perdida_descarte is not None
        assert c.perdida_descarte >= 0


class TestCLI:
    @pytest.fixture(autouse=True)
    def mesa_rapida(self, monkeypatch):
        import mus.__main__ as cli
        mesa = mesa_de(CORTA_CON_JUEGO, 30_000)
        monkeypatch.setattr(cli, "iterar_corte", lambda *a, **k: mesa)
        monkeypatch.setattr(cli, "mesa_rivales_razonables", lambda *a, **k: mesa)

    def test_cortar(self, capsys):
        assert main(["cortar", "R C 5 4", "--posicion", "1", "--n", "5000", "--semilla", "1"]) == 0
        salida = capsys.readouterr().out
        assert "Dar mus - cortar" in salida and "Si hay mus" in salida

    def test_corte_mesa(self, capsys, tmp_path):
        assert main(["corte-mesa", "--csv", str(tmp_path / "c.csv")]) == 0
        assert "P(hay mus)" in capsys.readouterr().out
        assert len((tmp_path / "c.csv").read_text(encoding="utf-8").splitlines()) == 1 + 4 * 330

    def test_testigos(self, capsys):
        assert main(["testigos", "--n", "3000"]) == 0
        salida = capsys.readouterr().out
        assert "A A 4 5 de postre, preguntando al compañero" in salida

    def test_factor_corte_invalido(self, monkeypatch):
        import mus.cortar as cortar
        with pytest.raises(ValueError):
            cortar.mesa_rivales_razonables(factor_corte=1.5)
