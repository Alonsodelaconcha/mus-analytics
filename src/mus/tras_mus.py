"""Fase 3b: la mesa después de una ronda de mus.

Si los cuatro jugadores se descartan según una política, las manos con las que
se juegan los lances ya no siguen la distribución del reparto inicial. Aquí se
calcula esa distribución, la equity contra ella y se itera hasta que la
política de descarte y la equity sean coherentes entre sí (punto fijo).

Piezas:

1. **Marginal exacta de cada asiento.** Desde el punto de vista de un jugador,
   las cartas que roba son un subconjunto uniforme de las 36 que no ve, hagan
   lo que hagan los demás (ver :mod:`mus.descarte`). Por tanto, la mano final
   del asiento s sigue exactamente q_s = p0 · M_s, donde M_s[h, h'] es la
   probabilidad de acabar con h' partiendo de h con la política de s.

2. **Equity tras el mus por simulación de la ronda completa** (reparto,
   descartes en orden desde la mano, robo del mazo y lances en paso),
   agrupando por la mano final de cada asiento, con su error típico.

   Se probó antes una alternativa con el motor exacto: reponderar el reparto
   uniforme con pesos q_s/p0 por asiento. La verificación contra la simulación
   la descartó (errores de 0,3-0,6 tantos totales). El motivo: no reproduce
   las marginales. En un reparto de un único mazo, los pesos de los cuatro
   asientos compiten por las mismas 16 figuras y cada asiento queda con un
   48 % de juego en lugar del 60 % real; en la mesa real las cartas bajas
   tiradas salen del juego y se reponen del mazo (las 16 cartas finales
   llevan 9,8 figuras de media frente a 6,4 en el reparto). Ver
   docs/decisiones.md.

3. **Valoración de las opciones de una mano concreta** simulando la ronda con
   esa mano fija: incluye el efecto de mis propios descartes y la conjunta
   real, y usa los mismos repartos para todas las opciones (números aleatorios
   comunes), así que las diferencias entre opciones tienen poco ruido.

Simplificación de esta versión: todos dan mus siempre (sin efecto de
selección por cortar, que llega en la 3c).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import NormalDist

import numpy as np

from mus.cartas import CARTAS_POR_MANO, Mano, parsear_mano
from mus.descarte import (
    OBJETIVOS,
    UMBRAL_EQUIVALENCIA,
    Objetivo,
    OpcionDescarte,
    TablaDescartes,
    construir_tabla_descartes,
)
from mus.equity import POSICIONES, TablaEquity, calcular_tabla_equity, cargar_tabla_equity
from mus.evaluacion import JUGADORES, Lance
from mus.reglas import REGLAS_POR_DEFECTO, ReglasMus
from mus.simulacion import (
    TAMANO_LOTE,
    Estimacion,
    EstimacionMedia,
    ganadores_lance,
    generador,
    tantos_lance,
)
from mus.tablas import TablaManos, potencias_codigo

LANCES = tuple(Lance)
TOLERANCIA_EXPLOTABILIDAD = 0.001
"""Ganancia media por mano (tantos) por debajo de la cual se da la política por
convergida: desviarse de forma óptima ganaría menos de un tanto cada mil manos."""
SIMULACIONES_POR_VUELTA = 4_000_000
SEMILLA_MESA = 20261006
VERSION_SIMULACION = "1"
"""Cambiarla invalida las tablas simuladas guardadas en disco."""


# --- Estructura densa de las opciones de descarte ------------------------------


@dataclass(frozen=True, eq=False)
class _Opciones:
    """Opciones de descarte en arrays densos, con relleno hasta el máximo de opciones.

    Atributos:
        transicion: (manos, max_opciones, manos) distribución de la mano final.
        valida: (manos, max_opciones) True en las opciones reales.
        n_descartes: (manos, max_opciones) cartas pedidas (−1 en el relleno).
        codigo_conservadas: (manos, max_opciones) código de las cartas que se quedan.
    """

    transicion: np.ndarray
    valida: np.ndarray
    n_descartes: np.ndarray
    codigo_conservadas: np.ndarray


@lru_cache(maxsize=None)
def _opciones_densas(td: TablaDescartes) -> _Opciones:
    n = td.tabla.n_manos
    maximo = max(len(o) for o in td.opciones)
    potencias = potencias_codigo(td.tabla.baraja)
    transicion = np.zeros((n, maximo, n))
    valida = np.zeros((n, maximo), dtype=bool)
    n_descartes = np.full((n, maximo), -1, dtype=np.int64)
    codigo = np.zeros((n, maximo), dtype=np.int64)
    for h, (opciones, matriz) in enumerate(zip(td.opciones, td.transicion)):
        k = len(opciones)
        transicion[h, :k] = matriz
        valida[h, :k] = True
        n_descartes[h, :k] = [o.n_descartes for o in opciones]
        codigo[h, :k] = [np.array(o.conservadas) @ potencias for o in opciones]
    for a in (transicion, valida, n_descartes, codigo):
        a.flags.writeable = False
    return _Opciones(transicion, valida, n_descartes, codigo)


# --- Políticas -------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Politica:
    """Probabilidad de elegir cada opción de descarte, por posición y mano.

    ``probabilidades`` tiene forma (4, manos, max_opciones); cada fila suma 1
    sobre las opciones válidas de la mano. Una política *pura* elige siempre
    una única opción; las mixtas aparecen al amortiguar la iteración.
    """

    td: TablaDescartes
    probabilidades: np.ndarray

    @property
    def principal(self) -> np.ndarray:
        """Opción más probable de cada (posición, mano): array (4, manos)."""
        return self.probabilidades.argmax(axis=2)

    @property
    def es_pura(self) -> bool:
        return bool(np.isin(self.probabilidades, (0.0, 1.0)).all())

    def mezclar(self, otra: Politica, alfa: float) -> Politica:
        """(1 − alfa)·esta + alfa·otra."""
        return Politica(self.td, (1 - alfa) * self.probabilidades + alfa * otra.probabilidades)

    def diferencia(self, otra: Politica) -> float:
        """Máxima diferencia de probabilidad entre las dos políticas."""
        return float(np.abs(self.probabilidades - otra.probabilidades).max())

    def cambios(self, otra: Politica) -> np.ndarray:
        """(4, manos) True donde cambia la opción principal."""
        return self.principal != otra.principal

    def transicion(self, posicion: int) -> np.ndarray:
        """M[h, h'] = P(mano final h' | mano inicial h) con la política de esa posición."""
        return np.einsum("ho,hok->hk", self.probabilidades[posicion - 1],
                         _opciones_densas(self.td).transicion)

    def marginal(self, posicion: int) -> np.ndarray:
        """Distribución exacta de la mano final del asiento ``posicion``."""
        return self.td.tabla.probabilidad @ self.transicion(posicion)

    def cartas_pedidas(self, posicion: int) -> dict[int, float]:
        """P(pedir k cartas) en esa posición, ponderada por la probabilidad de cada mano."""
        op = _opciones_densas(self.td)
        prob = self.td.tabla.probabilidad[:, None] * self.probabilidades[posicion - 1]
        return {k: float(prob[op.n_descartes == k].sum()) for k in range(CARTAS_POR_MANO + 1)
                if (op.n_descartes == k).any()}

    def huella(self) -> str:
        return hashlib.sha256(np.ascontiguousarray(self.probabilidades).tobytes()).hexdigest()


def _valores_opciones(td: TablaDescartes, te: TablaEquity, objetivo: Objetivo,
                      posicion: int) -> np.ndarray:
    """(manos, max_opciones) valor esperado de cada opción; −inf en el relleno."""
    op = _opciones_densas(td)
    return np.where(op.valida, op.transicion @ objetivo.valores(te, posicion), -np.inf)


def mejor_respuesta(td: TablaDescartes, te: TablaEquity, objetivo: Objetivo) -> Politica:
    """Política pura que, en cada posición, elige el descarte de mayor valor según ``te``."""
    op = _opciones_densas(td)
    probabilidades = np.zeros((len(POSICIONES), *op.valida.shape))
    filas = np.arange(td.tabla.n_manos)
    for p in POSICIONES:
        probabilidades[p - 1, filas, _valores_opciones(td, te, objetivo, p).argmax(axis=1)] = 1.0
    return Politica(td, probabilidades)


def ganancia_por_desviarse(politica: Politica, te: TablaEquity, objetivo: Objetivo
                           ) -> np.ndarray:
    """(4, manos): cuánto ganaría cada jugador cambiando a su mejor respuesta.

    Es max_o V(o) − Σ_o π(o)·V(o), en las unidades del objetivo. Si es menor
    que un ε en todas partes, la política es un ε-equilibrio: las decisiones
    que aún cambien son prácticamente equivalentes.
    """
    ganancia = np.zeros((len(POSICIONES), politica.td.tabla.n_manos))
    for p in POSICIONES:
        v = _valores_opciones(politica.td, te, objetivo, p)
        v_politica = (politica.probabilidades[p - 1] * np.where(np.isfinite(v), v, 0)).sum(axis=1)
        ganancia[p - 1] = v.max(axis=1) - v_politica
    return ganancia


def no_descartar(td: TablaDescartes) -> Politica:
    """Política que se queda servida (solo existe si ``reglas.descarte.minimo == 0``).

    Sirve para verificar el simulador: con ella la mesa tras el mus es la del
    reparto inicial, cuya equity exacta se conoce (Fase 2).
    """
    op = _opciones_densas(td)
    servida = op.n_descartes == 0
    if not servida.any(axis=1).all():
        raise ValueError("Quedarse servido no es una opción con estas reglas (minimo > 0)")
    probabilidades = np.broadcast_to(servida.astype(np.float64),
                                     (len(POSICIONES), *servida.shape)).copy()
    return Politica(td, probabilidades)


def marginales(politica: Politica) -> np.ndarray:
    """Distribución exacta de la mano final de cada asiento: array (4, manos)."""
    return np.stack([politica.marginal(p) for p in POSICIONES])


def _elegir(acumuladas: np.ndarray, valida: np.ndarray, manos: np.ndarray,
            u: np.ndarray) -> np.ndarray:
    """Opción elegida por cada mano según las probabilidades acumuladas y un uniforme u."""
    opcion = (u[:, None] > acumuladas[manos]).sum(axis=1)
    return np.minimum(opcion, valida[manos].sum(axis=1) - 1)  # por redondeo, nunca el relleno


# --- Monte Carlo de la ronda completa ----------------------------------------------


@dataclass(frozen=True, eq=False)
class SimulacionMesa:
    """Acumulados de una simulación de la ronda de mus, por asiento y mano final.

    Los arrays (4, manos, 5 lances) suman, sobre los repartos en que ese
    asiento acaba con esa mano: si gana él, si gana su pareja, si el lance se
    juega y los tantos netos de su pareja (y sus cuadrados, para los IC).
    """

    n: int
    frecuencias: np.ndarray            # (4, manos) manos finales
    gana_individual: np.ndarray
    gana_pareja: np.ndarray
    se_juega: np.ndarray
    tantos: np.ndarray
    tantos_cuadrado: np.ndarray
    tantos_total: np.ndarray           # (4, manos) suma de tantos netos de todos los lances
    tantos_total_cuadrado: np.ndarray
    cartas_pedidas: np.ndarray         # (4, 5) veces que se piden k = 0..4 cartas


def _repartir_y_descartar(politica: Politica, m: int, rng: np.random.Generator
                          ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reparte ``m`` manos completas y aplica la ronda de mus con la política.

    Returns:
        (iniciales, finales, pedidas): arrays (m, 4) con las manos iniciales, las
        finales y las cartas que pide cada asiento. Se descartan y roban en
        orden desde la mano; en la primera ronda el mazo no se agota (se piden
        como mucho 16 cartas y quedan 24).
    """
    td = politica.td
    tabla = td.tabla
    op = _opciones_densas(td)
    potencias = potencias_codigo(tabla.baraja)
    mazo = np.array(tabla.baraja.cartas(), dtype=np.int8)
    acumuladas = np.cumsum(politica.probabilidades, axis=2)
    filas = np.arange(m)
    barajado = rng.permuted(np.tile(mazo, (m, 1)), axis=1)
    iniciales = tabla.indices_de_codigos(
        potencias[barajado[:, :16]].reshape(m, JUGADORES, CARTAS_POR_MANO).sum(axis=2))
    # Código acumulado de las cartas del mazo, para sacar lo que roba cada uno.
    robo = np.zeros((m, 25), dtype=np.int64)
    np.cumsum(potencias[barajado[:, 16:]], axis=1, out=robo[:, 1:])
    inicio = np.zeros(m, dtype=np.int64)
    finales = np.empty((m, JUGADORES), dtype=np.int64)
    pedidas = np.empty((m, JUGADORES), dtype=np.int64)
    for s in range(JUGADORES):
        h = iniciales[:, s]
        opcion = _elegir(acumuladas[s], op.valida, h, rng.random(m))
        k = op.n_descartes[h, opcion]
        robado = robo[filas, inicio + k] - robo[filas, inicio]
        finales[:, s] = tabla.indices_de_codigos(op.codigo_conservadas[h, opcion] + robado)
        pedidas[:, s] = k
        inicio += k
    return iniciales, finales, pedidas


