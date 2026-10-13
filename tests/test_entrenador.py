"""Tests del entrenador (Fase 5): valoración de las respuestas y peso de las situaciones."""

import json
from pathlib import Path

import numpy as np
import pytest

from fuerza_bruta import p_habla_exacta
from mesas_prueba import TABLA
from mus.__main__ import main
from mus.cartas import parsear_mano
from mus.cortar import mesa_rivales_razonables, valorar_corte
from mus.entrenador import (
    HABLAN_ANTES,
    MODOS,
    UMBRAL_AJUSTADA,
    UMBRAL_CLARA,
    UMBRAL_DESCARTE,
    UMBRAL_IGUAL,
    ValoracionCorte,
    cargar_mesa,
    consultar,
    contexto,
    ids_de_mesas,
    referencia,
    valorar_decision,
    valorar_descartes,
)
from mus.testigos import CASOS_TESTIGO, comparar
from mus.web import SEMILLA_WEB, enteros, factor_corte_de_mesa

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "web" / "public" / "datos"
C_40_4 = 91_390


def indice(mano: str) -> int:
    return TABLA.indice(parsear_mano(mano))


# --- La regla de valoración ------------------------------------------------------------------


class TestValorarDecision:
    def test_da_igual(self):
        igual = ValoracionCorte(0, 0, 0, 0)
        assert valorar_decision(0, 400) == igual            # el IC contiene el 0
        assert valorar_decision(1, UMBRAL_IGUAL - 1) == igual
        assert valorar_decision(-1, -(UMBRAL_IGUAL - 1)) == igual
        assert valorar_decision(1, 0) == igual

    def test_quien_elige_lo_contrario_pierde_la_ventaja(self):
        assert valorar_decision(1, 412) == ValoracionCorte(1, 2, 0, 412)
        assert valorar_decision(-1, -1069) == ValoracionCorte(-1, 2, 1069, 0)

    def test_por_poco_y_clara(self):
        assert valorar_decision(1, UMBRAL_IGUAL).intensidad == 1
        assert valorar_decision(1, UMBRAL_CLARA - 1).intensidad == 1
        assert valorar_decision(-1, -UMBRAL_CLARA).intensidad == 2


class TestValorarDescartes:
    def test_de_mejor_a_peor(self):
        v = valorar_descartes([100, 500, None, 480, 300], [-400, 0, None, -20, -200],
                              [30, 0, None, 25, 30])
        assert [o.indice for o in v] == [1, 3, 4, 0]         # la que no tiene valor no sale
        assert [o.puesto for o in v] == [0, 1, 2, 3]
        assert [o.vale for o in v] == [True, True, False, False]   # −20 está dentro de su margen
        assert [o.perdidos for o in v] == [0, 0, 200, 400]

    def test_casi_igual_por_el_umbral_o_por_el_margen(self):
        v = valorar_descartes([500, 481, 480], [0, -(UMBRAL_DESCARTE - 1), -UMBRAL_DESCARTE],
                              [0, 5, 5])
        assert [o.vale for o in v] == [True, True, False]
        assert v[2].perdidos == UMBRAL_DESCARTE
        assert valorar_descartes([500, 440], [0, -60], [0, 60])[1].vale   # justo en el margen

    def test_empate_gana_el_orden_canonico(self):
        """Con los mismos tantos, va primero la opción que está antes: la ordenación es
        estable, como la de la web."""
        v = valorar_descartes([500, 500], [-1, 0], [10, 0])
        assert [o.indice for o in v] == [0, 1] and v[0].perdidos == v[1].perdidos == 0

    def test_sin_opciones_valoradas(self):
        assert valorar_descartes([None, None], [None, None], [None, None]) == []


# --- Las mesas publicadas ----------------------------------------------------------------------


@pytest.fixture(scope="module", params=["mucho-mus", "normal", "se-corta"])
def mesa(request):
    return cargar_mesa(DATOS, request.param)


@pytest.fixture(scope="module")
def normal():
    return cargar_mesa(DATOS)


