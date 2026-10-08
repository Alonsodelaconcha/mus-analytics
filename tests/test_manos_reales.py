"""Tests de las anotaciones de partidas reales y de los resúmenes que salen de ellas."""

from pathlib import Path

import pytest

from mus.__main__ import main
from mus.calibracion import (
    CortesPorPosicion,
    Observacion,
    leer_cortes,
    leer_observaciones,
    leer_partidas,
    variacion_entre_partidas,
)
from mus.manos_reales import (
    COLUMNAS,
    escribir_resumenes,
    leer_manos,
    parsear_rondas,
    resumenes_desfasados,
    resumir,
    rondas_siguientes,
)

RAIZ = Path(__file__).resolve().parents[1]
CABECERA = ",".join(COLUMNAS)


def escribir(ruta: Path, filas: list[str]) -> Path:
    ruta.write_text("\n".join([CABECERA, *filas]) + "\n", encoding="utf-8")
    return ruta


# Una partida pequeña con todos los casos: corte de cada posición, mus con
# continuación conocida y desconocida, y las dos exclusiones.
PARTIDA = [
    "1,1,mano,sí,primera mano,,,corte (mano)",
    "1,2,segundo,no,,mano,sí,corta segundo",
    "1,3,mus mus tercero,no,,,,\"mus, otro mus, corta tercero\"",
    "1,4,?,sí,no recordada,,,no me acuerdo",
    "1,5,mus ?,no,,postre,no,mus",
    "1,6,postre,no,,,,corta postre",
    "1,7,mano,no,,,,corta mano",
    "1,8,mus segundo,no,,,,\"mus, luego corta segundo\"",
]


def test_parsear_rondas():
    assert parsear_rondas("mus mus mano") == ("mus", "mus", "mano")
    assert parsear_rondas("  Postre ") == ("postre",)
    assert parsear_rondas("mus ?") == ("mus", "?")
    for malo in ("", "mus", "mano mus", "mano postre", "mus corte", "? mano"):
        with pytest.raises(ValueError):
            parsear_rondas(malo)


def test_leer_manos(tmp_path):
    manos = leer_manos(escribir(tmp_path / "m.csv", PARTIDA))
    assert len(manos) == 8
    m = manos[2]
    assert (m.hay_mus, m.corta, m.rondas_de_mus) == (True, None, 2)
    assert (manos[1].corta, manos[1].mi_posicion, manos[1].usa_web) == (2, 1, True)
    assert manos[4].rondas_de_mus is None and manos[4].usa_web is False
    assert manos[0].excluida and manos[0].motivo == "primera mano"
    assert manos[2].anotacion == "mus, otro mus, corta tercero"


@pytest.mark.parametrize("fila, error", [
    ("1,1,mano,no,,,,", "primera mano"),                    # la primera mano no se excluye
    ("1,1,mano,sí,otra cosa,,,", "primera mano"),
    ("1,2,mano,sí,,,,", "motivo"),                          # excluida sin motivo
    ("1,2,mano,no,porque sí,,,", "motivo"),                 # incluida con motivo
    ("1,2,?,no,,,,", "excluirse"),                          # primera ronda desconocida
    ("1,2,mano,quizá,,,,", "sí o no"),
    ("1,2,mano,no,,cuarto,,", "mi_posicion"),
    ("1,2,mano,no,,,a veces,", "usa_web"),
    ("1,2,mus,no,,,,", "corte"),
    ("0,1,mano,sí,primera mano,,,", "empiezan en 1"),
])
def test_filas_no_validas(tmp_path, fila, error):
    filas = [PARTIDA[0], fila] if not fila.startswith(("1,1,", "0,")) else [fila]
    with pytest.raises(ValueError, match=error) as e:
        leer_manos(escribir(tmp_path / "m.csv", filas))
    assert "línea" in str(e.value)