def tantos_netos_por_asiento(tabla: TablaManos, manos: np.ndarray,
                             pesos_lance: tuple[float, ...] | None = None) -> np.ndarray:
    """(m, 4) tantos netos en paso de la pareja de cada asiento, sumando los lances
    (ponderados por ``pesos_lance`` si se dan)."""
    neto = np.zeros(manos.shape)
    for l, lance in enumerate(LANCES):
        peso = 1.0 if pesos_lance is None else pesos_lance[l]
        if peso == 0:
            continue
        g = ganadores_lance(tabla, manos, lance)
        t = tantos_lance(tabla, manos, lance, g)
        for s in range(JUGADORES):
            mia = (g > 0) & ((g % 2 == 1) == (s % 2 == 0))
            neto[:, s] += peso * np.where(mia, t, np.where(g > 0, -t, 0))
    return neto


def tantos_netos_por_lance(tabla: TablaManos, manos: np.ndarray, posicion: int) -> np.ndarray:
    """(m, lances) tantos netos en paso de la pareja del asiento ``posicion`` (1-4)
    en cada lance, sin ponderar.

    Sumados por filas con :func:`sumar_lances` dan, bit a bit, la columna de ese
    asiento de :func:`tantos_netos_por_asiento`.
    """
    neto = np.empty((len(manos), len(LANCES)))
    pareja_de_la_mano = posicion % 2 == 1
    for l, lance in enumerate(LANCES):
        g = ganadores_lance(tabla, manos, lance)
        t = tantos_lance(tabla, manos, lance, g)
        mia = (g > 0) & ((g % 2 == 1) == pareja_de_la_mano)
        neto[:, l] = np.where(mia, t, np.where(g > 0, -t, 0))
    return neto


