"""Anotaciones de partidas reales, mano a mano (``datos/manos_reales.csv``).

Es la fuente de los datos reales. El usuario apunta cada mano de sus partidas,
que son online, en la aplicación Mus Maestro: los otros tres jugadores son los
que le tocan allí en cada partida, no un grupo fijo. Las señas son emojis que
ven los cuatro durante un segundo, y cuando un jugador se va lo sustituye un
bot. De cada mano se apunta:

- ``partida`` y ``numero`` (de mano dentro de la partida, desde 1);
- ``fecha`` (``2026-10-12``) y ``resultado`` (``ganamos`` o ``perdimos``) de la
  partida, repetidos en todas sus manos; vacíos si no se apuntaron;
- ``rondas``: la secuencia de rondas de mus separadas por espacios. Cada ronda
  es ``mus`` (todos dieron mus) o la posición que cortó (``mano``, ``segundo``,
  ``tercero``, ``postre``); ``?`` marca lo que no se recuerda. Por ejemplo,
  ``mus mus mano`` = dos rondas de mus y en la tercera cortó la mano;
- ``excluida`` (``sí``/``no``) y ``motivo``;
- ``mi_posicion`` y ``usa_web``: la posición del usuario (que juega todas las
  partidas) y si ha usado la web en esa mano. Vacías si no se anotaron;
- ``anotacion``: lo que escribió el usuario, tal cual. En la última mano de la
  partida, tras `` | ``, la línea con que la cerró ("GANAMOS", "No apunté más"...).

De aquí salen, con :func:`escribir_resumenes`, los dos ficheros que usa la
calibración (``datos/mus_real.csv`` y ``datos/cortes_por_posicion.csv``), con
código y no a mano. Así no se pierde la información de las rondas siguientes,
que la calibración no usa pero la Fase 6 necesitará.

Criterios (del usuario):

- Se excluye la primera mano de cada partida. Se juega con mus corrido y sin
  señas, y quien corta pasa a ser mano: así se decide la mano de la partida
  (es la regla tradicional, la del reglamento de Fournier). En esas manos, la
  posición de ``rondas`` es la que anotó el usuario.
- Se excluyen las manos que no se recuerdan.
- Se excluyen las manos jugadas con un bot: lo que se mide es cómo juegan las
  personas. El usuario apunta «bot desde la mano X» y se excluyen las manos
  desde esa, con motivo ``bot``; si no se sabe desde cuándo, se excluye la
  partida entera, con motivo ``bot (no se sabe desde qué mano)``, y se queda en
  el fichero. Un bot no se va: excluida una mano por bot, lo están las siguientes.
- Para las estadísticas solo cuenta la primera ronda.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

RUTA_MANOS = Path("datos/manos_reales.csv")
COLUMNAS = ("partida", "fecha", "resultado", "numero", "rondas", "excluida", "motivo",
            "mi_posicion", "usa_web", "anotacion")
POSICION = {"mano": 1, "segundo": 2, "tercero": 3, "postre": 4}
MUS = "mus"
DESCONOCIDO = "?"
MOTIVO_PRIMERA = "primera mano"
MOTIVO_BOT = "bot"
"""Mano jugada con un bot («bot desde la mano X»)."""
MOTIVO_BOT_PARTIDA = "bot (no se sabe desde qué mano)"
"""Partida con un bot sin saber desde cuándo: se excluye entera."""
RESULTADOS = ("ganamos", "perdimos")
QUIEN = ("todos", "yo", "otros")
"""De quién son las decisiones que se cuentan en :func:`contar_cortes`."""
_SI_NO = {"sí": True, "si": True, "no": False}


def es_por_bot(motivo: str) -> bool:
    """La mano se excluye porque se jugó con un bot."""
    return motivo in (MOTIVO_BOT, MOTIVO_BOT_PARTIDA)


@dataclass(frozen=True)
class ManoReal:
    """Una mano anotada.

    Atributos:
        rondas: ``"mus"`` por cada ronda de mus y, al final, la posición (1-4)
            que cortó como texto (``"mano"``...) o ``"?"`` si no se sabe.
        mi_posicion: 1-4, o None si no se anotó.
        usa_web: None si no se anotó.
        fecha: de la partida, como ``2026-10-12``; None si no se apuntó.
        resultado: ``"ganamos"`` o ``"perdimos"``; None si no se apuntó.
    """

    partida: int
    numero: int
    rondas: tuple[str, ...]
    excluida: bool
    motivo: str
    mi_posicion: int | None
    usa_web: bool | None
    anotacion: str
    fecha: str | None = None
    resultado: str | None = None

    @property
    def hay_mus(self) -> bool:
        """Hubo mus en la primera ronda."""
        return self.rondas[0] == MUS

    @property
    def corta(self) -> int | None:
        """Posición que cortó en la primera ronda (None si hubo mus)."""
        return POSICION.get(self.rondas[0])

    @property
    def rondas_de_mus(self) -> int | None:
        """Rondas de mus antes del corte, o None si no se sabe cuántas."""
        return None if self.rondas[-1] == DESCONOCIDO else len(self.rondas) - 1


def parsear_rondas(texto: str) -> tuple[str, ...]:
    """``"mus mus mano"`` -> ("mus", "mus", "mano").

    Las rondas de mus van seguidas de un corte o de ``?``: después de un corte no
    hay más rondas, y una mano no acaba en mus.
    """
    rondas = tuple(texto.lower().split())
    validas = {MUS, DESCONOCIDO, *POSICION}
    if not rondas:
        raise ValueError("faltan las rondas")
    if any(r not in validas for r in rondas):
        raise ValueError(f"ronda no válida en «{texto}»: cada ronda es 'mus', una posición "
                         "(mano, segundo, tercero, postre) o '?'")
    if any(r != MUS for r in rondas[:-1]) or rondas[-1] == MUS:
        raise ValueError(f"«{texto}»: antes del final solo puede haber 'mus', y la mano acaba "
                         "con un corte o con '?'")
    return rondas


def _mano_de_fila(fila: dict[str, str]) -> ManoReal:
    partida, numero = int(fila["partida"]), int(fila["numero"])
    if partida < 1 or numero < 1:
        raise ValueError("la partida y el número de mano empiezan en 1")
    rondas = parsear_rondas(fila["rondas"])
    excluida_texto = fila["excluida"].strip().lower()
    if excluida_texto not in _SI_NO:
        raise ValueError(f"'excluida' debe ser sí o no, no «{fila['excluida']}»")
    excluida, motivo = _SI_NO[excluida_texto], fila["motivo"].strip()
    if excluida != bool(motivo):
        raise ValueError("una mano excluida necesita motivo, y una incluida no lo lleva")
    if numero == 1 and motivo != MOTIVO_PRIMERA:
        raise ValueError(f"la primera mano de cada partida se excluye con motivo «{MOTIVO_PRIMERA}»")
    if rondas[0] == DESCONOCIDO and not excluida:
        raise ValueError("una mano sin la primera ronda conocida debe excluirse")
    posicion, web = fila["mi_posicion"].strip().lower(), fila["usa_web"].strip().lower()
    if posicion and posicion not in POSICION:
        raise ValueError(f"mi_posicion no válida: «{fila['mi_posicion']}»")
    if web and web not in _SI_NO:
        raise ValueError(f"usa_web debe ser sí, no o vacío, no «{fila['usa_web']}»")
    fecha, resultado = fila["fecha"].strip(), fila["resultado"].strip().lower()
    if fecha:
        try:
            date.fromisoformat(fecha)
        except ValueError:
            raise ValueError(f"la fecha debe ser como 2026-10-12, no «{fecha}»") from None
    if resultado and resultado not in RESULTADOS:
        raise ValueError(f"resultado debe ser {' o '.join(RESULTADOS)}, o vacío, no "
                         f"«{fila['resultado']}»")
    return ManoReal(partida, numero, rondas, excluida, motivo,
                    POSICION[posicion] if posicion else None,
                    _SI_NO[web] if web else None, fila["anotacion"],
                    fecha or None, resultado or None)


def leer_manos(ruta: str | Path = RUTA_MANOS) -> list[ManoReal]:
    """Lee y valida el fichero. Los errores indican la línea.

    Además de cada fila, comprueba en cada partida que las manos van numeradas
    1, 2, 3... sin huecos ni repeticiones, que todas llevan la misma fecha y el
    mismo resultado, y la regla de los bots: excluida una mano por bot, lo están
    las siguientes; y si no se sabe desde qué mano, todas desde la segunda.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise ValueError(f"No existe {ruta}: créalo con columnas {','.join(COLUMNAS)}")
    manos = []
    with ruta.open(encoding="utf-8", newline="") as f:
        lector = csv.DictReader(f)
        if tuple(lector.fieldnames or ()) != COLUMNAS:
            raise ValueError(f"{ruta}: las columnas deben ser {','.join(COLUMNAS)}")
        for fila in lector:
            try:
                manos.append(_mano_de_fila(fila))
            except (ValueError, TypeError) as e:
                raise ValueError(f"{ruta}, línea {lector.line_num}: {e}") from None
    for partida in sorted({m.partida for m in manos}):
        numeros = [m.numero for m in manos if m.partida == partida]
        if sorted(numeros) != list(range(1, len(numeros) + 1)):
            raise ValueError(f"{ruta}: las manos de la partida {partida} deben ir numeradas "
                             f"de 1 a {len(numeros)} sin huecos")
        de_partida = sorted((m for m in manos if m.partida == partida), key=lambda m: m.numero)
        if len({(m.fecha, m.resultado) for m in de_partida}) > 1:
            raise ValueError(f"{ruta}: todas las manos de la partida {partida} deben llevar la "
                             "misma fecha y el mismo resultado")
        con_bot = [es_por_bot(m.motivo) for m in de_partida]
        if any(con_bot) and not all(con_bot[con_bot.index(True):]):
            raise ValueError(f"{ruta}: en la partida {partida}, tras una mano excluida por bot "
                             "deben estarlo todas las siguientes")
        if (any(m.motivo == MOTIVO_BOT_PARTIDA for m in de_partida)
                and any(m.motivo != MOTIVO_BOT_PARTIDA for m in de_partida[1:])):
            raise ValueError(f"{ruta}: si en la partida {partida} no se sabe desde qué mano hay "
                             f"un bot, se excluyen todas con motivo «{MOTIVO_BOT_PARTIDA}»")
    return manos


