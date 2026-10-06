"""Fase 3a: descarte de una mano aislada.

Para una mano se enumeran todas las formas distintas de descartarse (los
sub-multiconjuntos que se conservan; con rangos repetidos hay menos de 15) y,
para cada una, la distribución **exacta** de la mano resultante.

Por qué se roba "de las 36 cartas que no veo": se roba del mazo (24 cartas),
pero desde el punto de vista del jugador ese mazo es un subconjunto uniforme
de las 36 cartas que no tiene, sea lo que sea lo que tengan o hagan los demás.
La probabilidad de robar el multiconjunto D es una hipergeométrica
multivariante: ∏ C(U_r, d_r) / C(36, n), con U = copias − mi mano original
(las cartas que descarto tampoco pueden volver).

Cada mano resultante se valora con una tabla de equity. En esta fase es la de
la Fase 2 (reparto inicial: los rivales no se han descartado); la Fase 3b la
sustituirá por la de la mesa tras el mus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from itertools import combinations_with_replacement, product
from math import comb

import numpy as np

from mus.cartas import CARTAS_POR_MANO, Baraja, Mano, parsear_mano
from mus.equity import TablaEquity
from mus.evaluacion import Lance
from mus.reglas import REGLAS_POR_DEFECTO, ReglasMus
from mus.simulacion import Estimacion, EstimacionMedia, generador, robar
from mus.tablas import TablaManos, construir_tabla, potencias_codigo

LANCES = tuple(Lance)


def texto_conteos(conteos: tuple[int, ...], baraja: Baraja) -> str:
    rangos = [r for r in reversed(range(len(conteos))) for _ in range(conteos[r])]
    return " ".join(baraja.simbolos[r] for r in rangos) or "-"


@dataclass(frozen=True)
class OpcionDescarte:
    """Una forma de descartarse: qué cartas se conservan y cuáles se tiran (conteos)."""

    conservadas: tuple[int, ...]
    descartadas: tuple[int, ...]

    @property
    def n_descartes(self) -> int:
        return sum(self.descartadas)

    def texto(self, baraja: Baraja) -> str:
        return f"me quedo {texto_conteos(self.conservadas, baraja)}, tiro {texto_conteos(self.descartadas, baraja)}"


def opciones_descarte(mano: Mano, reglas: ReglasMus = REGLAS_POR_DEFECTO) -> list[OpcionDescarte]:
    """Formas distintas de descartarse según ``reglas.descarte`` (por defecto, de 1 a 4).

    Ordenadas de menos a más cartas tiradas y, a igualdad, conservando antes
    las cartas más altas.
    """
    minimo, maximo = reglas.descarte.minimo, reglas.descarte.maximo
    opciones = []
    for conservadas in product(*(range(k + 1) for k in mano.conteos)):
        n = CARTAS_POR_MANO - sum(conservadas)
        if minimo <= n <= maximo:
            descartadas = tuple(k - c for k, c in zip(mano.conteos, conservadas))
            opciones.append(OpcionDescarte(tuple(conservadas), descartadas))
    opciones.sort(key=lambda o: (o.n_descartes, tuple(-c for c in reversed(o.conservadas))))
    return opciones


# --- Distribución exacta de la mano resultante --------------------------------


_COMBINATORIOS = np.array([[comb(d, k) for k in range(CARTAS_POR_MANO + 1)] for d in range(9)],
                          dtype=np.float64)
"""``_COMBINATORIOS[d, k] = C(d, k)`` para d ≤ 8 copias y k ≤ 4 cartas."""


@lru_cache(maxsize=None)
def _multiconjuntos(n_rangos: int, n: int) -> np.ndarray:
    """Todos los multiconjuntos de ``n`` cartas como conteos: array (M, rangos)."""
    filas = []
    for combinacion in combinations_with_replacement(range(n_rangos), n):
        fila = [0] * n_rangos
        for r in combinacion:
            fila[r] += 1
        filas.append(fila)
    resultado = np.array(filas, dtype=np.int64).reshape(-1, n_rangos)
    resultado.flags.writeable = False
    return resultado


def distribucion_tras_descarte(tabla: TablaManos, mano: Mano, opcion: OpcionDescarte
                               ) -> np.ndarray:
    """Probabilidad exacta de cada mano final (array con una entrada por mano de la tabla)."""
    no_vistas = np.array(tabla.baraja.copias) - np.array(mano.conteos)
    n = opcion.n_descartes
    robos = _multiconjuntos(tabla.baraja.n_rangos, n)
    # C(no_vistas_r, k_r) para cada robo y rango, con una tabla de combinatorios
    pesos = np.prod(_COMBINATORIOS[no_vistas[None, :], robos], axis=1)
    total = comb(int(no_vistas.sum()), n)
    assert pesos.sum() == total, "los pesos de la hipergeométrica no suman C(36, n)"
    posibles = pesos > 0
    finales = np.array(opcion.conservadas) + robos[posibles]
    indices = tabla.indices_de_codigos(finales @ potencias_codigo(tabla.baraja))
    distribucion = np.zeros(tabla.n_manos)
    np.add.at(distribucion, indices, pesos[posibles] / total)
    return distribucion


@dataclass(frozen=True, eq=False)
class TablaDescartes:
    """Opciones de descarte y distribuciones exactas de todas las manos.

    ``transicion[i]`` es una matriz (opciones de la mano i, manos finales):
    fila o = distribución de la mano final si la mano i se descarta según
    ``opciones[i][o]``.
    """

    tabla: TablaManos
    opciones: tuple[tuple[OpcionDescarte, ...], ...]
    transicion: tuple[np.ndarray, ...]


def construir_tabla_descartes(reglas: ReglasMus = REGLAS_POR_DEFECTO) -> TablaDescartes:
    """Construye (y cachea por reglas) las distribuciones de todas las manos y descartes."""
    return _construir_tabla_descartes(reglas)


@lru_cache(maxsize=None)
def _construir_tabla_descartes(reglas: ReglasMus) -> TablaDescartes:
    tabla = construir_tabla(reglas)
    opciones, transicion = [], []
    for mano in tabla.manos:
        ops = tuple(opciones_descarte(mano, reglas))
        matriz = np.array([distribucion_tras_descarte(tabla, mano, o) for o in ops])
        matriz.flags.writeable = False
        opciones.append(ops)
        transicion.append(matriz)
    return TablaDescartes(tabla, tuple(opciones), tuple(transicion))


# --- Objetivos ---------------------------------------------------------------


@dataclass(frozen=True)
class Objetivo:
    """Qué se quiere maximizar al descartarse.

    El valor de una mano final es Σ_lance peso · métrica[lance], donde la
    métrica es ``"tantos"`` (tantos netos en paso de la pareja),
    ``"individual"`` (P(gano yo el lance)) o ``"pareja"`` (P(gana mi pareja)).
    """

    nombre: str
    metrica: str
    pesos: tuple[float, ...]  # uno por lance, en el orden de Lance

    def __post_init__(self) -> None:
        if self.metrica not in ("tantos", "individual", "pareja"):
            raise ValueError(f"Métrica desconocida: {self.metrica!r}")
        if len(self.pesos) != len(LANCES):
            raise ValueError("Hace falta un peso por lance")

    def valores(self, te: TablaEquity, posicion: int) -> np.ndarray:
        """Valor de cada mano (servida) en la posición dada."""
        metrica = {"tantos": te.tantos_netos, "individual": te.gana_individual,
                   "pareja": te.gana_pareja}[self.metrica]
        return metrica[:, posicion - 1, :] @ np.array(self.pesos)


def _solo(lance: Lance) -> tuple[float, ...]:
    return tuple(1.0 if l is lance else 0.0 for l in LANCES)


OBJETIVOS: dict[str, Objetivo] = {
    "tantos": Objetivo("tantos netos en paso", "tantos", (1.0,) * len(LANCES)),
    "grande": Objetivo("ganar la grande", "individual", _solo(Lance.GRANDE)),
    "chica": Objetivo("ganar la chica", "individual", _solo(Lance.CHICA)),
    "pares": Objetivo("ganar los pares", "individual", _solo(Lance.PARES)),
    "juego": Objetivo("ganar el juego", "individual", _solo(Lance.JUEGO)),
}
"""Objetivos predefinidos. Los de un lance usan P(gano yo): miden la fuerza de
*mi* mano en ese lance, sin depender de lo que lleve el compañero."""


def objetivo_con_pesos(texto: str) -> Objetivo:
    """Tantos netos ponderados por lance, p. ej. ``"grande=2, punto=0"``.

    Los lances no mencionados conservan peso 1 (tantos en paso).
    """
    pesos = {l: 1.0 for l in LANCES}
    for parte in (p for p in texto.split(",") if p.strip()):
        nombre, _, valor = parte.partition("=")
        try:
            pesos[Lance(nombre.strip().lower())] = float(valor)
        except ValueError:
            raise ValueError(f"Peso no válido: {parte.strip()!r} (usa lance=número, "
                             f"con lance en {', '.join(l.value for l in LANCES)})") from None
    descripcion = ", ".join(f"{l.value}={pesos[l]:g}" for l in LANCES)
    return Objetivo(f"tantos ponderados ({descripcion})", "tantos",
                    tuple(pesos[l] for l in LANCES))


# --- Valoración ----------------------------------------------------------------


@dataclass(frozen=True)
class ValoracionDescarte:
    """Valor esperado de una forma de descartarse (o de la mano servida si ``opcion`` es None).

    Todos los campos son esperanzas sobre la mano final.
    """

    opcion: OpcionDescarte | None
    valor: float
    tantos_netos: float
    p_pares: float
    p_juego: float
    p_31: float
    gana_individual: tuple[float, ...]  # E[P(gano yo)] por lance
    distribucion: np.ndarray = field(repr=False, compare=False)


def _valorar(distribucion: np.ndarray, opcion: OpcionDescarte | None, te: TablaEquity,
             posicion: int, objetivo: Objetivo) -> ValoracionDescarte:
    tabla, p = te.tabla, posicion - 1
    return ValoracionDescarte(
        opcion=opcion,
        valor=float(distribucion @ objetivo.valores(te, posicion)),
        tantos_netos=float(distribucion @ te.tantos_netos[:, p, :].sum(axis=1)),
        p_pares=float(distribucion[tabla.jugada_pares > 0].sum()),
        p_juego=float(distribucion[tabla.tiene_juego].sum()),
        p_31=float(distribucion[tabla.suma == 31].sum()),
        gana_individual=tuple(float(distribucion @ te.gana_individual[:, p, l])
                              for l in range(len(LANCES))),
        distribucion=distribucion,
    )


def evaluar_descartes(
    mano: Mano | str, posicion: int, te: TablaEquity, objetivo: Objetivo = OBJETIVOS["tantos"]
) -> tuple[list[ValoracionDescarte], ValoracionDescarte]:
    """Valora todas las formas de descartarse de una mano.

    Returns:
        Las valoraciones ordenadas de mejor a peor según el objetivo, y la
        valoración de la mano servida como referencia (no es una opción si hay
        mus: quedarse servido equivale a cortar, que es la Fase 3c).
    """
    tabla = te.tabla
    if isinstance(mano, str):
        mano = parsear_mano(mano, tabla.reglas)
    i = tabla.indice(mano)
    td = construir_tabla_descartes(tabla.reglas)
    valoraciones = [_valorar(fila, o, te, posicion, objetivo)
                    for o, fila in zip(td.opciones[i], td.transicion[i])]
    valoraciones.sort(key=lambda v: -v.valor)
    servida = np.zeros(tabla.n_manos)
    servida[i] = 1.0
    return valoraciones, _valorar(servida, None, te, posicion, objetivo)


@dataclass(frozen=True)
class MejorDescarte:
    """Fila de la tabla de descartes recomendados."""

    mano: str
    posicion: int
    mejor: OpcionDescarte
    valor: float
    segunda: OpcionDescarte | None
    margen: float
    """Ventaja de la mejor opción sobre la segunda (0 si solo hay una)."""
    valor_servida: float


def mejores_descartes(te: TablaEquity, objetivo: Objetivo = OBJETIVOS["tantos"]
                      ) -> list[MejorDescarte]:
    """Descarte recomendado para cada mano y posición."""
    tabla = te.tabla
    td = construir_tabla_descartes(tabla.reglas)
    filas = []
    for p in (1, 2, 3, 4):
        valores = objetivo.valores(te, p)
        for i, mano in enumerate(tabla.manos):
            v = td.transicion[i] @ valores
            orden = np.argsort(-v, kind="stable")
            segunda = td.opciones[i][orden[1]] if len(orden) > 1 else None
            filas.append(MejorDescarte(
                mano.texto(tabla.baraja), p, td.opciones[i][orden[0]], float(v[orden[0]]),
                segunda, float(v[orden[0]] - v[orden[1]]) if len(orden) > 1 else 0.0,
                float(valores[i])))
    return filas


# --- Verificación Monte Carlo ------------------------------------------------


@dataclass(frozen=True)
class SimulacionDescarte:
    """Resultado de simular robos físicos para una forma de descartarse."""

    n: int
    frecuencias: np.ndarray = field(repr=False)
    """Veces que sale cada mano final (una entrada por mano de la tabla)."""
    valor: EstimacionMedia | None
    p_juego: Estimacion


def simular_descarte(
    mano: Mano | str, opcion: OpcionDescarte, n: int, reglas: ReglasMus = REGLAS_POR_DEFECTO,
    *, valores: np.ndarray | None = None, semilla: int | None = None, confianza: float = 0.95,
) -> SimulacionDescarte:
    """Roba ``n`` veces de las cartas no vistas y cuenta las manos resultantes.

    Si se dan ``valores`` (uno por mano final), estima también su media.
    """
    tabla = construir_tabla(reglas)
    if isinstance(mano, str):
        mano = parsear_mano(mano, reglas)
    no_vistas = np.array(tabla.baraja.copias) - np.array(mano.conteos)
    mazo = np.repeat(np.arange(tabla.baraja.n_rangos), no_vistas).astype(np.int8)
    potencias = potencias_codigo(tabla.baraja)
    robadas = robar(n, mazo, opcion.n_descartes, generador(semilla))
    codigos = (np.array(opcion.conservadas) @ potencias) + potencias[robadas].sum(axis=1)
    indices = tabla.indices_de_codigos(codigos)
    valor = (EstimacionMedia.de_muestra(valores[indices].astype(np.float64), confianza)
             if valores is not None else None)
    return SimulacionDescarte(n, np.bincount(indices, minlength=tabla.n_manos), valor,
                              Estimacion(int(tabla.tiene_juego[indices].sum()), n, confianza))