def sumar_lances(por_lance: np.ndarray, pesos_lance: tuple[float, ...] | None = None) -> np.ndarray:
    """(m,) suma de los lances de :func:`tantos_netos_por_lance`, ponderados por
    ``pesos_lance`` si se dan. Suma en el mismo orden que
    :func:`tantos_netos_por_asiento`, para dar exactamente lo mismo."""
    total = np.zeros(len(por_lance))
    for l in range(por_lance.shape[1]):
        peso = 1.0 if pesos_lance is None else pesos_lance[l]
        if peso == 0:
            continue
        total += peso * por_lance[:, l]
    return total


class _Acumulador:
    """Acumula, por asiento y mano final, los resultados de los lances (con pesos)."""

    def __init__(self, tabla: TablaManos):
        self.tabla = tabla
        nm, nl = tabla.n_manos, len(LANCES)
        self.n = 0
        self.lances = {k: np.zeros((JUGADORES, nm, nl)) for k in
                       ("gana_individual", "gana_pareja", "se_juega", "tantos", "tantos_cuadrado")}
        self.frecuencias = np.zeros((JUGADORES, nm))
        self.total = np.zeros((JUGADORES, nm))
        self.total_cuadrado = np.zeros((JUGADORES, nm))
        self.pedidas = np.zeros((JUGADORES, CARTAS_POR_MANO + 1))

    def sumar(self, finales: np.ndarray, pedidas: np.ndarray, pesos: np.ndarray | None = None,
              pesos_lance: tuple[float, ...] | None = None) -> np.ndarray:
        """Añade un lote de repartos (con un peso por reparto).

        Devuelve los tantos netos de cada asiento (m, 4), sumando los lances
        ponderados por ``pesos_lance`` (o sin ponderar si no se dan); la tabla
        acumulada guarda siempre los tantos sin ponderar.
        """
        tabla, nm = self.tabla, self.tabla.n_manos
        m = len(finales)
        w = np.ones(m) if pesos is None else pesos
        self.n += m
        neto_total = np.zeros((m, JUGADORES))
        neto_objetivo = np.zeros((m, JUGADORES))
        for l, lance in enumerate(LANCES):
            g = ganadores_lance(tabla, finales, lance)
            t = tantos_lance(tabla, finales, lance, g)
            for s in range(JUGADORES):
                mia = (g > 0) & ((g % 2 == 1) == (s % 2 == 0))
                neto = np.where(mia, t, np.where(g > 0, -t, 0)).astype(np.float64)
                neto_total[:, s] += neto
                neto_objetivo[:, s] += neto * (1.0 if pesos_lance is None else pesos_lance[l])
                f = finales[:, s]
                for clave, valores in (("gana_individual", g == s + 1), ("gana_pareja", mia),
                                       ("se_juega", g > 0), ("tantos", neto),
                                       ("tantos_cuadrado", neto * neto)):
                    self.lances[clave][s, :, l] += np.bincount(f, weights=valores * w,
                                                               minlength=nm)
        for s in range(JUGADORES):
            f = finales[:, s]
            self.frecuencias[s] += np.bincount(f, weights=w, minlength=nm)
            self.total[s] += np.bincount(f, weights=neto_total[:, s] * w, minlength=nm)
            self.total_cuadrado[s] += np.bincount(f, weights=neto_total[:, s] ** 2 * w,
                                                  minlength=nm)
            self.pedidas[s] += np.bincount(pedidas[:, s], weights=w,
                                           minlength=CARTAS_POR_MANO + 1)
        return neto_objetivo

    def resultado(self) -> SimulacionMesa:
        l = self.lances
        return SimulacionMesa(self.n, self.frecuencias, l["gana_individual"], l["gana_pareja"],
                              l["se_juega"], l["tantos"], l["tantos_cuadrado"], self.total,
                              self.total_cuadrado, self.pedidas)


