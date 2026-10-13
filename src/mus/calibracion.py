"""Calibración de λ (cuánto cortan los rivales) con partidas reales.

El escenario de "rivales razonables" de la Fase 3c tiene un parámetro, λ
(``factor_corte``), que escala cuánto cortan los demás: λ = 0 es "nadie corta"
y λ = 1 los rivales razonables. Las decisiones dudosas dependen de él. La forma
de fijarlo es medir en partidas reales en qué proporción de manos hay mus en la
primera ronda y buscar el λ con el que el modelo da esa misma proporción.

Los datos salen de las anotaciones mano a mano de ``datos/manos_reales.csv``
(módulo :mod:`mus.manos_reales`), que generan ``datos/mus_real.csv``: una fila
por partida, con solo la primera ronda. Este módulo **no cambia nada**: informa
del λ compatible con los datos y de su incertidumbre. Con pocas manos el intervalo es tan ancho que no sirve; se
recomienda decidir con al menos :data:`MANOS_RECOMENDADAS`.

Limitaciones:

- λ resume en un número cómo cortan los jugadores. Los jugadores reales no
  cortan exactamente como "rivales razonables escalados"; dependen también del
  marcador, las señas y el estilo. Es una calibración gruesa.
- Los intervalos suponen manos independientes, y las de una misma partida no lo
  son del todo (mismos jugadores, mismo marcador).
  :func:`variacion_entre_partidas` mide si la frecuencia de mus varía entre
  partidas más de lo que daría el azar y cuánto se ensancharía el error.
- El usuario juega todas las partidas: sus decisiones pesan en los datos.
- Las partidas son online, en la aplicación Mus Maestro: los otros tres
  jugadores son los que tocan allí. La calibración describe a esa población,
  que no tiene por qué cortar como una mesa presencial.

Una comprobación más fina, que no se usa para ajustar nada:
``datos/cortes_por_posicion.csv`` (generado igual) dice cuántas veces le tocó
hablar a cada posición y cuántas cortó, y :func:`comparar_cortes` lo contrasta con lo que
predice el modelo para cada posición (por ejemplo, que la pareja segundo-postre
corta bastante más que la de la mano).
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from math import comb, exp, factorial, log, sqrt
from pathlib import Path
from statistics import NormalDist

import numpy as np

from mus.reglas import REGLAS_POR_DEFECTO, ReglasMus
from mus.simulacion import Estimacion

RUTA_DATOS = Path("datos/mus_real.csv")
RUTA_CORTES = Path("datos/cortes_por_posicion.csv")
MANOS_RECOMENDADAS = 40
LAMBDAS = tuple(round(0.1 * i, 1) for i in range(11))


@dataclass(frozen=True)
class Observacion:
    """Manos observadas en partidas reales y en cuántas hubo mus en la primera ronda."""

    manos: int
    con_mus: int

    def __post_init__(self) -> None:
        if self.manos <= 0 or not 0 <= self.con_mus <= self.manos:
            raise ValueError("Hace falta 0 <= manos con mus <= manos, y al menos una mano")

    def estimacion(self, confianza: float = 0.95) -> Estimacion:
        return Estimacion(self.con_mus, self.manos, confianza)


def leer_partidas(ruta: str | Path = RUTA_DATOS) -> list[Observacion]:
    """Una observación por fila del CSV (columnas ``manos`` y ``con_mus``)."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise ValueError(f"No existe {ruta}: genéralo con python -m mus manos-reales")
    with ruta.open(encoding="utf-8") as f:
        return [Observacion(int(fila["manos"]), int(fila["con_mus"])) for fila in csv.DictReader(f)]


def leer_observaciones(ruta: str | Path = RUTA_DATOS) -> Observacion:
    """Suma las partidas del CSV."""
    partidas = leer_partidas(ruta)
    return Observacion(sum(o.manos for o in partidas), sum(o.con_mus for o in partidas))


def curva_hay_mus(reglas: ReglasMus = REGLAS_POR_DEFECTO,
                  lambdas: tuple[float, ...] = LAMBDAS) -> list[tuple[float, float]]:
    """P(hay mus en la primera ronda) del modelo para cada λ (decreciente en λ).

    La primera vez simula cada λ (~15 s cada uno); después sale de la caché.
    """
    from mus.cortar import mesa_rivales_razonables

    return [(l, mesa_rivales_razonables(reglas, factor_corte=l).p_hay_mus) for l in lambdas]


