"""Equity exacta: probabilidad de ganar cada lance según la mano y la posición.

Planteamiento
-------------
Fijada la mano del héroe, las otras tres se reparten de las 36 cartas
restantes. Como el reparto es intercambiable, se pueden enumerar en el orden
que convenga; aquí se enumera primero al **compañero** (P), luego al rival
del asiento más bajo (A) y por último al otro rival (B). El peso de cada
reparto es el número de repartos físicos que lo producen::

    w(P | mazo−H) · w(A | mazo−H−P) · w(B | mazo−H−P−A),   w(X | D) = ∏ C(D_r, x_r)

Sumar sobre 330³ ternas por mano sería caro, pero el último factor solo
depende del *mazo que queda* tras quitar P y A, y hay muy pocos mazos
distintos (≤ 6 435). Se precalcula una matriz ``W3[estado, B]`` y todo lo
demás son productos y sumas vectorizados (programación dinámica sobre la
composición del mazo). Los pesos son enteros y caben de sobra en un float64
(< 2⁵³), así que las sumas son exactas.

Todos los sucesos que interesan (ganar, que el lance se juegue, tantos) se
pueden escribir, fijado P, como un producto de condiciones sobre A y sobre B.
Las condiciones "fuerza de B menor que un umbral" se resuelven con sumas
acumuladas sobre las manos ordenadas por fuerza, sin recorrer umbrales.

Las condiciones de información (:mod:`mus.condiciones`) son máscaras por
asiento que multiplican los pesos; el resultado se normaliza por la
probabilidad de que se cumplan.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from math import comb
from pathlib import Path

import numpy as np

from mus.cartas import Mano, parsear_mano
from mus.condiciones import Condicion
from mus.evaluacion import JUGADORES, Lance, pareja_de
from mus.reglas import REGLAS_POR_DEFECTO, ReglasMus
from mus.simulacion import (
    Estimacion,
    EstimacionMedia,
    ganadores_lance,
    generador,
    repartir_con_mano,
    tantos_lance,
)
from mus.tablas import TablaManos, construir_tabla

POSICIONES = (1, 2, 3, 4)
_DESPLAZAMIENTO = 8
"""Margen para indexar C(d, k) con d negativo (manos imposibles), que vale 0."""
_BASE_ESTADO = 9
"""Base para codificar las cartas quitadas al mazo (hasta 8 por rango)."""


def companero_de(posicion: int) -> int:
    """Posición del compañero: 1↔3, 2↔4."""
    return (posicion + 1) % JUGADORES + 1


def rivales_de(posicion: int) -> tuple[int, int]:
    """Posiciones de los dos rivales, de menor a mayor."""
    a, b = (s for s in POSICIONES if pareja_de(s) != pareja_de(posicion))
    return a, b


# --- Resultados --------------------------------------------------------------


@dataclass(frozen=True)
class EquityLance:
    """Equity de una mano en un lance (probabilidades absolutas, no condicionadas
    a que el lance se juegue).

    Atributos:
        p_se_juega: probabilidad de que el lance se juegue.
        p_gana_individual: probabilidad de que el héroe gane el lance.
        p_gana_pareja: probabilidad de que lo gane su pareja (él o el compañero).
        tantos_netos: tantos esperados en paso a favor menos en contra.
    """

    lance: Lance
    p_se_juega: float
    p_gana_individual: float
    p_gana_pareja: float
    tantos_netos: float

    @property
    def p_gana_rival(self) -> float:
        return self.p_se_juega - self.p_gana_pareja


@dataclass(frozen=True)
class EquityMano:
    """Equity de una mano en una posición, opcionalmente con información."""

    texto_mano: str
    posicion: int
    por_lance: dict[Lance, EquityLance]
    p_condiciones: float
    """Probabilidad de que se cumplan las condiciones, dada la mano del héroe."""
    descripcion_condiciones: str

    @property
    def tantos_netos(self) -> float:
        """Tantos netos esperados en paso, sumando los cinco lances."""
        return sum(e.tantos_netos for e in self.por_lance.values())


# --- Datos por tabla ---------------------------------------------------------


@dataclass(frozen=True, eq=False)
class _DatosLance:
    fuerza: np.ndarray        # int64 por mano
    orden: np.ndarray         # manos ordenadas por fuerza
    fuerza_ordenada: np.ndarray
    base: np.ndarray          # 1.0 si la mano puede jugar el lance (punto: sin juego)
    valor: np.ndarray | None  # tantos de la jugada (pares, juego) o None


@lru_cache(maxsize=None)
def _datos(tabla: TablaManos) -> dict[Lance, _DatosLance]:
    sin_juego = (~tabla.tiene_juego).astype(np.float64)
    datos = {}
    for lance in Lance:
        f = tabla.fuerza[lance].astype(np.int64)
        orden = np.argsort(f, kind="stable")
        valor = tabla.valor_jugada(lance)
        datos[lance] = _DatosLance(
            fuerza=f, orden=orden, fuerza_ordenada=f[orden],
            base=sin_juego if lance is Lance.PUNTO else np.ones(tabla.n_manos),
            valor=None if valor is None else valor.astype(np.float64),
        )
    return datos


def _tabla_combinaciones(max_copias: int) -> np.ndarray:
    """``T[d + desplazamiento, k] = C(d, k)``, con 0 para d negativo."""
    filas = range(-_DESPLAZAMIENTO, max_copias + 1)
    return np.array([[comb(d, k) if d >= 0 else 0 for k in range(5)] for d in filas],
                    dtype=np.float64)


def _pesos(t: np.ndarray, conteos: np.ndarray, mazos: np.ndarray) -> np.ndarray:
    """``w[j, i] = ∏_r C(mazos[i, r], conteos[j, r])``: formas de sacar la mano j
    del mazo i. Forma (manos, mazos)."""
    w = np.ones((len(conteos), len(mazos)))
    for r in range(conteos.shape[1]):
        por_k = t[mazos[:, r] + _DESPLAZAMIENTO].T          # (5, mazos): C(d, k) por k
        w *= np.take(por_k, conteos[:, r], axis=0)          # filas contiguas por mano
    return w


# --- Motor -------------------------------------------------------------------


class _Contexto:
    """Pesos del reparto de las otras tres manos, fijada la del héroe.

    Atributos:
        w1[P]: formas de dar la mano P al compañero.
        w2[P, A]: formas de dar A al primer rival, dado P.
        estado[P, A]: índice del mazo restante tras quitar H, P y A.
        w3t[B, estado]: formas de dar B al segundo rival desde ese mazo. Se
            guarda traspuesta para que las sumas acumuladas sobre B recorran
            filas contiguas.
    """

    def __init__(self, tabla: TablaManos, heroe: int):
        conteos = tabla.conteos.astype(np.int64)
        t = _tabla_combinaciones(max(tabla.baraja.copias))
        restante = np.array(tabla.baraja.copias, dtype=np.int64) - conteos[heroe]

        self.n = tabla.n_manos
        self.w1 = _pesos(t, conteos, restante[None, :])[:, 0]
        self.w2 = _pesos(t, conteos, restante[None, :] - conteos).T * (self.w1 > 0)[:, None]

        valido = self.w2 > 0
        quitadas = conteos[:, None, :] + conteos[None, :, :]
        codigos = quitadas @ (_BASE_ESTADO ** np.arange(conteos.shape[1]))
        _, primero, inverso = np.unique(codigos[valido], return_index=True, return_inverse=True)
        self.estado = np.zeros((self.n, self.n), dtype=np.int64)
        self.estado[valido] = inverso
        mazos = restante[None, :] - quitadas[valido][primero]
        self.w3t = _pesos(t, conteos, mazos)
        self._ordenadas: dict[int, np.ndarray] = {}
        self._acumuladas: dict[tuple, np.ndarray] = {}
        self._cache: dict[tuple, np.ndarray] = {}

    @property
    def n_estados(self) -> int:
        return self.w3t.shape[1]

    def total(self, m_p: np.ndarray, m_a: np.ndarray, x: np.ndarray) -> float:
        """Σ_P w1·m_p Σ_A w2·m_a · x[P, A], donde x ya contiene la suma sobre B.

        ``m_a`` puede ser un vector (no depende de P) o una matriz [P, A].
        """
        return float(((self.w2 * m_a * x).sum(axis=1) * self.w1 * m_p).sum())

    def x_fija(self, m_b: np.ndarray) -> np.ndarray:
        """x[P, A] = Σ_B w3·m_b para una máscara de B que no depende de P.

        Se cachea por máscara: sin condiciones, las cuatro posiciones repiten
        las mismas máscaras.
        """
        clave = ("fija", m_b.tobytes())
        if clave not in self._cache:
            self._cache[clave] = (m_b @ self.w3t)[self.estado]
        return self._cache[clave]

    def x_umbral(self, m_b: np.ndarray, datos: _DatosLance, umbral: np.ndarray,
                 incluye_empate: np.ndarray) -> np.ndarray:
        """x[P, A] = Σ_B w3·m_b·[f_B < umbral[P]] (o ≤ si ``incluye_empate[P]``).

        Con las manos ordenadas por fuerza, la suma hasta un umbral es una
        suma acumulada: se calcula una vez y se indexa.
        """
        clave = (id(datos), m_b.tobytes())
        if clave not in self._acumuladas:
            if id(datos) not in self._ordenadas:  # W3 con las manos B ordenadas por fuerza
                self._ordenadas[id(datos)] = self.w3t[datos.orden]
            ordenada = self._ordenadas[id(datos)]
            acumulada = np.zeros((self.n + 1, self.n_estados))
            np.cumsum(ordenada * m_b[datos.orden][:, None], axis=0, out=acumulada[1:])
            self._acumuladas[clave] = acumulada
        acumulada = self._acumuladas[clave]
        k = np.where(incluye_empate,
                     np.searchsorted(datos.fuerza_ordenada, umbral, side="right"),
                     np.searchsorted(datos.fuerza_ordenada, umbral, side="left"))
        clave_x = ("umbral", *clave, k.tobytes())
        if clave_x not in self._cache:
            self._cache[clave_x] = acumulada[k[:, None], self.estado]
        return self._cache[clave_x]


def _equity_lance(ctx: _Contexto, datos: _DatosLance, tabla: TablaManos, heroe: int,
                  lance: Lance, posicion: int, mascaras: Mapping[int, np.ndarray],
                  z: float) -> EquityLance:
    """Equity de un lance para el héroe en ``posicion``; ``z`` normaliza las condiciones."""
    q = companero_de(posicion)
    a, b = rivales_de(posicion)
    c_p, c_a, c_b = mascaras[q], mascaras[a], mascaras[b]
    f, base, valor = datos.fuerza, datos.base, datos.valor
    f_h = f[heroe]

    if lance is Lance.PUNTO and tabla.tiene_juego[heroe]:
        return EquityLance(lance, 0.0, 0.0, 0.0, 0.0)  # el héroe tiene juego: no hay punto

    # P(el lance se juega)
    if lance in (Lance.GRANDE, Lance.CHICA):
        se_juega = z
    elif lance is Lance.PUNTO:
        se_juega = ctx.total(c_p * base, c_a * base, ctx.x_fija(c_b * base))
    else:  # pares o juego: se juega salvo que nadie participe
        nadie = (f == 0).astype(np.float64)
        sin_nadie = ctx.total(c_p * nadie, c_a * nadie, ctx.x_fija(c_b * nadie)) if f_h == 0 else 0.0
        se_juega = z - sin_nadie

    # Gana el héroe: cada otro asiento por debajo de él (empates a favor de quien va antes).
    if f_h == 0:
        gana_individual = 0.0
    else:
        def debajo(asiento: int, c: np.ndarray) -> np.ndarray:
            return c * base * ((f < f_h) | ((f == f_h) & (asiento > posicion)))
        gana_individual = ctx.total(debajo(q, c_p), debajo(a, c_a), ctx.x_fija(debajo(b, c_b)))

    # Gana la pareja: el mejor de (héroe, compañero) contra los dos rivales.
    umbral = np.maximum(f_h, f)                       # por cada mano P del compañero
    asiento_mejor = np.where(f > f_h, q, np.where(f < f_h, posicion, min(posicion, q)))
    m_p = c_p * base * (umbral > 0)
    empate_a = a > asiento_mejor                      # el rival va después: el empate es nuestro
    m_a = (c_a * base)[None, :] * ((f[None, :] < umbral[:, None])
                                   | ((f[None, :] == umbral[:, None]) & empate_a[:, None]))
    x_b = ctx.x_umbral(c_b * base, datos, umbral, b > asiento_mejor)
    gana_pareja = ctx.total(m_p, m_a, x_b)

    # Tantos netos en paso.
    if valor is None:
        tantos = tabla.tantos_fijos(lance) * (2 * gana_pareja - se_juega)
    else:
        a_favor = valor[heroe] * gana_pareja + ctx.total(m_p * valor, m_a, x_b)
        rivales_si_ganamos = (ctx.total(m_p, m_a * valor[None, :], x_b)
                              + ctx.total(m_p, m_a, ctx.x_umbral(c_b * base * valor, datos,
                                                                 umbral, b > asiento_mejor)))
        rivales_siempre = (ctx.total(c_p, c_a * valor, ctx.x_fija(c_b))
                           + ctx.total(c_p, c_a, ctx.x_fija(c_b * valor)))
        # Si no ganamos y el lance se juega, ganan ellos; si no se juega, sus jugadas valen 0.
        tantos = a_favor - (rivales_siempre - rivales_si_ganamos)

    return EquityLance(lance, se_juega / z, gana_individual / z, gana_pareja / z, tantos / z)


def _mascaras(tabla: TablaManos, posicion: int, companero: Condicion | None,
              rivales: Mapping[int, Condicion] | None) -> tuple[dict[int, np.ndarray], str]:
    condiciones: dict[int, Condicion] = dict(rivales or {})
    if any(s not in rivales_de(posicion) for s in condiciones):
        raise ValueError(f"Los rivales de la posición {posicion} son {rivales_de(posicion)}")
    if companero is not None:
        condiciones[companero_de(posicion)] = companero
    mascaras = {s: np.ones(tabla.n_manos) for s in POSICIONES if s != posicion}
    for s, c in condiciones.items():
        mascaras[s] = c.mascara(tabla).astype(np.float64)
    descripcion = "; ".join(f"jugador {s}: {c}" for s, c in sorted(condiciones.items()))
    return mascaras, descripcion or "sin información"


def _equity_con_contexto(ctx: _Contexto, tabla: TablaManos, heroe: int, posicion: int,
                         companero: Condicion | None,
                         rivales: Mapping[int, Condicion] | None) -> EquityMano:
    mascaras, descripcion = _mascaras(tabla, posicion, companero, rivales)
    q = companero_de(posicion)
    a, b = rivales_de(posicion)
    z = ctx.total(mascaras[q], mascaras[a], ctx.x_fija(mascaras[b]))
    if z == 0:
        raise ValueError(f"Las condiciones ({descripcion}) son imposibles con esta mano")
    datos = _datos(tabla)
    por_lance = {l: _equity_lance(ctx, datos[l], tabla, heroe, l, posicion, mascaras, z)
                 for l in Lance}
    p_cond = z / ctx.total(np.ones(ctx.n), np.ones(ctx.n), ctx.x_fija(np.ones(ctx.n)))
    return EquityMano(tabla.manos[heroe].texto(tabla.baraja), posicion, por_lance, p_cond,
                      descripcion)


# --- API pública -------------------------------------------------------------


def equity(
    mano: Mano | str,
    posicion: int,
    reglas: ReglasMus = REGLAS_POR_DEFECTO,
    *,
    companero: Condicion | None = None,
    rivales: Mapping[int, Condicion] | None = None,
) -> EquityMano:
    """Equity exacta de una mano en una posición (1 = mano, 4 = postre).

    Args:
        mano: la mano del héroe (objeto o texto como ``"R R C 5"``).
        posicion: posición del héroe.
        companero: condición conocida sobre la mano del compañero.
        rivales: condiciones sobre los rivales, por posición absoluta.

    Raises:
        ValueError: si la posición no es válida o las condiciones son imposibles.
    """
    if posicion not in POSICIONES:
        raise ValueError("La posición debe estar entre 1 y 4")
    tabla = construir_tabla(reglas)
    if isinstance(mano, str):
        mano = parsear_mano(mano, reglas)
    heroe = tabla.indice(mano)
    return _equity_con_contexto(_Contexto(tabla, heroe), tabla, heroe, posicion, companero, rivales)


@dataclass(frozen=True, eq=False)
class TablaEquity:
    """Equity sin información de todas las manos en todas las posiciones.

    Cada array tiene forma (manos, 4 posiciones, 5 lances), con los lances en
    el orden de :class:`Lance`.
    """

    tabla: TablaManos
    se_juega: np.ndarray
    gana_individual: np.ndarray
    gana_pareja: np.ndarray
    tantos_netos: np.ndarray

    def de(self, indice: int, posicion: int, lance: Lance) -> EquityLance:
        i, p, l = indice, posicion - 1, list(Lance).index(lance)
        return EquityLance(lance, float(self.se_juega[i, p, l]),
                           float(self.gana_individual[i, p, l]),
                           float(self.gana_pareja[i, p, l]), float(self.tantos_netos[i, p, l]))


_METRICAS = ("p_se_juega", "p_gana_individual", "p_gana_pareja", "tantos_netos")


def _filas_equity(reglas: ReglasMus, heroes: list[int]) -> np.ndarray:
    """Equity sin información de varias manos: array (manos, posiciones, lances, métricas).

    Es una función de módulo para poder ejecutarse en otro proceso.
    """
    tabla = construir_tabla(reglas)
    resultado = np.zeros((len(heroes), len(POSICIONES), len(Lance), len(_METRICAS)))
    for i, h in enumerate(heroes):
        ctx = _Contexto(tabla, h)  # se reutiliza en las 4 posiciones
        for p in POSICIONES:
            por_lance = _equity_con_contexto(ctx, tabla, h, p, None, None).por_lance
            for l, e in enumerate(por_lance.values()):
                resultado[i, p - 1, l] = [getattr(e, m) for m in _METRICAS]
    return resultado


def calcular_tabla_equity(reglas: ReglasMus = REGLAS_POR_DEFECTO,
                          procesos: int | None = None) -> TablaEquity:
    """Calcula (y cachea en memoria por reglas) la equity sin información de todas las manos.

    Args:
        procesos: procesos en paralelo (1 = sin paralelismo). Por defecto,
            hasta 4: el cálculo está limitado por el ancho de banda de memoria
            y más procesos no aceleran (medido: 1 → 83 s, 4 → 43 s, 8 → 45 s).
    """
    return _calcular_tabla_equity(reglas, procesos or min(4, os.cpu_count() or 1))


@lru_cache(maxsize=None)
def _calcular_tabla_equity(reglas: ReglasMus, procesos: int) -> TablaEquity:
    tabla = construir_tabla(reglas)
    heroes = list(range(tabla.n_manos))
    if procesos == 1:
        datos = _filas_equity(reglas, heroes)
    else:
        bloques = [heroes[i::procesos * 4] for i in range(procesos * 4)]  # bloques equilibrados
        with ProcessPoolExecutor(max_workers=procesos) as ejecutor:
            partes = list(ejecutor.map(_filas_equity, [reglas] * len(bloques), bloques))
        datos = np.zeros((tabla.n_manos, len(POSICIONES), len(Lance), len(_METRICAS)))
        for bloque, parte in zip(bloques, partes):
            datos[bloque] = parte
    return _tabla_equity_de_arrays(tabla, datos)


def _tabla_equity_de_arrays(tabla: TablaManos, datos: np.ndarray) -> TablaEquity:
    arrays = [np.ascontiguousarray(datos[..., k]) for k in range(len(_METRICAS))]
    for a in arrays:
        a.flags.writeable = False
    return TablaEquity(tabla, *arrays)


VERSION_MOTOR = "2"
"""Cambiarla invalida las tablas guardadas en disco si cambia el cálculo."""


def cargar_tabla_equity(reglas: ReglasMus = REGLAS_POR_DEFECTO,
                        directorio: str | Path = "resultados/cache") -> TablaEquity:
    """Como :func:`calcular_tabla_equity`, pero guarda el resultado en disco.

    El fichero se nombra con un hash de las reglas y de :data:`VERSION_MOTOR`,
    así que cambiar cualquier regla o el motor obliga a recalcular.
    """
    huella = hashlib.sha256(f"{reglas!r}|{VERSION_MOTOR}".encode()).hexdigest()[:16]
    ruta = Path(directorio) / f"equity_{huella}.npz"
    tabla = construir_tabla(reglas)
    if ruta.exists():
        with np.load(ruta) as f:
            return _tabla_equity_de_arrays(tabla, f["datos"])
    te = calcular_tabla_equity(reglas)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = np.stack([te.se_juega, te.gana_individual, te.gana_pareja, te.tantos_netos], axis=-1)
    np.savez_compressed(ruta, datos=datos)
    return te


# --- Verificación Monte Carlo ------------------------------------------------


@dataclass(frozen=True)
class EquityLanceMC:
    """Estimaciones Monte Carlo de las mismas magnitudes que :class:`EquityLance`."""

    lance: Lance
    p_se_juega: Estimacion
    p_gana_individual: Estimacion
    p_gana_pareja: Estimacion
    tantos_netos: EstimacionMedia


@dataclass(frozen=True)
class EquityManoMC:
    """Resultado de :func:`simular_equity`."""

    posicion: int
    n_simulados: int
    n_aceptados: int
    """Repartos que cumplen las condiciones (muestreo por rechazo)."""
    por_lance: dict[Lance, EquityLanceMC]

    @property
    def p_condiciones(self) -> Estimacion:
        return Estimacion(self.n_aceptados, self.n_simulados)


def simular_equity(
    mano: Mano | str,
    posicion: int,
    n: int,
    reglas: ReglasMus = REGLAS_POR_DEFECTO,
    *,
    companero: Condicion | None = None,
    rivales: Mapping[int, Condicion] | None = None,
    semilla: int | None = None,
    confianza: float = 0.95,
) -> EquityManoMC:
    """Estima por Monte Carlo lo mismo que :func:`equity`, para verificarla.

    Reparte ``n`` veces las otras tres manos y descarta los repartos que no
    cumplen las condiciones, de modo que el número efectivo de muestras es
    ``n_aceptados``.
    """
    tabla = construir_tabla(reglas)
    if isinstance(mano, str):
        mano = parsear_mano(mano, reglas)
    heroe = tabla.indice(mano)
    repartos = repartir_con_mano(n, tabla, generador(semilla), heroe, posicion)
    mascaras, _ = _mascaras(tabla, posicion, companero, rivales)
    acepta = np.ones(n, dtype=bool)
    for asiento, m in mascaras.items():
        acepta &= m[repartos[:, asiento - 1]] > 0
    repartos = repartos[acepta]
    m = len(repartos)
    if m < 2:
        raise ValueError("Casi ningún reparto cumple las condiciones: aumenta n")

    mi_pareja = pareja_de(posicion)
    por_lance = {}
    for lance in Lance:
        ganador = ganadores_lance(tabla, repartos, lance)
        tantos = tantos_lance(tabla, repartos, lance, ganador)
        nuestra = (ganador > 0) & ((ganador % 2 == 1) == (mi_pareja == 1))
        neto = np.where(nuestra, tantos, -tantos)
        por_lance[lance] = EquityLanceMC(
            lance,
            Estimacion(int((ganador > 0).sum()), m, confianza),
            Estimacion(int((ganador == posicion).sum()), m, confianza),
            Estimacion(int(nuestra.sum()), m, confianza),
            EstimacionMedia.de_muestra(neto.astype(np.float64), confianza),
        )
    return EquityManoMC(posicion, n, m, por_lance)