def simular_ronda_mus(politica: Politica, n: int, semilla: int | None = None,
                      tamano_lote: int = TAMANO_LOTE) -> SimulacionMesa:
    """Simula ``n`` manos completas: reparto, mus con la política y lances en paso."""
    rng = generador(semilla)
    acumulador = _Acumulador(politica.td.tabla)
    hechos = 0
    while hechos < n:
        m = min(tamano_lote, n - hechos)
        hechos += m
        _, finales, pedidas = _repartir_y_descartar(politica, m, rng)
        acumulador.sumar(finales, pedidas)
    return acumulador.resultado()


@dataclass(frozen=True, eq=False)
class EquitySimulada:
    """Tabla de equity tras el mus estimada por simulación.

    Atributos:
        tabla: medias por (mano final, posición, lance), en el formato de la Fase 2.
        muestras: (manos, 4) repartos en que cada asiento acabó con cada mano.
        error_tantos: (manos, 4) error típico de los tantos netos totales.
    """

    tabla: TablaEquity
    muestras: np.ndarray
    error_tantos: np.ndarray


def equity_simulada(sim: SimulacionMesa, respaldo: TablaEquity) -> EquitySimulada:
    """Convierte los acumulados de una simulación en tabla de equity.

    Las manos finales que no han salido nunca (probabilidad despreciable) toman
    el valor de ``respaldo``; no afectan a ninguna decisión.
    """
    muestras = sim.frecuencias.T                                   # (manos, 4)
    sin = muestras == 0
    divisor = np.where(sin, 1.0, muestras)[:, :, None]

    def media(acumulado: np.ndarray, valor_respaldo: np.ndarray) -> np.ndarray:
        m = acumulado.transpose(1, 0, 2) / divisor
        return np.where(sin[:, :, None], valor_respaldo, m)

    tabla = TablaEquity(
        respaldo.tabla,
        media(sim.se_juega, respaldo.se_juega),
        media(sim.gana_individual, respaldo.gana_individual),
        media(sim.gana_pareja, respaldo.gana_pareja),
        media(sim.tantos, respaldo.tantos_netos),
    )
    c = np.maximum(muestras, 2)
    media_total = sim.tantos_total.T / c
    varianza = np.maximum(sim.tantos_total_cuadrado.T / c - media_total ** 2, 0) * c / (c - 1)
    # Sin muestras suficientes no hay estimación del error: se usa la desviación
    # típica más grande observada, como cota prudente de una sola muestra.
    error = np.where(muestras < 2, np.sqrt(varianza.max()), np.sqrt(varianza / c))
    return EquitySimulada(tabla, muestras, error)