# --- Resúmenes para la calibración (solo la primera ronda) ----------------------------


@dataclass(frozen=True)
class ResumenPartida:
    """Primera ronda de las manos incluidas de una partida.

    Atributos:
        habla, corta: veces que le tocó hablar a cada posición (1-4) y veces que cortó.
        excluidas: manos excluidas por motivo.
        fecha, resultado: los de la partida (None si no se apuntaron).
    """

    partida: int
    manos: int
    con_mus: int
    habla: tuple[int, ...]
    corta: tuple[int, ...]
    excluidas: tuple[tuple[str, int], ...]
    fecha: str | None = None
    resultado: str | None = None


def contar_cortes(manos: Iterable[ManoReal], quien: str = "todos"
                  ) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """(habla, corta): veces que le tocó hablar a cada posición (1-4) en la primera
    ronda de las manos incluidas, y veces que cortó.

    En la primera ronda habla la mano y, si da mus, la siguiente posición, hasta
    que alguien corta o dan mus los cuatro. ``quien`` elige de quién son las
    decisiones que se cuentan: ``"todos"``; ``"yo"``, las del usuario (cuando la
    posición que habla es la suya); u ``"otros"``, las de los demás. Con ``"yo"``
    y ``"otros"`` solo entran las manos con ``mi_posicion`` anotada.
    """
    if quien not in QUIEN:
        raise ValueError(f"quien debe ser uno de {', '.join(QUIEN)}")
    habla, corta = [0] * 4, [0] * 4
    for m in manos:
        if m.excluida or (quien != "todos" and m.mi_posicion is None):
            continue
        ultima = m.corta or 4              # con mus hablan las cuatro posiciones
        for p in range(1, ultima + 1):
            if quien == "todos" or (quien == "yo") == (m.mi_posicion == p):
                habla[p - 1] += 1
                corta[p - 1] += m.corta == p
    return tuple(habla), tuple(corta)


