"""Fase 3c: cortar o dar mus, con el efecto de selección.

Reglas (confirmadas): se habla en orden desde la mano y basta con que uno
corte; si nadie corta, los cuatro se descartan (al menos una carta) y se
juegan los lances. Simplificaciones: una sola ronda de mus, tantos en paso
(sin envites) y sin comunicación entre compañeros.

Modelo. Una política de corte da, para cada asiento s y mano h, la
probabilidad κ_s(h) de cortar si le toca hablar. Como en paso los tantos solo
dependen de las cartas, para el asiento s (los anteriores han dado mus):

- **cortar** vale T_ini: los tantos jugando con las manos tal como se repartieron;
- **dar mus** vale w·T_mus + (1 − w)·T_ini, donde w = Π_{k>s} (1 − κ_k(h_k)) es
  la probabilidad de que todos los que hablan después den mus: si alguno
  corta, se juega con las manos iniciales, corte quien corte.

El **efecto de selección** entra de dos formas, ambas como pesos de
importancia en una misma simulación (en lugar de tirar repartos):

1. a la decisión de s solo se llega si los anteriores dieron mus: el reparto
   pesa Π_{k<s} (1 − κ_k(h_k));
2. las manos que llegan al descarte son las de los repartos en que dan mus
   los cuatro: la tabla de equity tras el mus se pondera por Π_k (1 − κ_k(h_k)).

Corte y descarte se ajustan a la vez hasta un punto fijo (como en la 3b).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from mus.cartas import CARTAS_POR_MANO, Mano, parsear_mano
from mus.condiciones import Condicion
from mus.descarte import OBJETIVOS, Objetivo, OpcionDescarte, construir_tabla_descartes
from mus.equity import POSICIONES, TablaEquity, calcular_tabla_equity, cargar_tabla_equity
from mus.evaluacion import JUGADORES
from mus.reglas import REGLAS_POR_DEFECTO, ReglasMus
from mus.simulacion import EstimacionMedia, generador
from mus.tablas import potencias_codigo
from mus.tras_mus import (
    TOLERANCIA_EXPLOTABILIDAD,
    EquitySimulada,
    Politica,
    SimulacionMesa,
    _Acumulador,
    _elegir,
    _opciones_densas,
    _repartir_y_descartar,
    equity_simulada,
    ganancia_por_desviarse,
    mejor_respuesta,
    tantos_netos_por_asiento,
)

SIMULACIONES_POR_VUELTA = 4_000_000
SEMILLA_CORTE = 20261007
VERSION_SIMULACION = "2"
TAMANO_LOTE_CORTE = 100_000


def _pesos_lance(objetivo: Objetivo) -> tuple[float, ...]:
    if objetivo.metrica != "tantos":
        raise ValueError("Cortar o dar mus se decide con tantos: usa un objetivo de tantos")
    return objetivo.pesos


# --- Política de corte -----------------------------------------------------------


@dataclass(frozen=True, eq=False)
class PoliticaCorte:
    """``probabilidades[s − 1, h]`` = P(el asiento s corta con la mano h | le toca hablar)."""

    probabilidades: np.ndarray

    @classmethod
    def nunca(cls, n_manos: int) -> PoliticaCorte:
        """Todos dan mus siempre (la situación de la 3b)."""
        return cls(np.zeros((JUGADORES, n_manos)))

    def mezclar(self, otra: PoliticaCorte, alfa: float) -> PoliticaCorte:
        return PoliticaCorte((1 - alfa) * self.probabilidades + alfa * otra.probabilidades)

    def principal(self) -> np.ndarray:
        """(4, manos) True donde lo más probable es cortar."""
        return self.probabilidades > 0.5

    def huella(self) -> str:
        return hashlib.sha256(np.ascontiguousarray(self.probabilidades).tobytes()).hexdigest()

    def no_cortan(self, iniciales: np.ndarray) -> np.ndarray:
        """(m, 4) probabilidad de que cada asiento dé mus con su mano inicial."""
        return 1 - self.probabilidades[np.arange(JUGADORES)[None, :], iniciales]


# --- Simulación de la mesa con corte ------------------------------------------------


@dataclass(frozen=True, eq=False)
class SimulacionCorte:
    """Acumulados de la simulación con corte, por (asiento, mano inicial).

    Con alcance = Π_{k<s} (1 − κ_k) (peso de llegar a hablar) y la ventaja del
    mus por reparto d = Π_{k>s} (1 − κ_k)·(T_mus − T_ini):

    Atributos:
        alcance, alcance_cuadrado: Σ alcance y Σ alcance².
        cortar, cortar_cuadrado: Σ alcance·T_ini y Σ alcance·T_ini².
        ventaja, ventaja_cuadrado: Σ alcance·d y Σ alcance·d².
        hay_mus_por_mano: Σ P(dan mus los cuatro), por asiento y mano inicial: con
            /n, la probabilidad de tener esa mano y llegar a descartarse.
        mesa: acumulados por mano final ponderados por P(dan mus los cuatro).
        hay_mus: Σ P(dan mus los cuatro).
        valor_pareja_mano: Σ tantos netos de la pareja 1-3 con el protocolo completo.
    """

    n: int
    alcance: np.ndarray
    alcance_cuadrado: np.ndarray
    cortar: np.ndarray
    cortar_cuadrado: np.ndarray
    ventaja: np.ndarray
    ventaja_cuadrado: np.ndarray
    hay_mus_por_mano: np.ndarray
    mesa: SimulacionMesa = field(repr=False)
    hay_mus: float
    valor_pareja_mano: float

    def _media(self, suma: np.ndarray, cuadrado: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Media ponderada y su error típico, con el tamaño efectivo de Kish
        n_ef = (Σw)² / Σw² (infinito si no hay muestras)."""
        con_muestras = self.alcance > 0
        w = np.where(con_muestras, self.alcance, 1.0)
        media = suma / w
        varianza = np.maximum(cuadrado / w - media ** 2, 0)
        n_efectivo = self.alcance ** 2 / np.where(con_muestras, self.alcance_cuadrado, 1.0)
        error = np.where(n_efectivo > 1, np.sqrt(varianza / np.maximum(n_efectivo, 1)), np.inf)
        return media, error

    def valor_cortar(self) -> tuple[np.ndarray, np.ndarray]:
        """(4, manos) valor de cortar y su error típico."""
        return self._media(self.cortar, self.cortar_cuadrado)

    def ventaja_mus(self) -> tuple[np.ndarray, np.ndarray]:
        """(4, manos) valor de dar mus menos el de cortar, y su error típico."""
        return self._media(self.ventaja, self.ventaja_cuadrado)


