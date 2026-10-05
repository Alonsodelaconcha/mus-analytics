"""Tests de las distribuciones exactas, la exportación y la CLI."""

import csv

import pytest

from mus.__main__ import main
from mus.analisis import (
    distribucion_exacta,
    distribucion_sumas,
    exportar_tabla_csv,
    graficar_distribucion,
)
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


class TestCLI:
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