def _equity_de_politica(politica: Politica, n: int, semilla: int, respaldo: TablaEquity,
                        directorio: str | None) -> EquitySimulada:
    """Simula la ronda con la política y la convierte en tabla (con caché en disco)."""
    ruta = None
    if directorio is not None:
        texto = (f"{politica.td.tabla.reglas!r}|{VERSION_SIMULACION}|{n}|{semilla}|"
                 f"{politica.huella()}")
        ruta = Path(directorio) / f"mesa_{hashlib.sha256(texto.encode()).hexdigest()[:16]}.npz"
        if ruta.exists():
            with np.load(ruta) as f:
                tabla = TablaEquity(respaldo.tabla, *(f[k] for k in
                                    ("se_juega", "gana_individual", "gana_pareja", "tantos")))
                return EquitySimulada(tabla, f["muestras"], f["error"])
    resultado = equity_simulada(simular_ronda_mus(politica, n, semilla), respaldo)
    if ruta is not None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        t = resultado.tabla
        np.savez_compressed(ruta, se_juega=t.se_juega, gana_individual=t.gana_individual,
                            gana_pareja=t.gana_pareja, tantos=t.tantos_netos,
                            muestras=resultado.muestras, error=resultado.error_tantos)
    return resultado


# --- Iteración hasta el punto fijo ---------------------------------------------------


@dataclass(frozen=True)
class Iteracion:
    """Resumen de una vuelta de la iteración."""

    numero: int
    cambios: int
    """(posición, mano) cuya opción principal cambia con la mejor respuesta."""
    cambios_ponderados: float
    """Proporción de repartos afectados por esos cambios (media de las 4 posiciones)."""
    diferencia: float
    """Máxima diferencia de probabilidad entre la política y su mejor respuesta."""
    ganancia_maxima: float
    """Lo máximo que ganaría un jugador, en alguna mano y posición, desviándose."""
    ganancia_media: float
    """Ganancia media por desviarse, ponderada por la probabilidad de cada mano."""
    amortiguacion: float
    """Peso de la mejor respuesta al actualizar (1 = sin amortiguar)."""