def lambda_para(p: float, curva: list[tuple[float, float]]) -> tuple[float, bool]:
    """λ con el que el modelo da P(hay mus) = p, interpolando la curva.

    Returns:
        (λ, dentro): ``dentro`` es False si p queda fuera del rango del modelo y
        λ se ha recortado a 0 o a 1.
    """
    lambdas = [l for l, _ in curva]
    ps = [q for _, q in curva]
    if p >= ps[0]:
        return lambdas[0], p <= ps[0]
    if p <= ps[-1]:
        return lambdas[-1], p >= ps[-1]
    for (l0, p0), (l1, p1) in zip(curva, curva[1:]):
        if p1 <= p <= p0:
            return l0 + (l1 - l0) * (p0 - p) / (p0 - p1), True
    raise ValueError("La curva debe ser decreciente en λ")


@dataclass(frozen=True)
class Calibracion:
    observacion: Observacion
    p_observada: Estimacion
    lambda_estimada: float
    lambda_intervalo: tuple[float, float]
    dentro_del_rango: bool
    """False si la proporción observada queda fuera de lo que el modelo puede dar
    (más mus que con λ = 0, o menos que con λ = 1)."""
    intervalo_recortado: bool
    """True si algún extremo del intervalo de λ se ha recortado a 0 o 1."""

    @property
    def suficiente(self) -> bool:
        return self.observacion.manos >= MANOS_RECOMENDADAS


def calibrar(observacion: Observacion, curva: list[tuple[float, float]],
             confianza: float = 0.95) -> Calibracion:
    """λ compatible con la proporción de mus observada, con su intervalo.

    El intervalo de λ sale de invertir el intervalo de Wilson de la proporción:
    más mus observado corresponde a un λ menor.
    """
    p = observacion.estimacion(confianza)
    bajo, alto = p.intervalo
    lam, dentro = lambda_para(p.p, curva)
    (desde, dentro_alto), (hasta, dentro_bajo) = lambda_para(alto, curva), lambda_para(bajo, curva)
    return Calibracion(observacion, p, lam, (desde, hasta), dentro,
                       not (dentro_alto and dentro_bajo))


# --- Manos de una misma partida ----------------------------------------------------------


@dataclass(frozen=True)
class VariacionEntrePartidas:
    """¿Varía la frecuencia de mus entre partidas más de lo que daría el azar?

    Atributos:
        chi2: estadístico de Pearson de homogeneidad (todas las partidas con la
            misma probabilidad de mus), con ``grados`` = partidas − 1.
        p_valor: proporción de permutaciones con un χ² igual o mayor. Con
            partidas de pocas manos la aproximación χ² no vale; las permutaciones
            reparten al azar las manos con mus entre las partidas, con sus tamaños.
        factor_error: error típico de la proporción contando cada partida como un
            bloque (estimador robusto por conglomerados) dividido por el binomial.
            Si es ~1, el intervalo de Wilson, que supone manos independientes, vale.
    """

    chi2: float
    grados: int
    p_valor: Estimacion
    factor_error: float


def variacion_entre_partidas(partidas: Sequence[Observacion], permutaciones: int = 100_000,
                             semilla: int = 1) -> VariacionEntrePartidas:
    n = np.array([o.manos for o in partidas])
    k = np.array([o.con_mus for o in partidas])
    total, con_mus = int(n.sum()), int(k.sum())
    if len(partidas) < 2 or con_mus in (0, total):
        raise ValueError("Hacen falta al menos dos partidas y manos con y sin mus")
    p = con_mus / total

    def chi2(conteos: np.ndarray) -> np.ndarray:
        return ((conteos - n * p) ** 2 / (n * p * (1 - p))).sum(axis=-1)

    observado = float(chi2(k))
    rng = np.random.default_rng(semilla)
    manos = np.zeros(total, dtype=np.int16)
    manos[:con_mus] = 1
    inicios = np.concatenate(([0], np.cumsum(n)[:-1]))
    iguales_o_mas = 0
    for desde in range(0, permutaciones, 10_000):
        lote = rng.permuted(np.tile(manos, (min(10_000, permutaciones - desde), 1)), axis=1)
        iguales_o_mas += int((chi2(np.add.reduceat(lote, inicios, axis=1)) >= observado - 1e-9).sum())
    robusta = len(n) / (len(n) - 1) * float(((k - p * n) ** 2).sum()) / total ** 2
    return VariacionEntrePartidas(observado, len(n) - 1, Estimacion(iguales_o_mas, permutaciones),
                                  sqrt(robusta / (p * (1 - p) / total)))