_CAMPOS = ("alcance", "alcance_cuadrado", "cortar", "cortar_cuadrado", "ventaja",
           "ventaja_cuadrado", "hay_mus_por_mano")
_CAMPOS_MESA = ("frecuencias", "gana_individual", "gana_pareja", "se_juega", "tantos",
                "tantos_cuadrado", "tantos_total", "tantos_total_cuadrado", "cartas_pedidas")


def simular_corte(corte: PoliticaCorte, descarte: Politica, n: int, semilla: int | None = None,
                  objetivo: Objetivo = OBJETIVOS["tantos"],
                  tamano_lote: int = TAMANO_LOTE_CORTE) -> SimulacionCorte:
    """Simula ``n`` repartos y acumula, para cada asiento y mano inicial, el valor
    de cortar y la ventaja de dar mus, con los pesos de selección."""
    tabla = descarte.td.tabla
    pesos_lance = _pesos_lance(objetivo)
    rng = generador(semilla)
    acumulador = _Acumulador(tabla)
    nm = tabla.n_manos
    acum = {k: np.zeros((JUGADORES, nm)) for k in _CAMPOS}
    hay_mus = valor_mano = 0.0
    hechos = 0
    while hechos < n:
        m = min(tamano_lote, n - hechos)
        hechos += m
        iniciales, finales, pedidas = _repartir_y_descartar(descarte, m, rng)
        dan_mus = corte.no_cortan(iniciales)                    # (m, 4)
        todos = dan_mus.prod(axis=1)
        t_ini = tantos_netos_por_asiento(tabla, iniciales, pesos_lance)
        t_mus = acumulador.sumar(finales, pedidas, pesos=todos, pesos_lance=pesos_lance)
        hay_mus += todos.sum()
        valor_mano += (todos * t_mus[:, 0] + (1 - todos) * t_ini[:, 0]).sum()
        for s in range(JUGADORES):
            alcance = dan_mus[:, :s].prod(axis=1)
            despues = dan_mus[:, s + 1:].prod(axis=1)
            d = despues * (t_mus[:, s] - t_ini[:, s])
            h = iniciales[:, s]
            for clave, valores in (("alcance", alcance), ("alcance_cuadrado", alcance ** 2),
                                   ("cortar", alcance * t_ini[:, s]),
                                   ("cortar_cuadrado", alcance * t_ini[:, s] ** 2),
                                   ("ventaja", alcance * d), ("ventaja_cuadrado", alcance * d * d),
                                   ("hay_mus_por_mano", todos)):
                acum[clave][s] += np.bincount(h, weights=valores, minlength=nm)
    return SimulacionCorte(n, **acum, mesa=acumulador.resultado(), hay_mus=hay_mus,
                           valor_pareja_mano=valor_mano)


