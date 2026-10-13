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
    MOTIVO_BOT,
    MOTIVO_BOT_PARTIDA,
    contar_cortes,
    escribir_resumenes,
    leer_manos,
    parsear_rondas,
    por_sesion,
    resumenes_desfasados,
    resumir,
    rondas_siguientes,
    texto_mus_real,
)

RAIZ = Path(__file__).resolve().parents[1]
CABECERA = ",".join(COLUMNAS)


def escribir(ruta: Path, filas: list[str], fecha: str = "", resultado: str = "") -> Path:
    """Escribe un fichero de anotaciones. Las filas van sin las dos columnas de la
    partida (fecha y resultado), que se añaden aquí tras el número de partida."""
    completas = [f"{partida},{fecha},{resultado},{resto}"
                 for partida, resto in (fila.split(",", 1) for fila in filas)]
    ruta.write_text("\n".join([CABECERA, *completas]) + "\n", encoding="utf-8")
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
    assert "Resultado de las partidas: ganamos 0, perdimos 0, sin apuntar 1." in salida
    assert "Sesiones: sin fecha, 1 partida y 6 manos." in salida
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
    assert all(m.fecha is None and m.resultado is None for m in manos)


def test_cuentas_del_usuario_sesion_del_2026_10_12():
    """Las cuentas hechas a mano por el usuario (partidas 16-24, anotadas el 2026-10-13)."""
    todas = leer_manos(RAIZ / "datos" / "manos_reales.csv")
    sesion = [m for m in todas if 16 <= m.partida <= 24]
    assert {m.fecha for m in sesion} == {"2026-10-12"} and len(sesion) == 54
    assert all(m.usa_web is False for m in sesion)
    assert all((m.mi_posicion is None) == (m.numero == 1) for m in sesion)

    # Sin la partida 3 de la sesión (la 18), que se jugó con un bot: 41 manos, mus en 9.
    incluidas = [m for m in sesion if not m.excluida]
    assert (len(incluidas), sum(m.hay_mus for m in incluidas)) == (41, 9)
    assert contar_cortes(sesion) == ((41, 32, 26, 22), (9, 6, 4, 13))
    s = rondas_siguientes(sesion)
    assert (s.otra_ronda, s.conocidas, s.con_mus) == (0, 9, 9)

    # La partida con bot: fuera entera, con su motivo. Habría añadido 4 manos:
    # un mus y un corte de mano, uno de segundo y uno de tercero.
    con_bot = [m for m in sesion if m.partida == 18]
    assert [m.motivo for m in con_bot] == ["primera mano"] + [MOTIVO_BOT_PARTIDA] * 4
    assert sorted(m.rondas[0] for m in con_bot[1:]) == ["mano", "mus", "segundo", "tercero"]
    assert 18 not in {r.partida for r in resumir(todas) if r.manos}

    # Con lo anterior: 112 manos, mus en 33.
    assert contar_cortes(todas) == ((112, 89, 68, 56), (23, 21, 12, 23))
    assert sum(r.manos for r in resumir(todas)) == 112
    assert sum(r.con_mus for r in resumir(todas)) == 33
    total = rondas_siguientes(todas)
    assert (total.otra_ronda, total.conocidas) == (8, 32)

    # Resultado de cada partida de la sesión; en la última no apuntó cómo acabó.
    resultados = {r.partida: r.resultado for r in resumir(sesion)}
    assert [resultados[p] for p in range(16, 25)] == [
        "ganamos", "ganamos", "perdimos", "ganamos", "perdimos", "perdimos", "ganamos", "perdimos",
        None]
    # Corrección del usuario: en la mano 2 de su partida 7 (la 22) era segundo, no tercero.
    (corregida,) = [m for m in sesion if (m.partida, m.numero) == (22, 2)]
    assert corregida.mi_posicion == 2 and "era S" in corregida.anotacion


def test_cortes_sin_las_decisiones_del_usuario():
    """En la sesión con su posición anotada: sus decisiones y las de los demás, que juntas
    son todas (contadas a mano mano a mano el 2026-10-13)."""
    sesion = [m for m in leer_manos(RAIZ / "datos" / "manos_reales.csv") if m.fecha == "2026-10-12"]
    mias, ajenas = contar_cortes(sesion, "yo"), contar_cortes(sesion, "otros")
    assert mias == ((10, 9, 8, 5), (4, 1, 3, 3))
    assert ajenas == ((31, 23, 18, 17), (5, 5, 1, 10))
    todas = contar_cortes(sesion)
    assert tuple(a + b for a, b in zip(mias[0], ajenas[0])) == todas[0]
    assert tuple(a + b for a, b in zip(mias[1], ajenas[1])) == todas[1]


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


# --- Fecha y resultado de cada partida ----------------------------------------------------


