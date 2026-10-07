"""Tests del exportador de la web y de los ficheros de referencia (Fase 4)."""

import json
from pathlib import Path

import numpy as np
import pytest

from mesas_prueba import CORTA_CON_JUEGO, JUEGO, TABLA, TD, mesa_de
from mus.__main__ import main
from mus.cartas import parsear_mano
from mus.cortar import PoliticaCorte, valorar_corte
from mus.evaluacion import resolver_mano
from mus.reglas import ReglasMus, Variante
from mus.senas import SENAS
from mus.tablas import potencias_codigo
from mus.web import (
    ESCALA_PROBABILIDAD,
    ESCALA_TANTOS,
    SEMILLA_WEB,
    TIPOS_MESA,
    calcular_decisiones,
    cargar_decisiones,
    comprobar_manifiesto,
    consultar_datos,
    datos_equity,
    enteros,
    exportar_datos_web,
    exportar_referencia,
    factor_corte,
)

MESA = mesa_de(CORTA_CON_JUEGO, 20_000)
CURVA = [(0.0, 1.0), (0.5, 0.4), (1.0, 0.1)]
MANOS = [TABLA.indice(parsear_mano(m)) for m in ("R C 5 4", "A A 4 5")]


def leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


# --- Utilidades -------------------------------------------------------------------------


def test_enteros():
    assert enteros([0.12344, -0.5004, np.nan, 1], 1000) == [123, -500, None, 1000]
    assert enteros(np.array([[1.0, 2.0], [3.0, np.inf]])) == [1, 2, 3, None]


def test_datos_equity_orden_y_escalas():
    datos = datos_equity(JUEGO)
    assert len(datos) == 330 * 4 * 5 * 4
    h, p, l, m = TABLA.indice(parsear_mano("R C S A")), 2, 3, 3  # juego, tantos
    assert datos[((h * 4 + p) * 5 + l) * 4 + m] == ESCALA_TANTOS * JUEGO.tantos_netos[h, p, l]
    assert datos[((h * 4 + p) * 5 + l) * 4 + 1] == ESCALA_PROBABILIDAD


def test_factor_corte():
    normal = next(t for t in TIPOS_MESA if t.id == "normal")
    assert factor_corte(normal, CURVA) == 0.67  # 0,3 está a un tercio entre 0,4 (λ=0,5) y 0,1 (λ=1)
    assert factor_corte(next(t for t in TIPOS_MESA if t.id == "se-corta"), CURVA) == 1.0
    with pytest.raises(ValueError):
        factor_corte(normal, [(0.0, 1.0), (1.0, 0.5)])  # el modelo no llega a un 30 %
    assert [t.por_defecto for t in TIPOS_MESA].count(True) == 1


# --- Decisiones mano a mano ---------------------------------------------------------------


@pytest.fixture(scope="module")
def decisiones():
    return calcular_decisiones(MESA, 1.0, MANOS, n=4_000, n_refinado=8_000)