# --- Corte por posición ----------------------------------------------------------------


@dataclass(frozen=True)
class CortesPorPosicion:
    """Veces que le tocó hablar a cada posición (1-4) y veces que cortó."""

    habla: tuple[int, ...]
    corta: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.habla) != 4 or len(self.corta) != 4:
            raise ValueError("Hace falta un dato por posición (4)")
        if any(not 0 <= c <= h for c, h in zip(self.corta, self.habla)) or self.habla[0] <= 0:
            raise ValueError("Hace falta 0 <= cortes <= veces que habla, y que la mano hable")

    @property
    def coherente(self) -> bool:
        """Una posición solo habla si nadie ha cortado antes: habla[p+1] = habla[p] − corta[p]."""
        return all(self.habla[p + 1] == self.habla[p] - self.corta[p] for p in range(3))

    @property
    def con_mus(self) -> int:
        """Manos en que no cortó nadie (si los datos son coherentes)."""
        return self.habla[3] - self.corta[3]


def leer_cortes(ruta: str | Path = RUTA_CORTES) -> CortesPorPosicion:
    """Suma las filas del CSV por posición (columnas ``posicion``, ``habla`` y ``corta``)."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise ValueError(f"No existe {ruta}: genéralo con python -m mus manos-reales")
    habla, corta = [0] * 4, [0] * 4
    with ruta.open(encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            p = int(fila["posicion"])
            if p not in (1, 2, 3, 4):
                raise ValueError(f"Posición no válida en {ruta}: {p}")
            habla[p - 1] += int(fila["habla"])
            corta[p - 1] += int(fila["corta"])
    return CortesPorPosicion(tuple(habla), tuple(corta))


def p_binomial_bilateral(k: int, n: int, p: float) -> float:
    """p-valor exacto bilateral de observar ``k`` éxitos en ``n`` con probabilidad ``p``.

    Suma la probabilidad de todos los resultados tan improbables o más que el
    observado (el criterio habitual del test binomial exacto).
    """
    probabilidades = [comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)]
    umbral = probabilidades[k] * (1 + 1e-7)
    return min(1.0, sum(q for q in probabilidades if q <= umbral))


def cola_chi2(x: float, grados: int) -> float:
    """P(χ² con ``grados`` grados de libertad ≥ x).

    Con grados pares es exacta: e^(−x/2) Σ_{i<g/2} (x/2)^i / i!. Con impares se
    usa la aproximación de Wilson-Hilferty (sin depender de SciPy).
    """
    if grados % 2 == 0:
        return exp(-x / 2) * sum((x / 2) ** i / factorial(i) for i in range(grados // 2))
    z = ((x / grados) ** (1 / 3) - (1 - 2 / (9 * grados))) / sqrt(2 / (9 * grados))
    return 1 - NormalDist().cdf(z)


@dataclass(frozen=True)
class ComparacionCortes:
    """Corte por posición observado frente al del modelo.

    Atributos:
        observado: datos reales.
        modelo: P(corta | le toca hablar) del modelo en cada posición.
    """

    observado: CortesPorPosicion
    modelo: tuple[float, ...]

    def posicion(self, p: int, confianza: float = 0.95) -> tuple[Estimacion, float, float]:
        """(proporción observada con su IC, valor del modelo, p-valor binomial exacto)."""
        k, n = self.observado.corta[p - 1], self.observado.habla[p - 1]
        return (Estimacion(k, n, confianza), self.modelo[p - 1],
                p_binomial_bilateral(k, n, self.modelo[p - 1]))

    def chi2(self) -> tuple[float, int, float]:
        """Contraste global de Pearson: (χ², grados de libertad, p-valor).

        Cada posición es una binomial con las veces que habló; el modelo está
        fijado de antemano, así que hay 4 grados de libertad.
        """
        x = sum((c - n * q) ** 2 / (n * q * (1 - q))
                for c, n, q in zip(self.observado.corta, self.observado.habla, self.modelo) if n)
        return x, 4, cola_chi2(x, 4)

    def pareja(self, posiciones: Sequence[int]) -> tuple[Estimacion, float]:
        """Corte de una pareja: proporción observada y la que espera el modelo
        con las mismas veces que habló cada posición."""
        k = sum(self.observado.corta[p - 1] for p in posiciones)
        n = sum(self.observado.habla[p - 1] for p in posiciones)
        esperado = sum(self.observado.habla[p - 1] * self.modelo[p - 1] for p in posiciones)
        return Estimacion(k, n), esperado / n

    def razon_parejas(self, confianza: float = 0.95) -> tuple[float, tuple[float, float], float]:
        """Cuántas veces más corta la pareja 2-4 que la 1-3: observado, su IC
        (método delta sobre el logaritmo) y lo que predice el modelo."""
        (mano, modelo_mano), (postre, modelo_postre) = self.pareja((1, 3)), self.pareja((2, 4))
        razon = postre.p / mano.p
        error = sqrt((1 - mano.p) / mano.exitos + (1 - postre.p) / postre.exitos)
        z = NormalDist().inv_cdf(0.5 + confianza / 2)
        return razon, (razon * exp(-z * error), razon * exp(z * error)), modelo_postre / modelo_mano


@dataclass(frozen=True)
class ContrastePareja:
    """¿Se reparte el corte dentro de la pareja segundo-postre como dice el modelo?

    Atributos:
        diferencia: (corte observado del postre − el del modelo) − (lo mismo para
            el segundo), en proporción. Positiva si, respecto al modelo, el
            postre corta de más y el segundo de menos.
        p_valor: proporción de sesiones simuladas con el modelo, con las mismas
            manos, cuya diferencia es tan grande o más en valor absoluto.
    """

    diferencia: float
    p_valor: Estimacion


def contraste_segundo_postre(observado: CortesPorPosicion, modelo: Sequence[float],
                             simulaciones: int = 200_000, semilla: int = 1) -> ContrastePareja:
    """Contrasta si el segundo corta de menos y el postre de más (o al revés)
    respecto al modelo, que por parejas puede encajar aunque dentro de la pareja no.

    Sirve para una hipótesis concreta: que el segundo dé mus para que decida su
    compañero, el postre, que habla el último. El modelo no tiene esa
    coordinación. Con el modelo, quién corta primero en cada mano es una
    multinomial (cada posición corta con su probabilidad si le llega el turno), y
    las manos se suponen independientes, como en el resto de la calibración.
    """
    q = tuple(modelo)
    if len(q) != 4 or not all(0 < x < 1 for x in q):
        raise ValueError("El modelo debe dar una probabilidad de corte en (0, 1) por posición")
    if observado.habla[1] == 0 or observado.habla[3] == 0:
        raise ValueError("Hace falta que el segundo y el postre hayan hablado alguna vez")

    def diferencia(habla2, corta2, habla4, corta4):
        return (corta4 / habla4 - q[3]) - (corta2 / habla2 - q[1])

    d = float(diferencia(observado.habla[1], observado.corta[1],
                         observado.habla[3], observado.corta[3]))
    # Probabilidad de que el primero en cortar sea cada posición, o de que haya mus.
    llega = np.cumprod([1.0, *(1 - x for x in q)])
    probabilidades = [*(llega[p] * q[p] for p in range(4)), llega[4]]
    manos = observado.habla[0]
    cuentas = np.random.default_rng(semilla).multinomial(manos, probabilidades, size=simulaciones)
    habla2 = manos - cuentas[:, 0]
    habla4 = habla2 - cuentas[:, 1] - cuentas[:, 2]
    validas = (habla2 > 0) & (habla4 > 0)
    simuladas = diferencia(habla2[validas], cuentas[validas, 1], habla4[validas], cuentas[validas, 3])
    extremas = int((np.abs(simuladas) >= abs(d) - 1e-12).sum())
    return ContrastePareja(d, Estimacion(extremas, int(validas.sum())))


def cortes_del_modelo(reglas: ReglasMus = REGLAS_POR_DEFECTO, factor_corte: float = 1.0
                      ) -> tuple[float, ...]:
    """P(corta | le toca hablar) de cada posición en la mesa de rivales razonables ×λ."""
    from mus.cortar import mesa_rivales_razonables

    mesa = mesa_rivales_razonables(reglas, factor_corte=factor_corte)
    return tuple(mesa.p_cortar(p) for p in (1, 2, 3, 4))


def comparar_cortes(observado: CortesPorPosicion, modelo: Sequence[float]) -> ComparacionCortes:
    if len(modelo) != 4 or not all(0 < q < 1 for q in modelo):
        raise ValueError("El modelo debe dar una probabilidad de corte en (0, 1) por posición")
    return ComparacionCortes(observado, tuple(modelo))