def test_numeracion_y_columnas(tmp_path):
    with pytest.raises(ValueError, match="sin huecos"):
        leer_manos(escribir(tmp_path / "m.csv", [PARTIDA[0], PARTIDA[2]]))
    with pytest.raises(ValueError, match="sin huecos"):
        leer_manos(escribir(tmp_path / "m.csv", [PARTIDA[0], PARTIDA[1], PARTIDA[1]]))
    (tmp_path / "c.csv").write_text("partida,numero,rondas\n1,1,mano\n", encoding="utf-8")
    with pytest.raises(ValueError, match="columnas"):
        leer_manos(tmp_path / "c.csv")
    with pytest.raises(ValueError, match="No existe"):
        leer_manos(tmp_path / "no_existe.csv")


def test_resumir_solo_primera_ronda(tmp_path):
    (r,) = resumir(leer_manos(escribir(tmp_path / "m.csv", PARTIDA)))
    # Incluidas: segundo, mus, mus, postre, mano, mus -> 6 manos, 3 con mus.
    assert (r.manos, r.con_mus) == (6, 3)
    assert r.corta == (1, 1, 0, 1)
    assert r.habla == (6, 5, 4, 4)                 # cada posición: la anterior − sus cortes
    assert CortesPorPosicion(r.habla, r.corta).coherente
    assert dict(r.excluidas) == {"primera mano": 1, "no recordada": 1}


def test_rondas_siguientes(tmp_path):
    s = rondas_siguientes(leer_manos(escribir(tmp_path / "m.csv", PARTIDA)))
    assert (s.con_mus, s.conocidas, s.otra_ronda) == (3, 2, 1)
    assert s.por_rondas == ((1, 1), (2, 1))


def test_escribir_y_leer_resumenes(tmp_path):
    otra = [f"2,{i}," + fila.split(",", 2)[2] for i, fila in
            enumerate(PARTIDA[:3], start=1)]
    anotaciones = escribir(tmp_path / "m.csv", PARTIDA + otra)
    mus, cortes = tmp_path / "mus.csv", tmp_path / "cortes.csv"
    assert resumenes_desfasados(anotaciones, mus, cortes) == [mus, cortes]
    escribir_resumenes(anotaciones, mus, cortes)
    assert resumenes_desfasados(anotaciones, mus, cortes) == []
    assert leer_partidas(mus) == [Observacion(6, 3), Observacion(2, 1)]
    assert leer_observaciones(mus) == Observacion(8, 4)
    c = leer_cortes(cortes)
    assert c.coherente and c.con_mus == 4 and c.habla[0] == 8
    # Con final de línea de Windows (git en Windows puede convertirlo) sigue al día.
    mus.write_bytes(mus.read_bytes().replace(b"\n", b"\r\n"))
    assert resumenes_desfasados(anotaciones, mus, cortes) == []
    mus.write_text(mus.read_text(encoding="utf-8").replace("6,3", "6,4"), encoding="utf-8")
    assert resumenes_desfasados(anotaciones, mus, cortes) == [mus]


def test_cli(tmp_path, capsys):
    anotaciones = escribir(tmp_path / "m.csv", PARTIDA)
    mus, cortes = tmp_path / "mus.csv", tmp_path / "cortes.csv"
    assert main(["manos-reales", "--anotaciones", str(anotaciones), "--datos", str(mus),
                 "--cortes", str(cortes)]) == 0
    salida = capsys.readouterr().out
    assert "mus en 3 de 6 manos" in salida
    assert "mano 1 de 6, segundo 1 de 5, tercero 0 de 4, postre 1 de 4" in salida
    assert "otra ronda de mus en 1 de 2" in salida
    assert "Manos con tu posición anotada: 2 de 6; usando la web: 1" in salida
    assert mus.exists() and cortes.exists()