@dataclass(frozen=True, eq=False)
class MesaTrasMus:
    """Resultado de :func:`iterar_tras_mus`."""

    reglas: ReglasMus
    objetivo: Objetivo
    politica: Politica
    marginales: np.ndarray
    """(4, manos): distribución exacta de la mano final de cada asiento."""
    equity: EquitySimulada
    """Equity de cada mano final contra la mesa tras el mus (simulada)."""
    tabla_inicial: TablaEquity
    """Equity del reparto inicial (Fase 2): la de cortar sin que nadie se descarte."""
    historia: tuple[Iteracion, ...]
    convergio: bool
    simulaciones: int
    semilla: int

    @property
    def tabla(self) -> TablaEquity:
        return self.equity.tabla


def iterar_tras_mus(
    reglas: ReglasMus = REGLAS_POR_DEFECTO,
    objetivo: Objetivo = OBJETIVOS["tantos"],
    *,
    simulaciones: int = SIMULACIONES_POR_VUELTA,
    semilla: int = SEMILLA_MESA,
    max_iteraciones: int = 12,
    tolerancia: float = TOLERANCIA_EXPLOTABILIDAD,
    directorio_cache: str | None = "resultados/cache",
    informar: Callable[[str], None] | None = None,
) -> MesaTrasMus:
    """Itera política de descarte ↔ equity de la mesa hasta un (ε-)punto fijo.

    1. Política inicial: la mejor respuesta a la equity del reparto inicial (la de la 3a).
    2. Con la política se simula la ronda completa y se obtiene la tabla de
       equity tras el mus. Todas las vueltas usan la misma semilla (números
       aleatorios comunes): así el ruido no hace cambiar decisiones de una
       vuelta a otra.
    3. Se mide la **explotabilidad media**: cuánto ganaría de media por mano
       un jugador que se desviara de forma óptima (ponderado por la
       probabilidad de cada mano). Si es menor que ``tolerancia``, se para.
    4. Si no, se actualiza la política hacia la mejor respuesta. Si esta
       vuelve a una política ya vista (ciclo), se amortigua: se mezcla con la
       anterior con un peso que se reduce a la mitad en cada nuevo ciclo.

    Por qué no se exige que la ganancia sea pequeña en *todas* las manos: en
    manos rarísimas (P ≈ 0,0002) el valor de tirar las cuatro depende de manos
    finales que apenas salen en la simulación, y su ruido mantiene una
    ganancia máxima espuria de ~0,01 aunque la política ya no cambie en nada
    que importe. Por la misma razón no se exige que la mejor respuesta
    coincida con la política: con decisiones en el filo entre dos opciones casi
    iguales, el equilibrio es mixto y la iteración oscilaría sin fin.
    """
    td = construir_tabla_descartes(reglas)
    p0 = td.tabla.probabilidad
    decir = informar or (lambda _: None)
    tabla_inicial = (calcular_tabla_equity(reglas) if directorio_cache is None
                     else cargar_tabla_equity(reglas, directorio_cache))
    politica = mejor_respuesta(td, tabla_inicial, objetivo)
    decir(f"Política inicial: mejor respuesta a la equity del reparto inicial (3a). "
          f"{simulaciones} rondas simuladas por vuelta.")
    alfa = 1.0
    historia: list[Iteracion] = []
    vistas: list[np.ndarray] = [politica.principal]
    convergio = False
    for numero in range(1, max_iteraciones + 1):
        eq = _equity_de_politica(politica, simulaciones, semilla, tabla_inicial,
                                 directorio_cache)
        respuesta = mejor_respuesta(td, eq.tabla, objetivo)
        cambios = politica.cambios(respuesta)
        ganancia = ganancia_por_desviarse(politica, eq.tabla, objetivo)
        ponderados = float((cambios * p0[None, :]).sum() / len(POSICIONES))
        media = float((ganancia * p0[None, :]).sum() / len(POSICIONES))
        historia.append(Iteracion(numero, int(cambios.sum()), ponderados,
                                  politica.diferencia(respuesta), float(ganancia.max()), media,
                                  alfa))
        decir(f"Vuelta {numero}: {int(cambios.sum())} decisiones cambian "
              f"({100 * ponderados:.2f} % de los repartos); ganancia por desviarse: "
              f"media {media:.5f}, máxima {ganancia.max():.4f}"
              + (f"; amortiguación {alfa:g}" if alfa < 1 else ""))
        if media < tolerancia:
            convergio = True
            break
        if any(np.array_equal(respuesta.principal, v) for v in vistas[:-1]):
            alfa /= 2
            decir(f"  Ciclo detectado: se amortigua con peso {alfa:g}.")
        vistas.append(respuesta.principal)
        politica = politica.mezclar(respuesta, alfa)
    else:
        eq = _equity_de_politica(politica, simulaciones, semilla, tabla_inicial,
                                 directorio_cache)
    return MesaTrasMus(reglas, objetivo, politica, marginales(politica), eq, tabla_inicial,
                       tuple(historia), convergio, simulaciones, semilla)