class TestDecisiones:
    def test_forma_y_casos_sin_calcular(self, decisiones):
        d = decisiones
        assert d.ventaja.shape == (330, 4) and d.opcion_diferencia.shape == (4, 3546)
        calculadas = np.zeros(330, dtype=bool)
        calculadas[MANOS] = True
        assert np.isfinite(d.ventaja[calculadas]).all() and np.isnan(d.ventaja[~calculadas]).all()
        assert (d.repartos[~calculadas] == 0).all()
        assert list(d.inicio[[0, -1]]) == [0, 3546]

    def test_decision_coherente_con_el_intervalo(self, decisiones):
        d = decisiones
        for h in MANOS:
            for p in range(4):
                bajo, alto = d.ventaja[h, p] - d.radio[h, p], d.ventaja[h, p] + d.radio[h, p]
                esperado = 1 if bajo > 0 else -1 if alto < 0 else 0
                assert d.decision[h, p] == esperado
                # las indiferentes se han repetido con más repartos
                if d.repartos[h, p] == 4_000:
                    assert d.decision[h, p] != 0

    def test_igual_que_valorar_corte_y_en_orden_canonico(self, decisiones):
        """Un caso sin refinar reproduce exactamente valorar_corte con su semilla, y
        sus opciones van en el orden de td.opciones (no ordenadas por valor)."""
        d = decisiones
        h, p = next((h, p) for h in MANOS for p in range(1, 5) if d.repartos[h, p - 1] == 4_000)
        ref = valorar_corte(TABLA.manos[h], p, MESA, 4_000, semilla=SEMILLA_WEB + 100 * h + p)
        assert d.ventaja[h, p - 1] == ref.ventaja_mus.media
        tramo = slice(d.inicio[h], d.inicio[h + 1])
        for o in ref.opciones:
            i = TD.opciones[h].index(o.opcion)
            assert d.opcion_diferencia[p - 1, tramo][i] == o.si_hay_mus_frente_a_la_mejor.media
        assert np.nanmax(d.opcion_diferencia[p - 1, tramo]) <= 1e-12  # la mejor, a cero

    def test_cache(self, tmp_path):
        a = cargar_decisiones(MESA, 1.0, MANOS[:1], n=2_000, n_refinado=0, directorio=tmp_path)
        assert len(list(tmp_path.glob("web_*.npz"))) == 1
        b = cargar_decisiones(MESA, 1.0, MANOS[:1], n=2_000, n_refinado=0, directorio=tmp_path)
        np.testing.assert_array_equal(a.opcion_si_hay_mus, b.opcion_si_hay_mus)
        assert b.factor_corte == 1.0

    @pytest.mark.slow
    def test_en_paralelo_da_lo_mismo(self, decisiones):
        paralelo = calcular_decisiones(MESA, 1.0, MANOS, n=4_000, n_refinado=8_000, procesos=2)
        np.testing.assert_array_equal(paralelo.ventaja, decisiones.ventaja)
        np.testing.assert_array_equal(paralelo.opcion_radio, decisiones.opcion_radio)


# --- Datos de la web ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def datos(tmp_path_factory):
    directorio = tmp_path_factory.mktemp("datos")
    mesa = mesa_de(PoliticaCorte.nunca(330), 20_000)
    escritos = exportar_datos_web(directorio / "web", manos=MANOS[:1], n=2_000, n_refinado=0,
                                  procesos=1, tabla_equity=lambda c: JUEGO,
                                  construir_mesa=lambda l: mesa, curva=CURVA,
                                  directorio_cache=directorio / "cache")
    return directorio / "web", escritos