class TestMesa:
    def test_carga(self, normal):
        assert normal.id == "normal" and normal.nombre == "Normal"
        assert normal.n_manos == 330 and normal.n_opciones == 3546
        assert sum(normal.combinaciones) == C_40_4
        assert ids_de_mesas(DATOS) == ["mucho-mus", "normal", "se-corta"]
        with pytest.raises(ValueError, match="desconocido"):
            cargar_mesa(DATOS, "torneo")
        with pytest.raises(ValueError, match="posición"):
            normal.corte(0, 5)

    def test_todo_esta_calculado(self, mesa):
        for h in range(330):
            for p in (1, 2, 3, 4):
                assert mesa.corte(h, p) is not None and mesa.descartes(h, p)
                assert mesa.ventaja_por_lance(h, p) is not None

    def test_los_lances_suman_la_ventaja(self, mesa):
        """Cada cifra se redondea a la milésima por separado: la suma de los cinco
        lances puede diferir de la ventaja en el redondeo, nunca en más."""
        for k in range(1320):
            lances = mesa.por_lance["ventaja"][5 * k:5 * k + 5]
            assert abs(sum(lances) - mesa.decision["ventaja"][k]) <= 3

    def test_la_mano_siempre_habla(self, mesa):
        p = mesa.escala_probabilidad
        assert all(mesa.decision["p_habla"][4 * h] == p for h in range(330))
        assert sum(mesa.peso_corte(h, 1, "mesa") for h in range(330)) == C_40_4 * p

    def test_cuanto_mas_tarde_menos_veces_se_habla(self, mesa):
        por_posicion = [sum(mesa.peso_corte(h, p, "mesa") for h in range(330))
                        for p in (1, 2, 3, 4)]
        assert por_posicion == sorted(por_posicion, reverse=True) and por_posicion[3] > 0

    def test_decisiones_por_mano(self, mesa):
        corte, descarte = (mesa.decisiones_por_mano(e) for e in ("corte", "descarte"))
        f_corte, f_descarte = corte[0] / corte[1], descarte[0] / descarte[1]
        assert 0.25 < f_corte < 1          # de mano se habla siempre: al menos 1 de cada 4
        assert 0 < f_descarte < f_corte    # para descartarse hay que hablar y que haya mus

    def test_en_las_mesas_que_cortan_mas_hay_menos_que_decidir(self):
        fracciones = []
        for id_mesa in ("mucho-mus", "normal", "se-corta"):
            n, d = cargar_mesa(DATOS, id_mesa).decisiones_por_mano("corte")
            fracciones.append(n / d)
        assert fracciones == sorted(fracciones, reverse=True)

    def test_descarte_como_en_la_mesa(self, normal):
        """Solo se plantean descartes con las manos con que el entrenador daría mus."""
        assert all(normal.peso_descarte(indice("R R C S"), p, "mesa") == 0 for p in (1, 2, 3, 4))
        h = indice("R C 5 4")
        k = 4 * h
        assert normal.corte(h, 1).veredicto == 1
        assert normal.peso_descarte(h, 1, "mesa") == (
            normal.combinaciones[h] * normal.decision["p_habla"][k]
            * normal.decision["p_mus_despues"][k]) > 0
        for h in range(330):
            for p in (1, 2, 3, 4):
                corta = normal.corte(h, p).veredicto == -1
                assert (normal.peso_descarte(h, p, "mesa") == 0) == corta

    def test_ajustadas(self, mesa):
        con_peso = 0
        for h in range(330):
            for p in (1, 2, 3, 4):
                v = mesa.corte(h, p)
                perdidos = max(v.perdidos_mus, v.perdidos_corto)
                esperado = mesa.combinaciones[h] if 0 < perdidos < UMBRAL_AJUSTADA else 0
                assert mesa.peso_corte(h, p, "ajustadas") == esperado
                con_peso += esperado > 0
                costes = [o.perdidos for o in mesa.descartes(h, p) if not o.vale]
                ajustado = bool(costes) and min(costes) < UMBRAL_AJUSTADA
                assert (mesa.peso_descarte(h, p, "ajustadas") > 0) == ajustado
        assert 100 < con_peso < 660        # ni casi ninguna ni la mayoría

    def test_modo_y_ejercicio_desconocidos(self, normal):
        with pytest.raises(ValueError, match="Modo"):
            normal.peso_corte(0, 1, "repaso")
        with pytest.raises(ValueError, match="Modo"):
            normal.peso_descarte(0, 1, "repaso")
        with pytest.raises(ValueError, match="Ejercicio"):
            normal.pesos("envite", "mesa")

    def test_los_pesos_son_exactos_en_javascript(self, mesa):
        for ejercicio in ("corte", "descarte"):
            for modo in MODOS:
                assert sum(mesa.pesos(ejercicio, modo)) < 2 ** 53