def _guardar(sim: SimulacionCorte, ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = {k: getattr(sim, k) for k in _CAMPOS}
    datos |= {f"mesa_{k}": getattr(sim.mesa, k) for k in _CAMPOS_MESA}
    np.savez_compressed(ruta, n=sim.n, hay_mus=sim.hay_mus, valor=sim.valor_pareja_mano,
                        **datos)


def _cargar(ruta: Path) -> SimulacionCorte:
    with np.load(ruta) as f:
        mesa = SimulacionMesa(int(f["n"]), *(f[f"mesa_{k}"] for k in _CAMPOS_MESA))
        return SimulacionCorte(int(f["n"]), *(f[k] for k in _CAMPOS), mesa=mesa,
                               hay_mus=float(f["hay_mus"]), valor_pareja_mano=float(f["valor"]))


def _simulacion_cacheada(corte: PoliticaCorte, descarte: Politica, n: int, semilla: int,
                         objetivo: Objetivo, directorio: str | None) -> SimulacionCorte:
    if directorio is None:
        return simular_corte(corte, descarte, n, semilla, objetivo)
    texto = (f"{descarte.td.tabla.reglas!r}|{VERSION_SIMULACION}|{n}|{semilla}|"
             f"{objetivo.pesos}|{corte.huella()}|{descarte.huella()}")
    ruta = Path(directorio) / f"corte_{hashlib.sha256(texto.encode()).hexdigest()[:16]}.npz"
    if ruta.exists():
        return _cargar(ruta)
    sim = simular_corte(corte, descarte, n, semilla, objetivo)
    _guardar(sim, ruta)
    return sim


# --- Iteración conjunta corte ↔ descarte --------------------------------------------


@dataclass(frozen=True)
class IteracionCorte:
    """Resumen de una vuelta de :func:`iterar_corte`.

    Las explotabilidades son **por reparto**: lo que ganaría de media por mano
    jugada un jugador que se desviara de forma óptima, ponderando cada decisión
    por la probabilidad de llegar a tomarla (hablar, para el corte; que haya
    mus, para el descarte). Así, el ruido en decisiones que casi nunca se toman
    no cuenta.
    """

    numero: int
    cambios_corte: int
    explotabilidad_corte: float
    """Solo con las ganancias estadísticamente significativas (|ventaja| > 2 errores típicos)."""
    explotabilidad_corte_bruta: float
    """Con todas las ganancias, incluidas las que son ruido de la simulación."""
    cambios_descarte: int
    explotabilidad_descarte: float
    amortiguacion: float
    hay_mus: float


@dataclass(frozen=True, eq=False)
class MesaConCorte:
    """Resultado de :func:`iterar_corte`."""

    reglas: ReglasMus
    objetivo: Objetivo
    corte: PoliticaCorte
    descarte: Politica
    simulacion: SimulacionCorte
    equity: EquitySimulada
    """Equity de cada mano final tras el mus, en los repartos en que hay mus."""
    tabla_inicial: TablaEquity
    historia: tuple[IteracionCorte, ...]
    convergio: bool
    simulaciones: int
    semilla: int
    escenario: str = "equilibrio"

    @property
    def p_hay_mus(self) -> float:
        return self.simulacion.hay_mus / self.simulacion.n

    def p_cortar(self, posicion: int) -> float:
        """P(el asiento corta | le toca hablar), ponderada por la frecuencia con que habla
        con cada mano."""
        alcance = self.simulacion.alcance[posicion - 1]
        return float(alcance @ self.corte.probabilidades[posicion - 1] / alcance.sum())

    def p_habla(self, posicion: int) -> float:
        """P(le toca hablar a ese asiento): todos los anteriores han dado mus."""
        return float(self.simulacion.alcance[posicion - 1].sum() / self.simulacion.n)


def _ganancia_corte(corte: PoliticaCorte, ventaja: np.ndarray) -> np.ndarray:
    """(4, manos) lo que se ganaría cambiando a la mejor decisión de corte.

    Si dar mus es mejor (ventaja > 0), se pierde ventaja·P(cortar); si no, −ventaja·P(mus).
    """
    k = corte.probabilidades
    return np.where(ventaja > 0, k * ventaja, (1 - k) * -ventaja)


def iterar_corte(
    reglas: ReglasMus = REGLAS_POR_DEFECTO,
    objetivo: Objetivo = OBJETIVOS["tantos"],
    *,
    simulaciones: int = SIMULACIONES_POR_VUELTA,
    semilla: int = SEMILLA_CORTE,
    max_iteraciones: int = 40,
    tolerancia: float = TOLERANCIA_EXPLOTABILIDAD,
    directorio_cache: str | None = "resultados/cache",
    informar: Callable[[str], None] | None = None,
) -> MesaConCorte:
    """Ajusta a la vez la política de corte y la de descarte hasta un ε-equilibrio.

    Parte de "todos dan mus" con la política de descarte de la 3a. En cada
    vuelta, una simulación da (a) la tabla de equity tras el mus en los repartos
    en que hay mus, de la que sale la mejor respuesta de descarte, y (b) para
    cada asiento y mano, el valor de cortar y la ventaja de dar mus, de los que
    sale la mejor respuesta de corte.

    Amortiguación: la política nueva se mezcla con la anterior con peso
    1/(t + 1) en la vuelta t (*fictitious play*). Sin amortiguar, la iteración
    oscila sin converger: las dos parejas tienen intereses opuestos (la ronda
    de mus favorece de media a la pareja de la mano, así que la otra corta
    mucho, lo que cambia qué manos llegan al mus, y así sucesivamente). En
    juegos de suma cero entre dos jugadores, el promedio de mejores respuestas
    converge al equilibrio.

    Se para cuando la explotabilidad por reparto de las dos decisiones es
    menor que ``tolerancia`` (ver :class:`IteracionCorte`).
    """
    _pesos_lance(objetivo)
    td = construir_tabla_descartes(reglas)
    decir = informar or (lambda _: None)
    tabla_inicial = (calcular_tabla_equity(reglas) if directorio_cache is None
                     else cargar_tabla_equity(reglas, directorio_cache))
    corte = PoliticaCorte.nunca(td.tabla.n_manos)
    descarte = mejor_respuesta(td, tabla_inicial, objetivo)
    decir(f"Inicio: todos dan mus; descarte de la 3a. {simulaciones} repartos por vuelta; "
          "amortiguación 1/(t+1).")
    historia: list[IteracionCorte] = []
    convergio = False
    for numero in range(1, max_iteraciones + 1):
        sim = _simulacion_cacheada(corte, descarte, simulaciones, semilla, objetivo,
                                   directorio_cache)
        eq = equity_simulada(sim.mesa, tabla_inicial)
        ventaja, error = sim.ventaja_mus()
        respuesta_corte = PoliticaCorte((ventaja < 0).astype(np.float64))
        respuesta_descarte = mejor_respuesta(td, eq.tabla, objetivo)
        # Explotabilidad por reparto: ganancia × P(tener la mano y llegar a decidir).
        # En manos casi indiferentes, el signo de la ventaja es ruido de la
        # simulación: solo cuentan las ganancias significativas.
        ganancia = _ganancia_corte(corte, ventaja) * sim.alcance / sim.n
        e_corte_bruta = float(ganancia.sum())
        e_corte = float(ganancia[np.abs(ventaja) > 2 * error].sum())
        g_desc = ganancia_por_desviarse(descarte, eq.tabla, objetivo)
        g_desc = np.where(np.isfinite(g_desc), g_desc, 0.0)
        e_desc = float((g_desc * sim.hay_mus_por_mano).sum() / sim.n)
        cambios_corte = int((corte.principal() != respuesta_corte.principal()).sum())
        cambios_desc = int(descarte.cambios(respuesta_descarte).sum())
        alfa = 1 / (numero + 1)
        historia.append(IteracionCorte(numero, cambios_corte, e_corte, e_corte_bruta,
                                       cambios_desc, e_desc, alfa, sim.hay_mus / sim.n))
        decir(f"Vuelta {numero}: P(hay mus) {sim.hay_mus / sim.n:.3f}; explotabilidad por "
              f"reparto: corte {e_corte:.4f} (bruta {e_corte_bruta:.4f}; {cambios_corte} "
              f"cambios), descarte {e_desc:.4f} ({cambios_desc} cambios)")
        if e_corte < tolerancia and e_desc < tolerancia:
            convergio = True
            break
        corte = corte.mezclar(respuesta_corte, alfa)
        descarte = descarte.mezclar(respuesta_descarte, alfa)
    else:
        sim = _simulacion_cacheada(corte, descarte, simulaciones, semilla, objetivo,
                                   directorio_cache)
        eq = equity_simulada(sim.mesa, tabla_inicial)
    return MesaConCorte(reglas, objetivo, corte, descarte, sim, eq, tabla_inicial,
                        tuple(historia), convergio, simulaciones, semilla)


def mesa_rivales_razonables(
    reglas: ReglasMus = REGLAS_POR_DEFECTO,
    objetivo: Objetivo = OBJETIVOS["tantos"],
    *,
    simulaciones: int = SIMULACIONES_POR_VUELTA,
    semilla: int = SEMILLA_CORTE,
    directorio_cache: str | None = "resultados/cache",
    factor_corte: float = 1.0,
) -> MesaConCorte:
    """Escenario de "rivales razonables" (razonamiento de nivel 1).

    Cada jugador corta si, suponiendo que todos los demás dan mus, cortar le
    sale mejor; y se descarta con el equilibrio de la 3b (sin selección). Es
    como razona un jugador que no anticipa que los demás también cortan. Quien
    use esta mesa para decidir (:func:`valorar_corte`) responde de forma óptima
    a esos rivales, con el efecto de selección completo.

    ``factor_corte`` (λ) escala la probabilidad de corte de los demás: λ = 0
    es "nadie corta" (la 3b) y λ = 1 los rivales razonables. Las decisiones
    dudosas dependen de cuánto se corta en la mesa (ver docs/decisiones.md).

    Motivo del escenario: el equilibrio de :func:`iterar_corte` es degenerado
    en este modelo (casi nunca hay mus), lo que no se parece a la mesa real.
    """
    if not 0 <= factor_corte <= 1:
        raise ValueError("factor_corte debe estar entre 0 y 1")
    from mus.tras_mus import iterar_tras_mus

    tabla_inicial = (calcular_tabla_equity(reglas) if directorio_cache is None
                     else cargar_tabla_equity(reglas, directorio_cache))
    descarte = iterar_tras_mus(reglas, objetivo, directorio_cache=directorio_cache).politica
    sin_cortes = _simulacion_cacheada(PoliticaCorte.nunca(tabla_inicial.tabla.n_manos), descarte,
                                      simulaciones, semilla, objetivo, directorio_cache)
    ventaja, _ = sin_cortes.ventaja_mus()
    corte = PoliticaCorte(factor_corte * (ventaja < 0).astype(np.float64))
    sim = _simulacion_cacheada(corte, descarte, simulaciones, semilla, objetivo, directorio_cache)
    nombre = "rivales razonables" + (f" (corte ×{factor_corte:g})" if factor_corte != 1 else "")
    return MesaConCorte(reglas, objetivo, corte, descarte, sim,
                        equity_simulada(sim.mesa, tabla_inicial), tabla_inicial, (), True,
                        simulaciones, semilla, escenario=nombre)


# --- Decisión para una mano concreta ------------------------------------------------


def _media_ponderada(x: np.ndarray, w: np.ndarray, confianza: float) -> EstimacionMedia:
    """Media ponderada con el tamaño efectivo de Kish: n_ef = (Σw)² / Σw²."""
    suma = w.sum()
    media = float((w * x).sum() / suma)
    varianza = float((w * (x - media) ** 2).sum() / suma)
    n_efectivo = max(int(suma ** 2 / (w * w).sum()), 2)
    return EstimacionMedia(media, float(np.sqrt(varianza)), n_efectivo, confianza)


@dataclass(frozen=True)
class OpcionTrasMus:
    opcion: OpcionDescarte
    valor_mus: EstimacionMedia
    """Valor de dar mus y descartarse así (incluye la probabilidad de que otro corte)."""
    frente_a_la_mejor: EstimacionMedia
    si_hay_mus: EstimacionMedia | None = None
    """Tantos esperados si llega a haber mus y me descarto así: solo los repartos
    en que dan mus todos, cada uno con su probabilidad. Es lo que importa en el
    momento de descartarse. ``None`` si nunca llega a haber mus."""
    si_hay_mus_frente_a_la_mejor: EstimacionMedia | None = None
    """Lo mismo, menos el mejor descarte, reparto a reparto. Su media es
    ``frente_a_la_mejor`` dividida por la probabilidad de que den mus los que
    hablan después (ver :class:`DecisionCorte`)."""


@dataclass(frozen=True)
class DecisionCorte:
    """Cortar o dar mus con una mano concreta, simulada con esa mano fija."""

    mano: str
    posicion: int
    informacion: str
    cortar: EstimacionMedia
    mus: EstimacionMedia
    ventaja_mus: EstimacionMedia
    """Dar mus (con el mejor descarte) menos cortar, reparto a reparto."""
    p_mus_despues: float
    """Probabilidad de que den mus todos los que hablan después."""
    opciones: tuple[OpcionTrasMus, ...]

    @property
    def decision(self) -> str:
        """"mus" o "cortar" si el IC de la ventaja excluye el 0; si no, "indiferente":
        con esa precisión, las dos decisiones valen lo mismo (el IC acota cuánto)."""
        bajo, alto = self.ventaja_mus.intervalo
        if bajo > 0:
            return "mus"
        if alto < 0:
            return "cortar"
        return "indiferente"

    @property
    def mejor_descarte(self) -> OpcionDescarte:
        return self.opciones[0].opcion


def valorar_corte(
    mano: Mano | str, posicion: int, mesa: MesaConCorte, n: int, *,
    companero: Condicion | None = None, semilla: int | None = None, confianza: float = 0.95,
    tamano_lote: int = TAMANO_LOTE_CORTE,
) -> DecisionCorte:
    """Cortar o dar mus con ``mano`` en ``posicion``, contra la mesa con corte.

    Los otros tres asientos reciben sus manos de las 36 cartas restantes y
    deciden y se descartan con las políticas de ``mesa``. Los anteriores han
    dado mus (sus repartos pesan por la probabilidad de haberlo dado); los
    posteriores pueden cortar. ``companero`` condiciona además la mano inicial
    del compañero (p. ej. lo que diría si se le pregunta). Todas las opciones de
    descarte se prueban sobre los mismos repartos.
    """
    descarte = mesa.descarte
    td = descarte.td
    tabla = td.tabla
    op = _opciones_densas(td)
    pesos_lance = _pesos_lance(mesa.objetivo)
    if isinstance(mano, str):
        mano = parsear_mano(mano, tabla.reglas)
    heroe = tabla.indice(mano)
    opciones = td.opciones[heroe]
    potencias = potencias_codigo(tabla.baraja)
    restantes = np.array(tabla.baraja.copias) - tabla.conteos[heroe]
    mazo = np.repeat(np.arange(tabla.baraja.n_rangos), restantes).astype(np.int8)
    otros = [s for s in POSICIONES if s != posicion]
    acumuladas = np.cumsum(descarte.probabilidades, axis=2)
    mascara_companero = None if companero is None else companero.mascara(tabla)
    companero_asiento = (posicion + 1) % JUGADORES + 1
    rng = generador(semilla)
    pesos, t_ini_todos, despues_todos = [], [], []
    t_mus = [[] for _ in opciones]

    hechos = 0
    while hechos < n:
        m = min(tamano_lote, n - hechos)
        hechos += m
        filas = np.arange(m)
        barajado = rng.permuted(np.tile(mazo, (m, 1)), axis=1)
        iniciales = np.empty((m, JUGADORES), dtype=np.int64)
        iniciales[:, posicion - 1] = heroe
        iniciales[:, [s - 1 for s in otros]] = tabla.indices_de_codigos(
            potencias[barajado[:, :12]].reshape(m, 3, CARTAS_POR_MANO).sum(axis=2))
        robo = np.zeros((m, 25), dtype=np.int64)
        np.cumsum(potencias[barajado[:, 12:]], axis=1, out=robo[:, 1:])
        dan_mus = mesa.corte.no_cortan(iniciales)
        alcance = dan_mus[:, :posicion - 1].prod(axis=1)
        if mascara_companero is not None:
            alcance = alcance * mascara_companero[iniciales[:, companero_asiento - 1]]
        despues = dan_mus[:, posicion:].prod(axis=1)
        eleccion = {s: _elegir(acumuladas[s - 1], op.valida, iniciales[:, s - 1], rng.random(m))
                    for s in otros}
        pesos.append(alcance)
        despues_todos.append(despues)
        t_ini_todos.append(tantos_netos_por_asiento(tabla, iniciales, pesos_lance)[:, posicion - 1])
        for i, opcion in enumerate(opciones):
            inicio = np.zeros(m, dtype=np.int64)
            finales = np.empty((m, JUGADORES), dtype=np.int64)
            for s in POSICIONES:
                if s == posicion:
                    conservadas = int(np.array(opcion.conservadas) @ potencias)
                    k = np.full(m, opcion.n_descartes)
                else:
                    h, o = iniciales[:, s - 1], eleccion[s]
                    conservadas, k = op.codigo_conservadas[h, o], op.n_descartes[h, o]
                robado = robo[filas, inicio + k] - robo[filas, inicio]
                finales[:, s - 1] = tabla.indices_de_codigos(conservadas + robado)
                inicio += k
            t_mus[i].append(tantos_netos_por_asiento(tabla, finales, pesos_lance)[:, posicion - 1])

    w = np.concatenate(pesos)
    if w.sum() == 0:
        raise ValueError("Con estas políticas (y condición), nunca se llega a esa decisión")
    despues = np.concatenate(despues_todos)
    t_ini = np.concatenate(t_ini_todos)
    t_mus_todos = [np.concatenate(t) for t in t_mus]
    valores = [despues * t + (1 - despues) * t_ini for t in t_mus_todos]
    medias = [float((w * v).sum() / w.sum()) for v in valores]
    mejor = int(np.argmax(medias))
    # Si llega a haber mus, cada reparto pesa por la probabilidad de llegar a
    # hablar y de que den mus todos los que hablan después. El mejor descarte
    # es el mismo: valores_i solo depende de la opción a través de despues·T_mus.
    w_mus = w * despues
    hay_mus = w_mus.sum() > 0

    def si_hay_mus(x: np.ndarray) -> EstimacionMedia | None:
        return _media_ponderada(x, w_mus, confianza) if hay_mus else None

    opciones_valoradas = sorted(
        (OpcionTrasMus(o, _media_ponderada(valores[i], w, confianza),
                       _media_ponderada(valores[i] - valores[mejor], w, confianza),
                       si_hay_mus(t_mus_todos[i]),
                       si_hay_mus(t_mus_todos[i] - t_mus_todos[mejor]))
         for i, o in enumerate(opciones)),
        key=lambda x: -x.valor_mus.media)
    informacion = "sin información" if companero is None else f"compañero: {companero}"
    return DecisionCorte(
        mano.texto(tabla.baraja), posicion, informacion,
        _media_ponderada(t_ini, w, confianza),
        _media_ponderada(valores[mejor], w, confianza),
        _media_ponderada(valores[mejor] - t_ini, w, confianza),
        float((w * despues).sum() / w.sum()),
        tuple(opciones_valoradas),
    )
