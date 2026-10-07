"""Tests de la calibración de λ con partidas reales."""

import pytest

from mus.__main__ import main
from mus.calibracion import (
    CortesPorPosicion,
    Observacion,
    calibrar,
    cola_chi2,
    comparar_cortes,
    lambda_para,
    leer_cortes,
    leer_observaciones,
    p_binomial_bilateral,
)

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


# --- Corte por posición -------------------------------------------------------------------


REALES = CortesPorPosicion((45, 37, 26, 21), (8, 11, 5, 8))


def test_cortes_coherencia():
    assert REALES.coherente and REALES.con_mus == 13
    assert not CortesPorPosicion((45, 40, 26, 21), (8, 11, 5, 8)).coherente
    with pytest.raises(ValueError):
        CortesPorPosicion((10, 5, 5, 5), (11, 0, 0, 0))
    with pytest.raises(ValueError):
        CortesPorPosicion((10, 5, 5), (1, 0, 0))


def test_leer_cortes_suma_por_posicion(tmp_path):
    ruta = tmp_path / "c.csv"
    ruta.write_text("fecha,posicion,habla,corta,notas\n,1,10,2,a\n,2,8,3,a\n,3,5,1,a\n,4,4,1,a\n"
                    ",1,5,1,b\n,2,4,0,b\n,3,4,1,b\n,4,3,0,b\n", encoding="utf-8")
    assert leer_cortes(ruta) == CortesPorPosicion((15, 12, 9, 7), (3, 3, 2, 1))
    with pytest.raises(ValueError):
        leer_cortes(tmp_path / "no_existe.csv")


def test_p_binomial_bilateral():
    assert p_binomial_bilateral(5, 10, 0.5) == pytest.approx(1.0)
    assert p_binomial_bilateral(0, 10, 0.5) == pytest.approx(2 / 1024)
    assert p_binomial_bilateral(10, 10, 0.5) == pytest.approx(2 / 1024)
    # asimétrica: P(X >= 4 | n=4, p=0,2) = 0,0016 y P(X = 0) = 0,4096 > 0,0016
    assert p_binomial_bilateral(4, 4, 0.2) == pytest.approx(0.2 ** 4)


def test_cola_chi2():
    assert cola_chi2(0, 4) == pytest.approx(1)
    assert cola_chi2(9.4877, 4) == pytest.approx(0.05, abs=1e-4)   # cuantil 95 % con 4 g.l.
    assert cola_chi2(5.9915, 2) == pytest.approx(0.05, abs=1e-4)
    assert cola_chi2(7.8147, 3) == pytest.approx(0.05, abs=2e-3)   # aproximación con g.l. impares


def test_comparar_cortes():
    c = comparar_cortes(REALES, (0.212, 0.328, 0.183, 0.305))
    e, modelo, p_valor = c.posicion(4)
    assert (e.exitos, e.n, modelo) == (8, 21, 0.305) and 0.3 < p_valor < 0.7
    x, grados, p = c.chi2()
    assert grados == 4 and x == pytest.approx(1.07, abs=0.01) and p > 0.8
    (mano, _), (postre, _) = c.pareja((1, 3)), c.pareja((2, 4))
    assert (mano.exitos, mano.n, postre.exitos, postre.n) == (13, 71, 19, 58)
    razon, (bajo, alto), razon_modelo = c.razon_parejas()
    assert razon == pytest.approx((19 / 58) / (13 / 71)) and bajo < razon_modelo < alto
    with pytest.raises(ValueError):
        comparar_cortes(REALES, (0.2, 0.3, 0.2))


def test_cortes_del_repositorio():
    """Los dos ficheros de datos reales deben cuadrar entre sí."""
    cortes, obs = leer_cortes(), leer_observaciones()
    assert cortes.coherente
    assert (cortes.habla[0], cortes.con_mus) == (obs.manos, obs.con_mus)


def test_cli_con_cortes(monkeypatch, capsys, tmp_path):
    import mus.__main__ as cli
    monkeypatch.setattr(cli, "curva_hay_mus", lambda reglas: CURVA)
    monkeypatch.setattr(cli, "cortes_del_modelo", lambda reglas, lam: (0.21, 0.33, 0.18, 0.3))
    datos, cortes = tmp_path / "mus.csv", tmp_path / "cortes.csv"
    datos.write_text("sesion,fecha,manos,con_mus,notas\n1,,45,13,a\n", encoding="utf-8")
    cortes.write_text("fecha,posicion,habla,corta,notas\n,1,45,8,\n,2,37,11,\n,3,26,5,\n,4,21,8,\n",
                      encoding="utf-8")
    assert main(["calibrar", "--datos", str(datos), "--cortes", str(cortes)]) == 0
    salida = capsys.readouterr().out
    assert "los datos encajan con el modelo" in salida and "1.79 veces más" in salida
    assert "La mesa «Normal» de la web usa λ = 0.67" in salida and "AVISO" not in salida