@pytest.fixture(scope="module")
def ref():
    return referencia(DATOS)


class TestReferencia:
    def test_estructura(self, ref):
        assert ref["umbrales"] == {"igual": 30, "clara": 150, "descarte": 20, "ajustada": 200}
        assert list(ref["mesas"]) == ["mucho-mus", "normal", "se-corta"] and ref["modos"] == list(MODOS)
        assert ref["hablan_antes"] == list(HABLAN_ANTES) and len(HABLAN_ANTES) == 4
        for datos in ref["mesas"].values():
            corte, descarte = datos["corte"], datos["descarte"]
            assert all(len(corte[k]) == 1320 for k in ("veredicto", "intensidad", "perdidos_mus",
                                                       "perdidos_corto"))
            assert len(descarte["perdidos"]) == len(descarte["vale"]) == 4 * 3546
            assert len(descarte["mejor"]) == 1320
            for bloque in (corte, descarte):
                assert all(len(bloque["pesos"][modo]) == 1320 for modo in MODOS)

    def test_coherencia(self, ref, normal):
        corte, descarte = ref["mesas"]["normal"]["corte"], ref["mesas"]["normal"]["descarte"]
        for k in range(1320):
            # como mucho pierde una de las dos respuestas, y solo si no da igual
            assert min(corte["perdidos_mus"][k], corte["perdidos_corto"][k]) == 0
            pierde = max(corte["perdidos_mus"][k], corte["perdidos_corto"][k])
            assert (pierde > 0) == (corte["veredicto"][k] != 0) == (corte["intensidad"][k] != 0)
        assert all(p >= 0 for p in descarte["perdidos"])
        # una opción vale si y solo si no pierde nada, y la mejor siempre vale
        assert all((v == 1) == (p == 0) for v, p in zip(descarte["vale"], descarte["perdidos"]))
        h, p = indice("R C 5 4"), 1
        mejor = descarte["mejor"][4 * h + p - 1]
        assert descarte["vale"][(p - 1) * 3546 + normal.inicio[h] + mejor] == 1

    def test_contexto(self):
        assert contexto("Normal") == ("La mejor jugada contra una mesa «Normal», sin contar "
                                      "envites, señas ni las cartas que piden los demás.")


class TestConsulta:
    def test_consultar(self):
        c = consultar(DATOS, "4 5 C R", 1)                  # se lee en cualquier orden
        assert c.mano == "R C 5 4" and c.mesa == "normal" and c.p_habla == 1
        assert c.corte.veredicto == 1 and c.corte.perdidos_corto == round(1000 * c.ventaja) > 0
        assert set(c.por_lance) == {"grande", "chica", "pares", "juego", "punto"}
        assert c.opciones[0].valoracion.puesto == 0 and c.opciones[0].me_quedo == "R C"
        assert 0 < c.probabilidad["corte"]["mesa"] < 0.01
        assert c.probabilidad["descarte"]["mesa"] > 0

    def test_cli(self, capsys):
        assert main(["entrenador", "R R C S", "--posicion", "4", "--mesa", "se-corta",
                     "--datos", str(DATOS)]) == 0
        salida = capsys.readouterr().out
        assert "Los tres anteriores han dado mus." in salida and "«Se corta mucho»" in salida
        assert "CORTA (claro)" in salida and "lance a lance" in salida
        assert "no sale: el entrenador corta con ella." in salida

    def test_cli_mano_mal_escrita(self, capsys):
        assert main(["entrenador", "R R C", "--datos", str(DATOS)]) == 1