class TestDatosWeb:
    def test_manifiesto_y_huellas(self, datos):
        directorio, escritos = datos
        assert escritos[-1].name == "manifiesto.json"
        assert comprobar_manifiesto(directorio) == []
        m = leer(directorio / "manifiesto.json")
        assert set(m["ficheros"]) == {r.relative_to(directorio).as_posix() for r in escritos[:-1]}
        reparto = directorio / "equity" / "reparto.json"
        original = reparto.read_bytes()
        reparto.write_text("{}", encoding="utf-8")
        assert comprobar_manifiesto(directorio) == ["equity/reparto.json no coincide con su huella"]
        reparto.write_bytes(original)

    def test_contenido_del_manifiesto(self, datos):
        m = leer(datos[0] / "manifiesto.json")
        assert m["manos"] == [x.texto(TABLA.baraja) for x in TABLA.manos]
        assert m["reglas"]["variante"] == "8reyes"
        inicio, conservadas = m["descartes"]["inicio"], m["descartes"]["conservadas"]
        assert len(inicio) == 331 and inicio[-1] == len(conservadas) == 3546
        potencias = potencias_codigo(TABLA.baraja)
        assert conservadas[inicio[7]:inicio[8]] == [int(np.array(o.conservadas) @ potencias)
                                                    for o in TD.opciones[7]]
        assert [s["id"] for s in m["senas"]] == [s.id for s in SENAS]
        assert all(s["gesto"] and s["cartas"] for s in m["senas"])
        assert len(m["tablas_equity"]) == 17 and m["tablas_equity"][0]["senas"] == []
        assert [x["id"] for x in m["mesas"]] == ["mucho-mus", "normal", "se-corta"]
        assert [x["factor_corte"] for x in m["mesas"]] == [0.33, 0.67, 1.0]

    def test_ficheros_de_equity(self, datos):
        directorio = datos[0]
        m = leer(directorio / "manifiesto.json")
        for t in m["tablas_equity"]:
            f = leer(directorio / t["fichero"])
            assert f["datos"] == datos_equity(JUEGO)
            if t["senas"]:
                assert f["condicion"]["senas"] == t["senas"]
                assert f["condicion"]["manos"] == t["manos"]

    def test_fichero_de_mesa(self, datos):
        directorio = datos[0]
        f = leer(directorio / "mesa-normal.json")
        decision, opciones = f["decision"], f["opciones"]
        assert all(len(v) == 1320 for k, v in decision.items() if k != "orden")
        assert all(len(v) == 4 * 3546 for k, v in opciones.items() if k != "orden")
        assert len(f["tras_mus"]["datos"]) == 330 * 4 * 5 * 4
        h = MANOS[0]
        assert decision["ventaja"][4 * h] is not None and decision["ventaja"][4 * h + 4] is None
        assert decision["repartos"][4 * h] == 2_000
        assert decision["decision"][4 * h] in (-1, 0, 1)

    def test_consultar_datos(self, datos):
        directorio = datos[0]
        mano = TABLA.manos[MANOS[0]].texto(TABLA.baraja)
        c = consultar_datos(directorio, mano, 1)
        assert c.mesa == "normal" and c.senas == ()
        juego = c.equity["juego"]
        h = MANOS[0]
        assert juego["tantos"] == pytest.approx(JUEGO.tantos_netos[h, 0, 3], abs=1e-3)
        assert c.decision["repartos"] == 2_000 and c.decision["decision"] in (-1, 0, 1)
        validas = [o for o in c.opciones if o["si_hay_mus"] is not None]
        assert validas[0]["diferencia"] == 0 and len(c.opciones) == len(TD.opciones[h])
        # sin decisión precalculada (otra posición sí, otra mano no)
        otra = TABLA.manos[MANOS[1]].texto(TABLA.baraja)
        assert consultar_datos(directorio, otra, 2, "se-corta").decision["ventaja"] is None

    def test_consultar_con_senas(self, datos):
        directorio = datos[0]
        c = consultar_datos(directorio, "A A 4 5", 1, senas=["dos-reyes", "31"])
        assert c.senas == ("dos-reyes", "31")
        with pytest.raises(ValueError, match="Ninguna mano"):
            consultar_datos(directorio, "A A 4 5", 1, senas=["dos-reyes", "tres-reyes"])
        with pytest.raises(ValueError, match="desconocidas"):
            consultar_datos(directorio, "A A 4 5", 1, senas=["cuatro-reyes"])

    def test_cli_consultar(self, datos, capsys):
        mano = TABLA.manos[MANOS[0]].texto(TABLA.baraja)
        assert main(["consultar-web", mano, "--datos", str(datos[0]), "--senas", "31"]) == 0
        salida = capsys.readouterr().out
        assert "¿Mus o corto?" in salida and "señas del compañero: 31" in salida

    def test_solo_ocho_reyes(self, tmp_path):
        with pytest.raises(ValueError, match="8 reyes"):
            exportar_datos_web(tmp_path, ReglasMus(variante=Variante.CUATRO_REYES))


# --- Ficheros de referencia ------------------------------------------------------------------


@pytest.fixture(scope="module")
def referencia(tmp_path_factory):
    directorio = tmp_path_factory.mktemp("referencia")
    exportar_referencia(directorio, repartos=300)
    return {r.stem: leer(r) for r in directorio.glob("*.json")}


