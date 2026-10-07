"""Tests de la calibración de λ con partidas reales."""

import pytest

from mus.__main__ import main
from mus.calibracion import Observacion, calibrar, lambda_para, leer_observaciones

# Curva sintética, decreciente como la del modelo.
CURVA = [(0.0, 1.0), (0.5, 0.4), (1.0, 0.1)]


def test_lambda_para_interpola():
    assert lambda_para(0.4, CURVA) == (0.5, True)
    assert lambda_para(0.7, CURVA)[0] == pytest.approx(0.25)
    assert lambda_para(0.25, CURVA)[0] == pytest.approx(0.75)


def test_lambda_para_recorta_fuera_de_rango():
    assert lambda_para(0.05, CURVA) == (1.0, False)
    assert lambda_para(1.0, CURVA) == (0.0, True)


def test_observacion_valida():
    with pytest.raises(ValueError):
        Observacion(0, 0)
    with pytest.raises(ValueError):
        Observacion(5, 6)


def test_calibrar():
    c = calibrar(Observacion(50, 20), CURVA)
    assert c.p_observada.p == pytest.approx(0.4)
    assert c.lambda_estimada == pytest.approx(0.5)
    desde, hasta = c.lambda_intervalo
    assert desde < 0.5 < hasta          # más mus observado -> λ menor
    assert c.suficiente and c.dentro_del_rango and not c.intervalo_recortado
    pocas = calibrar(Observacion(7, 2), CURVA)
    assert not pocas.suficiente and pocas.intervalo_recortado  # el 8 % queda fuera


def test_leer_observaciones(tmp_path):
    ruta = tmp_path / "mus.csv"
    ruta.write_text("sesion,fecha,manos,con_mus,notas\n1,,7,2,a\n2,2026-10-10,13,5,b\n",
                    encoding="utf-8")
    assert leer_observaciones(ruta) == Observacion(20, 7)
    with pytest.raises(ValueError):
        leer_observaciones(tmp_path / "no_existe.csv")


def test_datos_del_repositorio():
    obs = leer_observaciones()
    assert obs.manos >= 7 and 0 <= obs.con_mus <= obs.manos


def test_cli(monkeypatch, capsys):
    import mus.__main__ as cli
    monkeypatch.setattr(cli, "curva_hay_mus", lambda reglas: CURVA)
    assert main(["calibrar", "--manos", "7", "--con-mus", "2"]) == 0
    salida = capsys.readouterr().out
    assert "No se cambia nada" in salida and "recortado" in salida
    assert main(["calibrar", "--manos", "50", "--con-mus", "20"]) == 0
    assert "--factor-corte 0.50" in capsys.readouterr().out