def test_calibrar_avisa_si_los_resumenes_estan_desfasados(tmp_path, monkeypatch, capsys):
    import mus.__main__ as cli
    monkeypatch.setattr(cli, "curva_hay_mus", lambda reglas: [(0.0, 1.0), (1.0, 0.1)])
    monkeypatch.setattr(cli, "cortes_del_modelo", lambda reglas, lam: (0.2, 0.3, 0.2, 0.3))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "datos").mkdir()
    escribir(tmp_path / "datos" / "manos_reales.csv", PARTIDA)
    escribir_resumenes("datos/manos_reales.csv", "datos/mus_real.csv",
                       "datos/cortes_por_posicion.csv")
    assert main(["calibrar"]) == 0
    assert "AVISO" not in capsys.readouterr().out
    escribir(tmp_path / "datos" / "manos_reales.csv", PARTIDA[:3])
    assert main(["calibrar"]) == 0
    assert "Regenéralos con: python -m mus manos-reales" in capsys.readouterr().out


# --- Los datos del repositorio ------------------------------------------------------------


def test_resumenes_versionados_al_dia():
    """Si se cambian las anotaciones, hay que regenerar: python -m mus manos-reales."""
    datos = RAIZ / "datos"
    assert resumenes_desfasados(datos / "manos_reales.csv", datos / "mus_real.csv",
                                datos / "cortes_por_posicion.csv") == []


def test_cuentas_del_usuario_partidas_1_a_15():
    """Las cuentas hechas a mano por el usuario el 2026-10-08 (partidas 1-15)."""
    manos = [m for m in leer_manos(RAIZ / "datos" / "manos_reales.csv") if m.partida <= 15]
    resumenes = resumir(manos)
    assert len(resumenes) == 15

    def total(desde: int, hasta: int) -> tuple[int, int]:
        rs = [r for r in resumenes if desde <= r.partida <= hasta]
        return sum(r.manos for r in rs), sum(r.con_mus for r in rs)

    assert total(1, 15) == (71, 24)
    assert total(1, 9) == (44, 13)        # antes se contaban 45: la primera de la partida 1
    assert tuple(sum(r.corta[p] for r in resumenes) for p in range(4)) == (14, 15, 8, 10)
    assert tuple(sum(r.habla[p] for r in resumenes) for p in range(4)) == (71, 57, 42, 34)
    s = rondas_siguientes(manos)
    assert (s.otra_ronda, s.conocidas) == (8, 23)
    assert all(m.mi_posicion is None and m.usa_web is None for m in manos)


# --- Manos de una misma partida -----------------------------------------------------------


def test_variacion_entre_partidas():
    iguales = [Observacion(10, 3)] * 6
    v = variacion_entre_partidas(iguales, permutaciones=20_000)
    assert v.chi2 == pytest.approx(0) and v.grados == 5 and v.p_valor.p == 1
    assert v.factor_error == pytest.approx(0)
    extremas = [Observacion(8, 8), Observacion(8, 0), Observacion(8, 8), Observacion(8, 0)]
    v = variacion_entre_partidas(extremas, permutaciones=20_000)
    assert v.p_valor.p < 0.001 and v.factor_error > 2
    # Reproducible con la semilla
    tipicas = [Observacion(6, 2), Observacion(7, 5), Observacion(3, 0), Observacion(8, 1)]
    assert variacion_entre_partidas(tipicas, 20_000) == variacion_entre_partidas(tipicas, 20_000)
    with pytest.raises(ValueError):
        variacion_entre_partidas([Observacion(10, 3)])
    with pytest.raises(ValueError):
        variacion_entre_partidas([Observacion(10, 0), Observacion(5, 0)])


def test_variacion_permutaciones_frente_a_chi2():
    """Con partidas grandes, el p-valor por permutaciones se acerca al de la χ²."""
    from mus.calibracion import cola_chi2
    partidas = [Observacion(200, k) for k in (60, 75, 52, 70, 81, 58)]
    v = variacion_entre_partidas(partidas, permutaciones=50_000)
    assert abs(v.p_valor.p - cola_chi2(v.chi2, v.grados)) < 0.02