class TestReferencia:
    def test_evaluacion(self, referencia):
        e = referencia["evaluacion"]
        assert len(e["manos"]) == 330
        for i, (texto, conteos, codigo, comb, suma, pares, pp, pj, fuerza) in enumerate(e["manos"]):
            assert texto == TABLA.manos[i].texto(TABLA.baraja)
            assert codigo == TABLA.codigos[i] and comb == TABLA.combinaciones[i]
            assert (suma, pares, pp, pj) == (TABLA.suma[i], TABLA.jugada_pares[i],
                                             TABLA.puntos_pares[i], TABLA.puntos_juego[i])
        assert sum(m[3] for m in e["manos"]) == 91_390
        lecturas = {x["entrada"]: x for x in e["lectura"]}
        assert lecturas["3 3 11 5"]["mano"] == "R R C 5"
        assert lecturas["2 2 4 5"]["mano"] == "5 4 A A"
        assert lecturas["R R C"]["error"] and lecturas[""]["error"]

    def test_lances(self, referencia):
        filas = referencia["lances"]["repartos"]
        assert len(filas) == 12 + 300
        for manos, resultado in filas[:60]:
            esperado = resolver_mano([parsear_mano(t) for t in manos])
            assert resultado == [[r.ganador or 0, r.tantos] for r in esperado.values()]
        # Todo empatado: la mano gana grande, chica y juego (cuatro 31); no hay pares ni punto.
        assert filas[0][1] == [[1, 1], [1, 1], [0, 0], [1, 6], [0, 0]]

    def test_descartes(self, referencia):
        d = referencia["descartes"]
        assert sum(len(m["opciones"]) for m in d["manos"]) == 3546
        pesos = np.array(d["pesos_huella"])
        filas = {(x["mano"], x["conservadas"]): x["numeradores"] for x in d["distribuciones"]}
        comprobadas = 0
        for m in d["manos"]:
            for codigo, k, denominador, pares, medias, duples, juego, j31, h1, h2 in m["opciones"]:
                assert 1 <= k <= 4 and medias + duples <= pares <= denominador and j31 <= juego
                numeradores = filas.get((m["texto"], codigo))
                if numeradores is None:
                    continue
                v = np.zeros(330, dtype=np.int64)
                for j, x in numeradores:
                    v[j] = x
                assert v.sum() == denominador
                assert [int(v @ pesos[0]), int(v @ pesos[1])] == [h1, h2]
                assert int(v[TABLA.jugada_pares > 0].sum()) == pares
                assert int(v[TABLA.suma == 31].sum()) == j31
                comprobadas += 1
        assert comprobadas == len(filas) > 200

    def test_huellas_caben_en_doble_precision(self, referencia):
        maximo = max(max(f[-2:]) for m in referencia["descartes"]["manos"] for f in m["opciones"])
        assert maximo < 2 ** 53


def test_cli_solo_referencia(tmp_path, capsys):
    assert main(["exportar-web", "--solo-referencia", "--referencia", str(tmp_path)]) == 0
    assert {r.name for r in tmp_path.iterdir()} == {"evaluacion.json", "lances.json",
                                                    "descartes.json"}
    assert "Referencia" in capsys.readouterr().out


def test_cli_rechaza_cuatro_reyes(tmp_path):
    assert main(["--variante", "4reyes", "exportar-web", "--salida", str(tmp_path / "d"),
                 "--referencia", str(tmp_path / "r")]) == 1


# --- Ficheros versionados en git -------------------------------------------------------------

RAIZ = Path(__file__).resolve().parents[1]


def test_referencia_versionada_al_dia(tmp_path):
    """Si cambia el motor o el exportador, hay que regenerar los ficheros de referencia
    (python -m mus exportar-web --solo-referencia): el núcleo en TypeScript se prueba con ellos."""
    for ruta in exportar_referencia(tmp_path):
        versionado = RAIZ / "web" / "test" / "referencia" / ruta.name
        assert versionado.read_bytes() == ruta.read_bytes(), f"{ruta.name} está desfasado"


def test_datos_versionados_integros_y_de_esta_version():
    import mus
    from mus import cortar, equity, tras_mus, web

    directorio = RAIZ / "web" / "public" / "datos"
    assert comprobar_manifiesto(directorio) == []
    m = leer(directorio / "manifiesto.json")
    assert m["formato"] == web.FORMATO
    assert m["versiones"] == {"paquete": mus.__version__, "equity": equity.VERSION_MOTOR,
                              "tras_mus": tras_mus.VERSION_SIMULACION,
                              "cortar": cortar.VERSION_SIMULACION,
                              "decisiones": web.VERSION_DECISIONES}, \
        "los datos de la web son de otra versión del motor: regenerarlos con exportar-web"
    assert m["manos"] == [x.texto(TABLA.baraja) for x in TABLA.manos]