# --- Verificación: tabla simulada frente a una simulación independiente ---------------


def _media(suma: float, suma_cuadrados: float, n: int, confianza: float) -> EstimacionMedia:
    media = suma / n
    varianza = max(suma_cuadrados / n - media * media, 0.0) * n / (n - 1)
    return EstimacionMedia(media, float(np.sqrt(varianza)), n, confianza)


@dataclass(frozen=True)
class ComparacionMesa:
    """Una magnitud agregada de mesa: lo que predice la tabla frente a lo simulado."""

    asiento: int
    lance: Lance | None  # None = total de los cinco lances
    metrica: str
    prediccion: float
    simulado: Estimacion | EstimacionMedia

    @property
    def dentro(self) -> bool:
        return self.simulado.contiene(self.prediccion)


@dataclass(frozen=True)
class ErrorPorMano:
    """Diferencia, mano a mano, en los tantos netos totales de un asiento."""

    asiento: int
    manos_comparadas: int
    error_medio: float
    error_maximo: float
    mano_error_maximo: str
    fuera_del_intervalo: int
    """Manos cuya diferencia supera el IC combinado de las dos estimaciones."""


@dataclass(frozen=True)
class InformeVerificacion:
    n: int
    chi2_marginales: tuple[tuple[float, int], ...]
    """(χ², grados de libertad) de las manos finales simuladas frente a la marginal exacta."""
    agregadas: tuple[ComparacionMesa, ...]
    por_mano: tuple[ErrorPorMano, ...]


def verificar_mesa(mesa: MesaTrasMus, sim: SimulacionMesa, confianza: float = 0.999,
                   min_muestras: int = 5000) -> InformeVerificacion:
    """Compara la mesa calculada con una simulación **independiente** (otra semilla).

    - Marginales: deben coincidir dentro del error estadístico (son exactas).
    - Magnitudes de mesa: la tabla simulada, ponderada con las marginales
      exactas, debe reproducir la simulación independiente.
    - Mano a mano: las dos estimaciones de los tantos de cada mano final deben
      coincidir dentro de su error combinado.
    """
    n = sim.n
    tabla = mesa.tabla.tabla
    chi2 = []
    for s in range(JUGADORES):
        esperadas = n * mesa.marginales[s]
        soporte = esperadas > 0
        chi2.append((float(((sim.frecuencias[s, soporte] - esperadas[soporte]) ** 2
                              / esperadas[soporte]).sum()), int(soporte.sum() - 1)))

    agregadas = []
    for s in range(JUGADORES):
        q = mesa.marginales[s]
        for l, lance in enumerate(LANCES):
            for metrica, modelo, simulado in (
                ("gana él", mesa.tabla.gana_individual, sim.gana_individual),
                ("gana su pareja", mesa.tabla.gana_pareja, sim.gana_pareja),
                ("se juega", mesa.tabla.se_juega, sim.se_juega),
            ):
                agregadas.append(ComparacionMesa(
                    s + 1, lance, metrica, float(q @ modelo[:, s, l]),
                    Estimacion(int(round(simulado[s, :, l].sum())), n, confianza)))
            agregadas.append(ComparacionMesa(
                s + 1, lance, "tantos netos", float(q @ mesa.tabla.tantos_netos[:, s, l]),
                _media(sim.tantos[s, :, l].sum(), sim.tantos_cuadrado[s, :, l].sum(), n,
                       confianza)))
        agregadas.append(ComparacionMesa(
            s + 1, None, "tantos netos", float(q @ mesa.tabla.tantos_netos[:, s, :].sum(axis=1)),
            _media(sim.tantos_total[s].sum(), sim.tantos_total_cuadrado[s].sum(), n, confianza)))

    z = NormalDist().inv_cdf(0.5 + confianza / 2)
    por_mano = []
    for s in range(JUGADORES):
        prediccion = mesa.tabla.tantos_netos[:, s, :].sum(axis=1)
        frecuentes = np.nonzero((sim.frecuencias[s] >= min_muestras)
                                & (mesa.equity.muestras[:, s] >= min_muestras))[0]
        if len(frecuentes) == 0:  # simulación demasiado corta para comparar mano a mano
            por_mano.append(ErrorPorMano(s + 1, 0, float("nan"), float("nan"), "-", 0))
            continue
        errores, pesos, fuera = [], [], 0
        for h in frecuentes:
            c = int(sim.frecuencias[s, h])
            e = _media(sim.tantos_total[s, h], sim.tantos_total_cuadrado[s, h], c, confianza)
            error_combinado = np.hypot(e.desviacion / np.sqrt(c), mesa.equity.error_tantos[h, s])
            diferencia = abs(prediccion[h] - e.media)
            errores.append(diferencia)
            pesos.append(c)
            fuera += diferencia > z * error_combinado
        errores_a = np.array(errores)
        peor = int(frecuentes[errores_a.argmax()])
        por_mano.append(ErrorPorMano(
            s + 1, len(frecuentes), float(np.average(errores_a, weights=pesos)),
            float(errores_a.max()), tabla.manos[peor].texto(tabla.baraja), fuera))
    return InformeVerificacion(n, tuple(chi2), tuple(agregadas), tuple(por_mano))