def resumir(manos: Sequence[ManoReal]) -> list[ResumenPartida]:
    """Un resumen por partida, en orden, con la primera ronda de sus manos incluidas."""
    resumenes = []
    for partida in sorted({m.partida for m in manos}):
        de_partida = [m for m in manos if m.partida == partida]
        incluidas = [m for m in de_partida if not m.excluida]
        habla, corta = contar_cortes(incluidas)
        excluidas = Counter(m.motivo for m in de_partida if m.excluida)
        resumenes.append(ResumenPartida(partida, len(incluidas), sum(m.hay_mus for m in incluidas),
                                        habla, corta, tuple(sorted(excluidas.items())),
                                        de_partida[0].fecha, de_partida[0].resultado))
    return resumenes


def por_sesion(manos: Sequence[ManoReal]) -> list[tuple[str | None, list[ManoReal]]]:
    """Las manos agrupadas por la fecha de su partida, en orden; primero las que no
    la tienen apuntada (``None``)."""
    fechas = sorted({m.fecha for m in manos}, key=lambda f: (f is not None, f or ""))
    return [(f, [m for m in manos if m.fecha == f]) for f in fechas]


def texto_mus_real(resumenes: Sequence[ResumenPartida]) -> str:
    """Contenido de ``datos/mus_real.csv``: manos y manos con mus por partida."""
    lineas = ["partida,manos,con_mus,excluidas"]
    for r in resumenes:
        if r.manos:
            excluidas = "; ".join(f"{motivo}: {n}" for motivo, n in r.excluidas)
            lineas.append(f"{r.partida},{r.manos},{r.con_mus},{excluidas}")
    return "\n".join(lineas) + "\n"