def test_fecha_y_resultado(tmp_path):
    manos = leer_manos(escribir(tmp_path / "m.csv", PARTIDA, "2026-10-12", "ganamos"))
    assert {(m.fecha, m.resultado) for m in manos} == {("2026-10-12", "ganamos")}
    (r,) = resumir(manos)
    assert (r.fecha, r.resultado) == ("2026-10-12", "ganamos")
    sin_apuntar = leer_manos(escribir(tmp_path / "m.csv", PARTIDA))
    assert {(m.fecha, m.resultado) for m in sin_apuntar} == {(None, None)}
    for fecha, resultado, error in (("12/10/2026", "", "fecha"), ("2026-13-40", "", "fecha"),
                                    ("", "empate", "resultado")):
        with pytest.raises(ValueError, match=error):
            leer_manos(escribir(tmp_path / "m.csv", PARTIDA[:2], fecha, resultado))


def test_la_fecha_y_el_resultado_son_de_la_partida(tmp_path):
    ruta = tmp_path / "m.csv"
    ruta.write_text("\n".join([CABECERA, "1,2026-10-12,ganamos,1,mano,sí,primera mano,,,",
                               "1,2026-10-12,perdimos,2,mano,no,,,,"]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="misma fecha"):
        leer_manos(ruta)


def test_por_sesion(tmp_path):
    otra = [f"2,{i}," + fila.split(",", 2)[2] for i, fila in enumerate(PARTIDA[:3], start=1)]
    ruta = tmp_path / "m.csv"
    escribir(ruta, PARTIDA)
    con_fecha = escribir(tmp_path / "f.csv", otra, "2026-10-12", "perdimos").read_text(
        encoding="utf-8").splitlines()[1:]
    ruta.write_text(ruta.read_text(encoding="utf-8") + "\n".join(con_fecha) + "\n", encoding="utf-8")
    sesiones = por_sesion(leer_manos(ruta))
    assert [(fecha, len(manos)) for fecha, manos in sesiones] == [(None, 8), ("2026-10-12", 3)]


# --- Manos jugadas con un bot ---------------------------------------------------------------


def test_bot_desde_una_mano(tmp_path):
    """«Bot desde la mano 6»: se excluyen esa y las siguientes."""
    filas = PARTIDA[:5] + [f"1,{n},{rondas},sí,{MOTIVO_BOT},,," for n, rondas in
                           ((6, "postre"), (7, "mano"), (8, "mus segundo"))]
    (r,) = resumir(leer_manos(escribir(tmp_path / "m.csv", filas)))
    assert (r.manos, r.con_mus) == (3, 2)             # segundo, mus, mus
    assert dict(r.excluidas) == {"primera mano": 1, "no recordada": 1, MOTIVO_BOT: 3}


def test_bot_sin_saber_desde_cuando_excluye_la_partida(tmp_path):
    con_bot = [PARTIDA[0]] + [f"1,{n},{rondas},sí,{MOTIVO_BOT_PARTIDA},,," for n, rondas in
                              ((2, "mus tercero"), (3, "mano"))]
    otra = [f"2,{i}," + fila.split(",", 2)[2] for i, fila in enumerate(PARTIDA[:3], start=1)]
    resumenes = resumir(leer_manos(escribir(tmp_path / "m.csv", con_bot + otra)))
    assert [(r.partida, r.manos) for r in resumenes] == [(1, 0), (2, 2)]
    # La partida sigue en el fichero, pero no entra en los resúmenes de la calibración.
    assert texto_mus_real(resumenes).splitlines()[1:] == ["2,2,1,primera mano: 1"]


@pytest.mark.parametrize("filas, error", [
    # tras una mano con bot, una sin él
    ([f"1,2,mano,sí,{MOTIVO_BOT},,,", "1,3,mano,no,,,,"], "siguientes"),
    ([f"1,2,mano,sí,{MOTIVO_BOT},,,", "1,3,?,sí,no recordada,,,"], "siguientes"),
    # no se sabe desde cuándo, pero no se excluye la partida entera
    (["1,2,mano,no,,,,", f"1,3,mano,sí,{MOTIVO_BOT_PARTIDA},,,"], "se excluyen todas"),
])
def test_regla_de_los_bots(tmp_path, filas, error):
    with pytest.raises(ValueError, match=error):
        leer_manos(escribir(tmp_path / "m.csv", [PARTIDA[0], *filas]))


# --- De quién es cada decisión ---------------------------------------------------------------


def test_contar_cortes_segun_quien(tmp_path):
    """Yo de segundo: hablo si la mano da mus. Lo que no decido yo, lo deciden los demás."""
    filas = [
        "1,1,mano,sí,primera mano,,,",
        "1,2,mano,no,,segundo,no,",            # corta la mano: yo no llego a hablar
        "1,3,segundo,no,,segundo,no,",         # corto yo
        "1,4,postre,no,,segundo,no,",          # doy mus; corta el postre
        "1,5,mus tercero,no,,mano,no,",        # doy mus de mano; mus los cuatro
        "1,6,tercero,no,,,,",                  # sin mi posición: no entra en yo ni en otros
    ]
    manos = leer_manos(escribir(tmp_path / "m.csv", filas))
    assert contar_cortes(manos) == ((5, 4, 3, 2), (1, 1, 1, 1))
    assert contar_cortes(manos, "yo") == ((1, 2, 0, 0), (0, 1, 0, 0))
    assert contar_cortes(manos, "otros") == ((3, 1, 2, 2), (1, 0, 0, 1))
    with pytest.raises(ValueError, match="quien"):
        contar_cortes(manos, "rivales")