# --- Valoración de las opciones de una mano concreta -----------------------------------


@dataclass(frozen=True)
class OpcionSimulada:
    """Valor simulado de una forma de descartarse con la mano y posición fijas."""

    opcion: OpcionDescarte
    tantos: EstimacionMedia
    """Tantos netos totales en paso de mi pareja (todos los lances)."""
    tantos_por_lance: tuple[float, ...]
    diferencia_con_la_mejor: EstimacionMedia
    """(esta − la mejor) reparto a reparto: con números aleatorios comunes, su
    IC es mucho más estrecho que el de cada valor por separado."""


def valorar_opciones_simuladas(
    mano: Mano | str, posicion: int, politica: Politica, n: int,
    semilla: int | None = None, confianza: float = 0.95, tamano_lote: int = TAMANO_LOTE,
) -> list[OpcionSimulada]:
    """Valora cada forma de descartarse simulando la ronda con mi mano fija.

    Los otros tres asientos reciben sus manos de las 36 cartas restantes y se
    descartan con ``politica``; yo pruebo cada opción sobre **los mismos**
    repartos. Incluye todo lo que la tabla por mano final no recoge: mis
    propios descartes salen del juego y la conjunta de los rivales es la real.
    """
    td = politica.td
    tabla = td.tabla
    op = _opciones_densas(td)
    if isinstance(mano, str):
        mano = parsear_mano(mano, tabla.reglas)
    heroe = tabla.indice(mano)
    opciones = td.opciones[heroe]
    potencias = potencias_codigo(tabla.baraja)
    restantes = np.array(tabla.baraja.copias) - tabla.conteos[heroe]
    mazo = np.repeat(np.arange(tabla.baraja.n_rangos), restantes).astype(np.int8)
    otros = [s for s in POSICIONES if s != posicion]
    acumuladas = np.cumsum(politica.probabilidades, axis=2)
    rng = generador(semilla)
    netos = np.zeros((len(opciones), n))
    por_lance = np.zeros((len(opciones), len(LANCES)))

    hechos = 0
    while hechos < n:
        m = min(tamano_lote, n - hechos)
        filas = np.arange(m)
        barajado = rng.permuted(np.tile(mazo, (m, 1)), axis=1)
        iniciales = tabla.indices_de_codigos(
            potencias[barajado[:, :12]].reshape(m, 3, CARTAS_POR_MANO).sum(axis=2))
        robo = np.zeros((m, 25), dtype=np.int64)
        np.cumsum(potencias[barajado[:, 12:]], axis=1, out=robo[:, 1:])
        eleccion = {}
        for j, s in enumerate(otros):  # los demás eligen una vez: igual para todas mis opciones
            h = iniciales[:, j]
            eleccion[s] = (h, _elegir(acumuladas[s - 1], op.valida, h, rng.random(m)))
        for i, opcion in enumerate(opciones):
            inicio = np.zeros(m, dtype=np.int64)
            finales = np.empty((m, JUGADORES), dtype=np.int64)
            for s in POSICIONES:
                if s == posicion:
                    conservadas = int(np.array(opcion.conservadas) @ potencias)
                    k = np.full(m, opcion.n_descartes)
                else:
                    h, o = eleccion[s]
                    conservadas, k = op.codigo_conservadas[h, o], op.n_descartes[h, o]
                robado = robo[filas, inicio + k] - robo[filas, inicio]
                finales[:, s - 1] = tabla.indices_de_codigos(conservadas + robado)
                inicio += k
            total = np.zeros(m)
            for l, lance in enumerate(LANCES):
                g = ganadores_lance(tabla, finales, lance)
                t = tantos_lance(tabla, finales, lance, g)
                mia = (g > 0) & ((g % 2 == 1) == (posicion % 2 == 1))
                neto = np.where(mia, t, np.where(g > 0, -t, 0))
                por_lance[i, l] += neto.sum()
                total += neto
            netos[i, hechos:hechos + m] = total
        hechos += m

    medias = netos.mean(axis=1)
    mejor = int(medias.argmax())
    resultado = [
        OpcionSimulada(o, EstimacionMedia.de_muestra(netos[i], confianza),
                       tuple(por_lance[i] / n),
                       EstimacionMedia.de_muestra(netos[i] - netos[mejor], confianza))
        for i, o in enumerate(opciones)
    ]
    resultado.sort(key=lambda r: -r.tantos.media)
    return resultado