def texto_cortes(resumenes: Sequence[ResumenPartida]) -> str:
    """Contenido de ``datos/cortes_por_posicion.csv``: una fila por partida y posición."""
    lineas = ["partida,posicion,habla,corta"]
    for r in resumenes:
        if r.manos:
            lineas += [f"{r.partida},{p + 1},{r.habla[p]},{r.corta[p]}" for p in range(4)]
    return "\n".join(lineas) + "\n"


def resumenes_esperados(ruta_manos: str | Path, ruta_mus: str | Path,
                        ruta_cortes: str | Path) -> dict[Path, str]:
    """Contenido que deben tener los dos resúmenes según las anotaciones."""
    resumenes = resumir(leer_manos(ruta_manos))
    return {Path(ruta_mus): texto_mus_real(resumenes), Path(ruta_cortes): texto_cortes(resumenes)}


def resumenes_desfasados(ruta_manos: str | Path, ruta_mus: str | Path,
                         ruta_cortes: str | Path) -> list[Path]:
    """Resúmenes que no coinciden con lo que sale de las anotaciones (o que no existen).

    Se comparan como texto, sin tener en cuenta el final de línea (git puede
    convertirlo en Windows).
    """
    return [ruta for ruta, texto in resumenes_esperados(ruta_manos, ruta_mus, ruta_cortes).items()
            if not ruta.exists()
            or ruta.read_text(encoding="utf-8").replace("\r\n", "\n") != texto]


def escribir_resumenes(ruta_manos: str | Path, ruta_mus: str | Path,
                       ruta_cortes: str | Path) -> list[Path]:
    """Regenera los dos resúmenes a partir de las anotaciones."""
    escritos = []
    for ruta, texto in resumenes_esperados(ruta_manos, ruta_mus, ruta_cortes).items():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(texto.encode("utf-8"))
        escritos.append(ruta)
    return escritos


# --- Rondas siguientes (dato para la Fase 6; no se usa en la calibración) -------------


@dataclass(frozen=True)
class RondasSiguientes:
    """Qué pasa después de una primera ronda con mus, en las manos incluidas.

    Atributos:
        con_mus: manos con mus en la primera ronda.
        por_rondas: rondas de mus antes del corte -> manos, entre las que se sabe.
    """

    con_mus: int
    por_rondas: tuple[tuple[int, int], ...]

    @property
    def conocidas(self) -> int:
        return sum(n for _, n in self.por_rondas)

    @property
    def otra_ronda(self) -> int:
        """Manos con al menos una segunda ronda de mus."""
        return sum(n for rondas, n in self.por_rondas if rondas >= 2)


def rondas_siguientes(manos: Sequence[ManoReal]) -> RondasSiguientes:
    con_mus = [m for m in manos if not m.excluida and m.hay_mus]
    rondas = Counter(m.rondas_de_mus for m in con_mus if m.rondas_de_mus is not None)
    return RondasSiguientes(len(con_mus), tuple(sorted(rondas.items())))
