"""Tests de las distribuciones exactas, la exportación y la CLI."""

import csv
import json

import numpy as np
import pytest

from mus.__main__ import main
from mus.analisis import (
    distribucion_exacta,
    distribucion_sumas,
    exportar_equity_csv,
    exportar_equity_json,
    exportar_rankings_csv,
    exportar_tabla_csv,
    graficar_condicion,
    graficar_distribucion,
    graficar_posicion,
    ranking,
)
from mus.condiciones import sin_pares
from mus.equity import POSICIONES, TablaEquity, equity
from mus.evaluacion import Lance
from mus.reglas import ReglasMus, Variante
from mus.tablas import construir_tabla


def test_valores_de_referencia_ocho_reyes():
    d = distribucion_exacta(construir_tabla())
    assert d["Al menos un rey"] == pytest.approx(0.607, abs=5e-4)
    assert d["Pares (cualquiera)"] == pytest.approx(0.566, abs=5e-4)
    # P(al menos un rey) exacta: 1 - C(32,4)/C(40,4)
    assert d["Al menos un rey"] == pytest.approx(1 - 35960 / 91390, abs=1e-12)


@pytest.mark.parametrize("variante", list(Variante))
def test_distribuciones_coherentes(variante):
    tabla = construir_tabla(ReglasMus(variante=variante))
    d = distribucion_exacta(tabla)
    assert d["Par"] + d["Medias"] + d["Duples"] == pytest.approx(d["Pares (cualquiera)"])
    juegos = sum(p for nombre, p in d.items() if nombre.startswith("Juego "))
    assert juegos == pytest.approx(d["Juego"])
    sumas = distribucion_sumas(tabla)
    assert sum(sumas.values()) == pytest.approx(1.0)
    assert 38 not in sumas and 39 not in sumas  # imposibles con 4 cartas
    assert set(s for s in sumas if s >= 31) == set(tabla.reglas.orden_juego)


def test_exportar_csv(tmp_path):
    ruta = exportar_tabla_csv(construir_tabla(), tmp_path / "manos.csv")
    with ruta.open(encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    assert len(filas) == 330
    assert sum(int(f["combinaciones"]) for f in filas) == 91390
    rrrr = next(f for f in filas if f["mano"] == "R R R R")
    assert (rrrr["pares"], rrrr["suma"], rrrr["combinaciones"]) == ("duples", "40", "70")


def test_grafica(tmp_path):
    ruta = graficar_distribucion(construir_tabla(), tmp_path / "dist.png")
    assert ruta.stat().st_size > 0


@pytest.fixture(scope="module")
def tabla_equity_pequena():
    """Tabla de equity con valores reales solo en tres manos (A A A A, una
    intermedia y R R R R): las exportaciones no dependen de que estén todas."""
    tabla = construir_tabla()
    arrays = [np.zeros((tabla.n_manos, 4, 5)) for _ in range(4)]
    for i in (0, tabla.n_manos // 2, tabla.n_manos - 1):
        for p in POSICIONES:
            for l, e in enumerate(equity(tabla.manos[i], p).por_lance.values()):
                for a, v in zip(arrays, (e.p_se_juega, e.p_gana_individual,
                                         e.p_gana_pareja, e.tantos_netos)):
                    a[i, p - 1, l] = v
    return TablaEquity(tabla, *arrays)


class TestExportacionEquity:
    def test_csv(self, tabla_equity_pequena, tmp_path):
        ruta = exportar_equity_csv(tabla_equity_pequena, tmp_path / "e.csv")
        with ruta.open(encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        assert len(filas) == 330 * 4 * 5
        assert {f["lance"] for f in filas} == {l.value for l in Lance}

    def test_json(self, tabla_equity_pequena, tmp_path):
        datos = json.loads(exportar_equity_json(tabla_equity_pequena,
                                                tmp_path / "e.json").read_text("utf-8"))
        assert len(datos["manos"]) == 330
        assert len(datos["equity"]["p_gana_pareja"]["grande"]) == 330
        assert len(datos["equity"]["p_gana_pareja"]["grande"][0]) == 4

    def test_ranking(self, tabla_equity_pequena, tmp_path):
        filas = ranking(tabla_equity_pequena, Lance.GRANDE, 1)
        assert [f.puesto for f in filas] == list(range(1, 331))
        equities = [f.equity.p_gana_individual for f in filas]
        assert equities == sorted(equities, reverse=True)
        assert filas[0].mano == "R R R R"
        assert exportar_rankings_csv(tabla_equity_pequena, tmp_path / "r.csv").exists()

    def test_graficas(self, tabla_equity_pequena, tmp_path):
        assert graficar_posicion(tabla_equity_pequena, tmp_path / "p.png").stat().st_size > 0
        sin, con = equity("R R C 5", 1), equity("R R C 5", 1, companero=sin_pares())
        assert graficar_condicion(sin, con, tmp_path / "c.png").stat().st_size > 0


class TestCLI:
    def test_equity(self, capsys):
        assert main(["equity", "R R C 5", "--posicion", "1", "--companero", "pares>=medias",
                     "--n", "20000", "--semilla", "1"]) == 0
        salida = capsys.readouterr().out
        assert "jugador 3: pares>=medias" in salida
        assert "Monte Carlo" in salida

    def test_equity_condicion_invalida(self, capsys):
        assert main(["equity", "R R C 5", "--companero", "pares>=trio"]) == 1
        assert "Categoría de pares" in capsys.readouterr().err

    def test_ayuda_menciona_las_comillas(self, capsys):
        with pytest.raises(SystemExit):
            main(["equity", "--help"])
        assert "comillas" in capsys.readouterr().out.lower()

    def test_evaluar(self, capsys):
        assert main(["evaluar", "R R C 5"]) == 0
        assert "448 combinaciones" in capsys.readouterr().out

    def test_resolver(self, capsys):
        assert main(["resolver", "R R C 5", "7 7 7 S", "A A 4 5", "C C S S"]) == 0
        salida = capsys.readouterr().out
        assert "pares   gana el jugador 4 -> pareja 2 cobra 5" in salida
        assert "punto   no se juega" in salida

    def test_verificar(self, capsys, tmp_path):
        assert main(["verificar", "--n", "20000", "--semilla", "1",
                     "--csv", str(tmp_path / "v.csv")]) == 0
        assert "métricas dentro del intervalo" in capsys.readouterr().out
        assert (tmp_path / "v.csv").exists()

    def test_variante_y_31_real(self, capsys):
        assert main(["--variante", "4reyes", "distribucion"]) == 0
        assert "715 manos distintas" in capsys.readouterr().out
        assert main(["--31-real", "distribucion"]) == 0
        assert "31 real" in capsys.readouterr().out

    def test_mano_invalida(self, capsys):
        assert main(["evaluar", "R R X 5"]) == 1
        assert "Carta desconocida" in capsys.readouterr().err