# --- Los datos publicados frente al motor (necesitan resultados/cache) -------------------------


@pytest.fixture(scope="module")
def real():
    """La mesa «Normal» del motor (sale de resultados/cache) y la misma, leída de los ficheros."""
    lam = factor_corte_de_mesa("normal")
    return mesa_rivales_razonables(factor_corte=lam), cargar_mesa(DATOS, "normal")


@pytest.mark.slow
class TestDatosFrenteAlMotor:
    @pytest.mark.parametrize("mano, posicion", [("R C 5 4", 1), ("7 7 4 4", 2), ("R R C S", 4),
                                               ("A A 4 5", 3)])
    def test_reproducen_la_simulacion(self, real, mano, posicion):
        """Lo publicado es lo que da valorar_corte con la semilla del exportador: la
        ventaja, su desglose por lance y la probabilidad de hablar."""
        motor, publicada = real
        m = json.loads((DATOS / "manifiesto.json").read_text(encoding="utf-8"))
        h, k = indice(mano), 4 * indice(mano) + posicion - 1
        repartos = publicada.decision["repartos"][k]
        refinada = repartos == m["calculo"]["repartos_refinado"]
        d = valorar_corte(mano, posicion, motor, repartos,
                          semilla=SEMILLA_WEB + 100 * h + (10 if refinada else 0) + posicion)
        assert enteros([d.ventaja_mus.media], 1000) == [publicada.decision["ventaja"][k]]
        assert enteros([d.p_habla], 10_000) == [publicada.decision["p_habla"][k]]
        assert enteros([e.media for e in d.ventaja_por_lance], 1000) == \
            publicada.por_lance["ventaja"][5 * k:5 * k + 5]
        radios = [(e.intervalo[1] - e.intervalo[0]) / 2 for e in d.ventaja_por_lance]
        assert enteros(radios, 1000) == publicada.por_lance["radio"][5 * k:5 * k + 5]

    @pytest.mark.parametrize("mano", ["R C 5 4", "R R C S", "6 5 4 A"])
    @pytest.mark.parametrize("posicion", [2, 3])
    def test_p_habla_frente_al_calculo_exacto(self, real, mano, posicion):
        """La probabilidad publicada de que te toque hablar (simulada) coincide con la
        exacta, calculada con la política de corte de la mesa."""
        motor, publicada = real
        h = indice(mano)
        k = 4 * h + posicion - 1
        exacta = p_habla_exacta(TABLA, h, posicion, 1 - motor.corte.probabilidades)
        n = publicada.decision["repartos"][k]
        # los pesos están entre 0 y 1: su desviación típica es como mucho 0,5
        assert abs(publicada.decision["p_habla"][k] / 10_000 - exacta) < 4 * 0.5 / np.sqrt(n) + 5e-5

    def test_casos_testigo(self, real):
        """Los casos testigo dan en el entrenador lo mismo que `python -m mus testigos`
        (el motor, simulando otra vez con otra semilla)."""
        motor, publicada = real
        for caso in CASOS_TESTIGO:
            modelo = comparar(caso, motor, 100_000, semilla=1).modelo
            v = publicada.corte(indice(caso.mano), caso.posicion)
            esperado = {"mus": 1, "cortar": -1, "indiferente": 0}[modelo.decision]
            ventaja = modelo.ventaja_mus.media
            if abs(ventaja) > 0.1:            # decisiones claras: el mismo veredicto
                assert v.veredicto == esperado, caso
            else:                             # ajustadas: al menos, no lo contrario
                assert v.veredicto * esperado >= 0, caso
