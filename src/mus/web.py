"""Fase 4: datos para la web y ficheros de referencia del núcleo en TypeScript.

El motor de Python sigue siendo la referencia. La web solo consulta tablas que
genera este módulo y hace en el navegador las cuentas ligeras: evaluar una mano
y calcular la distribución exacta de la mano tras descartarse. Hay dos salidas.

1. **Datos de la web** (``web/public/datos``), que se publican con ella:

   - ``equity/reparto.json``: equity exacta de cada mano y posición (Fase 2),
     sin información del compañero.
   - ``equity/<señas>.json``: lo mismo sabiendo las señas del compañero. Hay
     un fichero por cada conjunto distinto de manos que pueden dejar las
     señas libres (:func:`mus.senas.grupos_de_senas`; 16 en 8 reyes).
   - ``mesa-<tipo>.json``, uno por tipo de mesa: ¿cortar o dar mus?, el valor
     de cada descarte si hay mus y la equity de la mesa tras el mus. Las dos
     primeras cosas se simulan mano a mano con las cartas fijas, igual que
     ``python -m mus cortar``.
   - ``manifiesto.json``: versiones, reglas, escalas, orden de los arrays,
     señas, tipos de mesa y la huella SHA-256 de cada fichero.

2. **Ficheros de referencia** (``web/test/referencia``), para comprobar que
   el núcleo portado a TypeScript da exactamente lo mismo que Python: la
   evaluación de las 330 manos, la lectura de manos escritas, los lances de
   miles de repartos y la distribución exacta de la mano tras cada descarte,
   con numeradores enteros para comparar sin redondeos.

Formato de los números: enteros escalados (probabilidades ×10 000, tantos
×1 000) en arrays planos, con el orden descrito en el manifiesto. Es compacto
y conserva más precisión de la que se muestra. ``null`` = no disponible.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date
from math import comb
from pathlib import Path

import numpy as np

import mus
from mus import cortar as modulo_cortar
from mus import equity as modulo_equity
from mus import tras_mus as modulo_tras_mus
from mus.calibracion import curva_hay_mus, lambda_para
from mus.cartas import parsear_mano
from mus.condiciones import Condicion
from mus.cortar import MesaConCorte, mesa_rivales_razonables, valorar_corte
from mus.descarte import construir_tabla_descartes, distribucion_tras_descarte
from mus.equity import POSICIONES, TablaEquity, cargar_tabla_equity
from mus.evaluacion import Lance, resolver_mano
from mus.reglas import REGLAS_POR_DEFECTO, ReglasMus, Variante
from mus.senas import SENAS, grupos_de_senas
from mus.simulacion import EstimacionMedia, generador, repartir
from mus.tablas import TablaManos, construir_tabla, potencias_codigo

FORMATO = 1
"""Versión del formato de los ficheros. Cambiarla si cambia su estructura."""
VERSION_DECISIONES = "1"
"""Cambiarla invalida las decisiones guardadas en caché si cambia su cálculo."""

ESCALA_PROBABILIDAD = 10_000
ESCALA_TANTOS = 1_000
METRICAS_EQUITY = ("se_juega", "gana_individual", "gana_pareja", "tantos")
NOMBRES_POSICION = ("Mano", "Segundo", "Tercero", "Postre")

N_DECISION = 100_000
"""Repartos simulados por mano y posición para decidir si cortar."""
N_REFINADO = 400_000
"""Repartos con que se repite el cálculo cuando la decisión queda en el aire."""
SEMILLA_WEB = 20261008

DIRECTORIO_DATOS = Path("web/public/datos")
DIRECTORIO_REFERENCIA = Path("web/test/referencia")


# --- Tipos de mesa -------------------------------------------------------------------


@dataclass(frozen=True)
class TipoMesa:
    """Un nivel del selector "tipo de mesa".

    Se define por la frecuencia de mus que ve el jugador, no por λ: es lo que
    se puede observar en una partida. El λ (``factor_corte``) que la produce se
    obtiene invirtiendo la curva P(hay mus | λ) del modelo.
    """

    id: str
    nombre: str
    descripcion: str
    p_hay_mus: float | None
    """Frecuencia de mus buscada; ``None`` = rivales razonables sin escalar (λ = 1)."""
    por_defecto: bool = False


TIPOS_MESA: tuple[TipoMesa, ...] = (
    TipoMesa("mucho-mus", "Se da mucho mus", "Hay mus en unas 6 de cada 10 manos.", 0.60),
    TipoMesa("normal", "Normal", "Hay mus en unas 3 de cada 10 manos.", 0.30, por_defecto=True),
    TipoMesa("se-corta", "Se corta mucho",
             "Hay mus en 1 de cada 10 manos: los rivales cortan siempre que les conviene.", None),
)


def factor_corte(tipo: TipoMesa, curva: Sequence[tuple[float, float]]) -> float:
    """λ con el que el modelo da la frecuencia de mus del tipo de mesa (2 decimales)."""
    if tipo.p_hay_mus is None:
        return 1.0
    lam, dentro = lambda_para(tipo.p_hay_mus, list(curva))
    if not dentro:
        raise ValueError(f"El modelo no puede dar P(hay mus) = {tipo.p_hay_mus}")
    return round(lam, 2)


# --- Decisiones de corte y descarte ----------------------------------------------------


@dataclass(frozen=True, eq=False)
class DecisionesMesa:
    """¿Cortar o dar mus? y valor de cada descarte, para cada mano y posición.

    Los arrays por caso tienen forma (manos, 4). Los de opciones, (4, opciones):
    las opciones de todas las manos van seguidas en el orden canónico de
    :func:`mus.descarte.opciones_descarte`, y las de la mano h ocupan
    ``[inicio[h], inicio[h + 1])``. Lo no calculado queda a NaN (o 0 en los
    enteros).

    Atributos:
        decision: 1 = dar mus, −1 = cortar, 0 = indiferente (el IC 95 % de la
            ventaja contiene el 0), como :attr:`mus.cortar.DecisionCorte.decision`.
        ventaja, radio: dar mus − cortar (tantos por mano) y la semiamplitud de
            su IC 95 %.
        cortar, mus: valor de cada decisión.
        p_mus_despues: probabilidad de que den mus todos los que hablan después.
        n_efectivo: tamaño efectivo de la muestra (Kish).
        repartos: repartos simulados (N_DECISION o, si se refinó, N_REFINADO).
        opcion_si_hay_mus: tantos esperados si hay mus y me descarto así.
        opcion_diferencia, opcion_radio: esa opción menos la mejor, reparto a
            reparto, y la semiamplitud de su IC 95 %.
    """

    factor_corte: float
    inicio: np.ndarray
    decision: np.ndarray
    ventaja: np.ndarray
    radio: np.ndarray
    cortar: np.ndarray
    mus: np.ndarray
    p_mus_despues: np.ndarray
    n_efectivo: np.ndarray
    repartos: np.ndarray
    opcion_si_hay_mus: np.ndarray
    opcion_diferencia: np.ndarray
    opcion_radio: np.ndarray


_CAMPOS_DECISIONES = ("inicio", "decision", "ventaja", "radio", "cortar", "mus", "p_mus_despues",
                      "n_efectivo", "repartos", "opcion_si_hay_mus", "opcion_diferencia",
                      "opcion_radio")
_CODIGO_DECISION = {"mus": 1, "cortar": -1, "indiferente": 0}


def _radio(e: EstimacionMedia) -> float:
    bajo, alto = e.intervalo
    return (alto - bajo) / 2


def _caso(mesa: MesaConCorte, h: int, posicion: int, n: int, semilla: int) -> tuple:
    """Simula una mano y posición; devuelve un resumen pequeño (se envía entre procesos)."""
    td = mesa.descarte.td
    d = valorar_corte(td.tabla.manos[h], posicion, mesa, n, semilla=semilla)
    indice = {o: i for i, o in enumerate(td.opciones[h])}
    opciones = np.full((3, len(indice)), np.nan)
    for o in d.opciones:
        if o.si_hay_mus is not None:
            opciones[:, indice[o.opcion]] = (o.si_hay_mus.media,
                                            o.si_hay_mus_frente_a_la_mejor.media,
                                            _radio(o.si_hay_mus_frente_a_la_mejor))
    v = d.ventaja_mus
    return (h, posicion, n, _CODIGO_DECISION[d.decision], v.media, _radio(v), d.cortar.media,
            d.mus.media, d.p_mus_despues, v.n, opciones)


_MESA_DEL_PROCESO: MesaConCorte | None = None


def _preparar_proceso(mesa: MesaConCorte) -> None:
    global _MESA_DEL_PROCESO
    _MESA_DEL_PROCESO = mesa


def _caso_en_proceso(tarea: tuple[int, int, int, int]) -> tuple:
    assert _MESA_DEL_PROCESO is not None
    return _caso(_MESA_DEL_PROCESO, *tarea)


def _ejecutar(mesa: MesaConCorte, tareas: list[tuple[int, int, int, int]], procesos: int,
              decir: Callable[[str], None], etiqueta: str) -> list[tuple]:
    """Ejecuta los casos, en paralelo si ``procesos`` > 1, informando del avance.

    Cada proceso recibe la mesa una sola vez, al arrancar. Los resultados no
    dependen del número de procesos: cada caso lleva su propia semilla.
    """
    inicio = time.perf_counter()
    resultados: list[tuple] = []
    aviso = max(1, len(tareas) // 20)

    def anotar(r: tuple) -> None:
        resultados.append(r)
        if len(resultados) % aviso == 0 or len(resultados) == len(tareas):
            transcurrido = time.perf_counter() - inicio
            restante = transcurrido / len(resultados) * (len(tareas) - len(resultados))
            decir(f"  {etiqueta}: {len(resultados)}/{len(tareas)} casos "
                  f"({transcurrido:.0f} s; quedan ~{restante:.0f} s)")

    if procesos == 1 or len(tareas) <= 1:
        for t in tareas:
            anotar(_caso(mesa, *t))
    else:
        with ProcessPoolExecutor(max_workers=procesos, initializer=_preparar_proceso,
                                 initargs=(mesa,)) as ejecutor:
            for r in ejecutor.map(_caso_en_proceso, tareas, chunksize=4):
                anotar(r)
    return resultados


def calcular_decisiones(
    mesa: MesaConCorte,
    factor: float,
    manos: Sequence[int] | None = None,
    *,
    n: int = N_DECISION,
    n_refinado: int = N_REFINADO,
    procesos: int = 1,
    semilla: int = SEMILLA_WEB,
    informar: Callable[[str], None] | None = None,
) -> DecisionesMesa:
    """Decide cortar o dar mus y valora los descartes de cada mano y posición.

    Cada caso se simula con :func:`mus.cortar.valorar_corte` (``n`` repartos
    con la mano fija). Si la decisión queda indiferente (el IC 95 % de la
    ventaja contiene el 0), se repite **desde cero** con ``n_refinado``
    repartos y otra semilla, y se usa solo el segundo cálculo. Como es
    independiente del primero, elegir qué casos se repiten no sesga su
    estimación. El primero solo sirve para no gastar repartos en decisiones
    claras.

    Args:
        factor: λ de la mesa (solo se anota en el resultado).
        manos: índices de las manos a calcular (por defecto, todas).
        semilla: semilla base; cada caso usa una propia derivada de ella, así
            que el resultado es reproducible y no depende de ``procesos``.
    """
    decir = informar or (lambda _: None)
    td = mesa.descarte.td
    n_manos = td.tabla.n_manos
    manos = list(range(n_manos)) if manos is None else list(manos)
    inicio = np.zeros(n_manos + 1, dtype=np.int64)
    np.cumsum([len(o) for o in td.opciones], out=inicio[1:])

    tareas = [(h, p, n, semilla + 100 * h + p) for h in manos for p in POSICIONES]
    resultados = {(r[0], r[1]): r for r in _ejecutar(mesa, tareas, procesos, decir,
                                                     f"{n} repartos")}
    if n_refinado > n:
        dudosas = [(h, p, n_refinado, semilla + 100 * h + 10 + p)
                   for (h, p), r in resultados.items() if r[3] == 0]
        if dudosas:
            decir(f"  {len(dudosas)} decisiones indiferentes: se repiten con {n_refinado} repartos")
            for r in _ejecutar(mesa, dudosas, procesos, decir, f"{n_refinado} repartos"):
                resultados[(r[0], r[1])] = r

    por_caso = {k: np.full((n_manos, len(POSICIONES)), np.nan)
                for k in ("ventaja", "radio", "cortar", "mus", "p_mus_despues")}
    decision = np.zeros((n_manos, len(POSICIONES)), dtype=np.int64)
    n_efectivo = np.zeros_like(decision)
    repartos = np.zeros_like(decision)
    opciones = np.full((3, len(POSICIONES), int(inicio[-1])), np.nan)
    for (h, p), r in resultados.items():
        _, _, n_caso, codigo, ventaja, radio, cortar, mus_, p_despues, n_ef, valores = r
        fila = (h, p - 1)
        decision[fila], n_efectivo[fila], repartos[fila] = codigo, n_ef, n_caso
        for clave, valor in (("ventaja", ventaja), ("radio", radio), ("cortar", cortar),
                             ("mus", mus_), ("p_mus_despues", p_despues)):
            por_caso[clave][fila] = valor
        opciones[:, p - 1, inicio[h]:inicio[h + 1]] = valores
    return DecisionesMesa(factor, inicio, decision, por_caso["ventaja"], por_caso["radio"],
                          por_caso["cortar"], por_caso["mus"], por_caso["p_mus_despues"],
                          n_efectivo, repartos, *opciones)


def cargar_decisiones(mesa: MesaConCorte, factor: float, manos: Sequence[int] | None = None, *,
                      n: int = N_DECISION, n_refinado: int = N_REFINADO, procesos: int = 1,
                      semilla: int = SEMILLA_WEB, directorio: str | Path = "resultados/cache",
                      informar: Callable[[str], None] | None = None) -> DecisionesMesa:
    """Como :func:`calcular_decisiones`, con caché en disco.

    La huella incluye las reglas, las versiones de los cálculos, las políticas
    de la mesa, los repartos, la semilla y las manos.
    """
    texto = "|".join(map(str, (
        repr(mesa.reglas), modulo_equity.VERSION_MOTOR, modulo_tras_mus.VERSION_SIMULACION,
        modulo_cortar.VERSION_SIMULACION, VERSION_DECISIONES, mesa.corte.huella(),
        mesa.descarte.huella(), factor, n, n_refinado, semilla,
        None if manos is None else tuple(manos))))
    ruta = Path(directorio) / f"web_{hashlib.sha256(texto.encode()).hexdigest()[:16]}.npz"
    if ruta.exists():
        with np.load(ruta) as f:
            return DecisionesMesa(float(f["factor_corte"]), *(f[k] for k in _CAMPOS_DECISIONES))
    resultado = calcular_decisiones(mesa, factor, manos, n=n, n_refinado=n_refinado,
                                    procesos=procesos, semilla=semilla, informar=informar)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(ruta, factor_corte=resultado.factor_corte,
                        **{k: getattr(resultado, k) for k in _CAMPOS_DECISIONES})
    return resultado


# --- Escritura de los ficheros -----------------------------------------------------------


def enteros(valores: np.ndarray | Sequence[float], escala: float = 1) -> list[int | None]:
    """Array aplanado de enteros ``round(valor · escala)``; NaN se convierte en ``None``."""
    a = np.round(np.asarray(valores, dtype=np.float64).ravel() * escala)
    return [int(v) if np.isfinite(v) else None for v in a]


def datos_equity(te: TablaEquity) -> list[int | None]:
    """Tabla de equity como array plano, en orden (mano, posición, lance, métrica)."""
    escalas = np.array([ESCALA_PROBABILIDAD] * 3 + [ESCALA_TANTOS], dtype=np.float64)
    datos = np.stack([te.se_juega, te.gana_individual, te.gana_pareja, te.tantos_netos], axis=-1)
    return enteros(datos * escalas)


def _solo_ocho_reyes(reglas: ReglasMus) -> None:
    if reglas.variante is not Variante.OCHO_REYES:
        raise ValueError("La web del MVP solo usa la variante de 8 reyes")


def _escribir_json(ruta: Path, datos: dict) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                    encoding="utf-8")
    return ruta


def _descripcion_reglas(reglas: ReglasMus) -> dict:
    p = reglas.puntuacion
    return {
        "variante": reglas.variante.value,
        "orden_juego": list(reglas.orden_juego),
        "treinta_y_una_real": reglas.treinta_y_una_real,
        "puntuacion": {"grande": p.grande, "chica": p.chica, "par": p.par, "medias": p.medias,
                       "duples": p.duples, "juego_31": p.juego_31, "juego_otro": p.juego_otro,
                       "punto": p.punto},
        "descarte": {"minimo": reglas.descarte.minimo, "maximo": reglas.descarte.maximo},
        "tantos_partida": reglas.tantos_partida,
    }


def _indices(mascara: np.ndarray) -> list[int]:
    return [int(i) for i in np.flatnonzero(mascara)]


def _fichero_mesa(tipo: TipoMesa, mesa: MesaConCorte, decisiones: DecisionesMesa) -> dict:
    eq = mesa.equity
    return {
        "formato": FORMATO,
        "mesa": {"id": tipo.id, "factor_corte": decisiones.factor_corte,
                 "p_hay_mus": round(mesa.p_hay_mus, 4)},
        "decision": {
            "orden": "mano, posicion",
            "decision": enteros(decisiones.decision),
            "ventaja": enteros(decisiones.ventaja, ESCALA_TANTOS),
            "radio": enteros(decisiones.radio, ESCALA_TANTOS),
            "cortar": enteros(decisiones.cortar, ESCALA_TANTOS),
            "mus": enteros(decisiones.mus, ESCALA_TANTOS),
            "p_mus_despues": enteros(decisiones.p_mus_despues, ESCALA_PROBABILIDAD),
            "n_efectivo": enteros(decisiones.n_efectivo),
            "repartos": enteros(decisiones.repartos),
        },
        "opciones": {
            "orden": "posicion, opcion (en el orden de manifiesto.descartes)",
            "si_hay_mus": enteros(decisiones.opcion_si_hay_mus, ESCALA_TANTOS),
            "diferencia": enteros(decisiones.opcion_diferencia, ESCALA_TANTOS),
            "radio": enteros(decisiones.opcion_radio, ESCALA_TANTOS),
        },
        "tras_mus": {
            "orden": "mano, posicion, lance, metrica",
            "datos": datos_equity(eq.tabla),
            "error_tantos": enteros(eq.error_tantos, ESCALA_TANTOS),
        },
    }


def _huella(ruta: Path) -> dict:
    contenido = ruta.read_bytes()
    return {"bytes": len(contenido), "sha256": hashlib.sha256(contenido).hexdigest()}


def exportar_datos_web(
    directorio: str | Path = DIRECTORIO_DATOS,
    reglas: ReglasMus = REGLAS_POR_DEFECTO,
    *,
    tipos_mesa: Sequence[TipoMesa] = TIPOS_MESA,
    manos: Sequence[int] | None = None,
    n: int = N_DECISION,
    n_refinado: int = N_REFINADO,
    procesos: int | None = None,
    tabla_equity: Callable[[Condicion | None], TablaEquity] | None = None,
    construir_mesa: Callable[[float], MesaConCorte] | None = None,
    curva: Sequence[tuple[float, float]] | None = None,
    directorio_cache: str | Path = "resultados/cache",
    informar: Callable[[str], None] | None = None,
) -> list[Path]:
    """Genera todos los datos de la web (ver el docstring del módulo).

    Lo costoso se guarda en ``directorio_cache``. Los parámetros
    ``tabla_equity``, ``construir_mesa`` y ``curva`` permiten sustituir el motor
    (en los tests); por defecto se usan :func:`mus.equity.cargar_tabla_equity`,
    :func:`mus.cortar.mesa_rivales_razonables` y
    :func:`mus.calibracion.curva_hay_mus`.

    Returns:
        Las rutas escritas, con el manifiesto en último lugar.
    """
    _solo_ocho_reyes(reglas)
    decir = informar or (lambda _: None)
    directorio = Path(directorio)
    procesos = procesos or max(1, min(6, (os.cpu_count() or 2) - 2))
    tabla = construir_tabla(reglas)
    td = construir_tabla_descartes(reglas)
    tabla_equity = tabla_equity or (lambda c: cargar_tabla_equity(reglas, companero=c))
    construir_mesa = construir_mesa or (lambda l: mesa_rivales_razonables(reglas,
                                                                          factor_corte=l))
    escritos: list[Path] = []

    # Equity del reparto inicial, sin información y con cada conjunto de señas.
    decir("Equity del reparto inicial (sin información y con cada combinación de señas)...")
    tablas_equity = [{"id": "reparto", "senas": [], "fichero": "equity/reparto.json"}]
    escritos.append(_escribir_json(directorio / "equity/reparto.json", {
        "formato": FORMATO, "condicion": None, "orden": "mano, posicion, lance, metrica",
        "datos": datos_equity(tabla_equity(None))}))
    for grupo in grupos_de_senas(tabla):
        decir(f"  señas: {grupo.id}")
        fichero = f"equity/{'_'.join(s.id for s in grupo.senas)}.json"
        condicion = {"senas": [s.id for s in grupo.senas], "manos": _indices(grupo.mascara)}
        escritos.append(_escribir_json(directorio / fichero, {
            "formato": FORMATO, "condicion": condicion, "orden": "mano, posicion, lance, metrica",
            "datos": datos_equity(tabla_equity(grupo.condicion))}))
        tablas_equity.append({"id": grupo.id, **condicion, "fichero": fichero})

    # Tipos de mesa: λ, mesa con corte y decisiones mano a mano.
    curva = curva if curva is not None else curva_hay_mus(reglas)
    mesas = []
    for tipo in tipos_mesa:
        lam = factor_corte(tipo, curva)
        mesa = construir_mesa(lam)
        decir(f"Mesa «{tipo.nombre}»: λ = {lam:g}, P(hay mus) = {mesa.p_hay_mus:.3f}")
        decisiones = cargar_decisiones(mesa, lam, manos, n=n, n_refinado=n_refinado,
                                       procesos=procesos, directorio=directorio_cache,
                                       informar=decir)
        fichero = f"mesa-{tipo.id}.json"
        escritos.append(_escribir_json(directorio / fichero, _fichero_mesa(tipo, mesa, decisiones)))
        mesas.append({"id": tipo.id, "nombre": tipo.nombre, "descripcion": tipo.descripcion,
                      "factor_corte": lam, "p_hay_mus": round(mesa.p_hay_mus, 4),
                      "por_defecto": tipo.por_defecto, "fichero": fichero})

    potencias = potencias_codigo(tabla.baraja)
    manifiesto = {
        "formato": FORMATO,
        "nombre": "Mus Analytics",
        "generado": date.today().isoformat(),
        "versiones": {"paquete": mus.__version__, "equity": modulo_equity.VERSION_MOTOR,
                      "tras_mus": modulo_tras_mus.VERSION_SIMULACION,
                      "cortar": modulo_cortar.VERSION_SIMULACION, "decisiones": VERSION_DECISIONES},
        "reglas": _descripcion_reglas(reglas),
        "calculo": {"repartos_decision": n, "repartos_refinado": n_refinado,
                    "confianza": 0.95, "semilla": SEMILLA_WEB},
        "posiciones": [{"numero": p, "nombre": NOMBRES_POSICION[p - 1]} for p in POSICIONES],
        "lances": [l.value for l in Lance],
        "metricas_equity": list(METRICAS_EQUITY),
        "escalas": {"probabilidad": ESCALA_PROBABILIDAD, "tantos": ESCALA_TANTOS},
        "manos": [m.texto(tabla.baraja) for m in tabla.manos],
        "descartes": {
            "inicio": [0, *np.cumsum([len(o) for o in td.opciones]).tolist()],
            "conservadas": [int(np.array(o.conservadas) @ potencias)
                            for opciones in td.opciones for o in opciones],
        },
        "senas": [{"id": s.id, "nombre": s.nombre, "cartas": s.cartas, "gesto": s.gesto,
                   "manos": _indices(s.mascara(tabla))} for s in SENAS],
        "tablas_equity": tablas_equity,
        "mesas": mesas,
        "ficheros": {str(r.relative_to(directorio).as_posix()): _huella(r) for r in escritos},
    }
    escritos.append(_escribir_json(directorio / "manifiesto.json", manifiesto))
    return escritos


# --- Ficheros de referencia para el núcleo en TypeScript -----------------------------------

_LECTURAS = (
    "R R C 5", "r r c 5", "R,R,C,5", "R;R;C;5", "  R  R C   5 ", "RRC5", "rrc5", "5 C R R",
    "3 3 11 5", "12 12 11 5", "3 R 12 C", "2 2 4 5", "1 1 10 4", "1 2 A 7", "10 11 12 1",
    "S C R A", "4 4 4 4", "A A A A", "R R R R", "3 3 3 3", "7 7 7 S", "6 5 4 A", "C S 7 4",
    "R R C", "R R C 5 5", "R R C X", "", "RRC", "RRC55", "R R C 0", "R R C 8", "R R C 9",
    "R R C 13", "R R C 3x", "B R C 5", "R-R-C-5",
)
"""Entradas de prueba para la lectura de manos: válidas e inválidas."""

_REPARTOS_ESPECIALES = (
    ("R C 7 4", "R C 7 4", "R C 7 4", "R C 7 4"),  # todo empatado: gana siempre la mano
    ("7 6 5 4", "7 6 5 A", "6 5 4 A", "S 6 5 4"),  # nadie tiene pares ni juego: se juega el punto
    ("7 6 5 4", "7 6 5 A", "6 5 4 A", "R C S A"),  # solo el postre tiene juego: no hay punto
    ("R R A A", "C C C C", "5 5 5 5", "R R 4 4"),  # duples: pareja alta primero
    ("R R C S", "R R C S", "C S 7 4", "A A A A"),  # empate en grande entre 1 y 2
    ("A A 4 5", "C C 5 4", "A A 4 5", "S 7 6 4"),  # empate en chica y pares entre 1 y 3
    ("R C S A", "R C 7 4", "C S 6 5", "R R C A"),  # cuatro 31: gana la mano
    ("R R C S", "R R S S", "C C 7 7", "R C S 7"),  # 40, 40, 34, 37
    ("6 6 6 A", "5 5 5 4", "S S S 4", "7 7 4 4"),  # medias frente a duples
    ("C S 5 4", "C S 6 4", "S 7 6 5", "S 7 5 4"),  # punto 29, 30, 28, 26
    ("A A A 4", "A A A 5", "A 4 4 5", "6 5 4 A"),  # chica muy baja
    ("R R R A", "R R R 4", "7 7 7 S", "A A C S"),  # solomillo, medias y 31
)
"""Repartos con empates y casos límite (todos válidos con una sola baraja)."""


def _pesos_huella(n_manos: int, semilla: int) -> np.ndarray:
    """Dos vectores de enteros pseudoaleatorios (< 2²⁰) para resumir distribuciones.

    Σ numerador·peso cabe holgadamente en 2⁵³ (C(36, 4) · 2²⁰ · 330 ≈ 2·10¹³),
    así que en TypeScript la suma también es exacta.
    """
    return np.random.default_rng(semilla).integers(1, 2 ** 20, size=(2, n_manos), dtype=np.int64)


def exportar_referencia(
    directorio: str | Path = DIRECTORIO_REFERENCIA,
    reglas: ReglasMus = REGLAS_POR_DEFECTO,
    *,
    repartos: int = 3000,
    semilla: int = SEMILLA_WEB,
) -> list[Path]:
    """Escribe los ficheros de referencia del núcleo en TypeScript.

    - ``evaluacion.json``: baraja, reglas y, para cada mano, conteos, código,
      combinaciones, suma, jugada de pares, tantos y fuerza en cada lance;
      además, cómo se leen (o se rechazan) varias manos escritas.
    - ``lances.json``: ganador y tantos de cada lance en repartos especiales y
      aleatorios, resueltos con :func:`mus.evaluacion.resolver_mano`, la
      versión escalar e independiente de las tablas.
    - ``descartes.json``: las opciones de cada mano en orden canónico y, para
      cada una, numeradores **enteros** de la distribución exacta de la mano
      final (sobre C(36, cartas pedidas)): totales por jugada y dos huellas
      Σ numerador·peso que detectan cualquier diferencia. Para una muestra de
      manos, la distribución completa.
    """
    _solo_ocho_reyes(reglas)
    directorio = Path(directorio)
    tabla = construir_tabla(reglas)
    return [
        _escribir_json(directorio / "evaluacion.json", _referencia_evaluacion(tabla)),
        _escribir_json(directorio / "lances.json",
                       _referencia_lances(tabla, repartos, semilla)),
        _escribir_json(directorio / "descartes.json", _referencia_descartes(tabla, semilla)),
    ]


def _referencia_evaluacion(tabla: TablaManos) -> dict:
    baraja, reglas = tabla.baraja, tabla.reglas
    manos = [[m.texto(baraja), list(m.conteos), int(tabla.codigos[i]),
              int(tabla.combinaciones[i]), int(tabla.suma[i]), int(tabla.jugada_pares[i]),
              int(tabla.puntos_pares[i]), int(tabla.puntos_juego[i]),
              [int(tabla.fuerza[l][i]) for l in Lance]]
             for i, m in enumerate(tabla.manos)]
    lecturas = []
    for entrada in _LECTURAS:
        try:
            lecturas.append({"entrada": entrada, "mano": parsear_mano(entrada, reglas).texto(baraja)})
        except ValueError:
            lecturas.append({"entrada": entrada, "error": True})
    return {
        "formato": FORMATO,
        "reglas": _descripcion_reglas(reglas),
        "baraja": {"simbolos": list(baraja.simbolos), "copias": list(baraja.copias),
                   "valores": list(baraja.valores), "alias": dict(baraja.alias)},
        "lances": [l.value for l in Lance],
        "columnas": ["texto", "conteos", "codigo", "combinaciones", "suma", "pares",
                     "puntos_pares", "puntos_juego", "fuerza"],
        "manos": manos,
        "lectura": lecturas,
    }


def _referencia_lances(tabla: TablaManos, n: int, semilla: int) -> dict:
    reglas, baraja = tabla.reglas, tabla.baraja
    textos = [list(r) for r in _REPARTOS_ESPECIALES]
    aleatorios = repartir(n, tabla, generador(semilla))
    textos += [[tabla.manos[i].texto(baraja) for i in fila] for fila in aleatorios]
    filas = []
    for reparto in textos:
        manos = [parsear_mano(t, reglas) for t in reparto]
        conteo = np.sum([m.conteos for m in manos], axis=0)
        assert (conteo <= np.array(baraja.copias)).all(), f"reparto imposible: {reparto}"
        resultado = resolver_mano(manos, reglas)
        filas.append([reparto, [[r.ganador or 0, r.tantos] for r in resultado.values()]])
    return {
        "formato": FORMATO,
        "lances": [l.value for l in Lance],
        "columnas": ["manos (en orden de juego: mano, segundo, tercero, postre)",
                     "por lance: [ganador (0 = no se juega), tantos que cobra su pareja]"],
        "repartos": filas,
    }


def _referencia_descartes(tabla: TablaManos, semilla: int) -> dict:
    td = construir_tabla_descartes(tabla.reglas)
    baraja = tabla.baraja
    potencias = potencias_codigo(baraja)
    pesos = _pesos_huella(tabla.n_manos, semilla)
    mascaras = {
        "pares": tabla.jugada_pares > 0,
        "medias": tabla.jugada_pares == 2,
        "duples": tabla.jugada_pares == 3,
        "juego": tabla.tiene_juego,
        "juego_31": tabla.suma == 31,
    }
    no_vistas = baraja.total_cartas - 4
    muestra = set(range(0, tabla.n_manos, 15))
    manos, distribuciones = [], []
    for i, mano in enumerate(tabla.manos):
        filas = []
        for opcion in td.opciones[i]:
            k = opcion.n_descartes
            denominador = comb(no_vistas, k)
            reales = distribucion_tras_descarte(tabla, mano, opcion) * denominador
            numeradores = np.round(reales).astype(np.int64)
            assert np.abs(reales - numeradores).max() < 1e-6, "los numeradores deben ser enteros"
            assert numeradores.sum() == denominador
            codigo = int(np.array(opcion.conservadas) @ potencias)
            filas.append([codigo, k, denominador,
                          *(int(numeradores[m].sum()) for m in mascaras.values()),
                          *(int(numeradores @ p) for p in pesos)])
            if i in muestra:
                distribuciones.append({"mano": mano.texto(baraja), "conservadas": codigo,
                                       "numeradores": [[int(j), int(numeradores[j])]
                                                       for j in np.flatnonzero(numeradores)]})
        manos.append({"texto": mano.texto(baraja), "opciones": filas})
    return {
        "formato": FORMATO,
        "cartas_no_vistas": no_vistas,
        "columnas": ["conservadas (código)", "cartas pedidas", "denominador = C(36, pedidas)",
                     *mascaras, "huella_1", "huella_2"],
        "nota": ("Numeradores enteros de P(mano final) · C(36, pedidas). La huella k es "
                 "Σ numerador(mano final) · pesos_huella[k][índice de la mano final]."),
        "pesos_huella": pesos.tolist(),
        "manos": manos,
        "distribuciones": distribuciones,
    }


@dataclass(frozen=True)
class ConsultaWeb:
    """Lo que la web enseñará para una mano, leído solo de los ficheros exportados.

    Las cifras ya están desescaladas (probabilidades en [0, 1], tantos).
    """

    mano: str
    posicion: int
    mesa: str
    senas: tuple[str, ...]
    equity: dict[str, dict[str, float | None]]
    """Por lance: se_juega, gana_individual, gana_pareja, tantos."""
    decision: dict[str, float | int | None]
    opciones: list[dict[str, float | str | None]]
    """Descartes de mejor a peor: me_quedo, si_hay_mus, diferencia, radio."""


def consultar_datos(directorio: str | Path, mano: str, posicion: int, mesa: str | None = None,
                    senas: Sequence[str] = ()) -> ConsultaWeb:
    """Lee de los ficheros de la web la información de una mano y posición.

    No usa el motor salvo para leer la mano escrita: sirve para comprobar que
    los ficheros dicen lo mismo que ``mus equity`` y ``mus cortar``.
    """
    directorio = Path(directorio)
    m = json.loads((directorio / "manifiesto.json").read_text(encoding="utf-8"))
    tabla = construir_tabla()
    texto = parsear_mano(mano).texto(tabla.baraja)
    h = m["manos"].index(texto)
    p = posicion - 1
    ep, et = m["escalas"]["probabilidad"], m["escalas"]["tantos"]

    def leer(nombre: str) -> dict:
        return json.loads((directorio / nombre).read_text(encoding="utf-8"))

    # Equity: la tabla cuyo conjunto de manos es la intersección de las señas.
    if senas:
        por_id = {s["id"]: set(s["manos"]) for s in m["senas"]}
        desconocidas = [s for s in senas if s not in por_id]
        if desconocidas:
            raise ValueError(f"Señas desconocidas: {', '.join(desconocidas)}")
        manos_compatibles = sorted(set.intersection(*(por_id[s] for s in senas)))
        if not manos_compatibles:
            raise ValueError("Ninguna mano cumple a la vez esas señas")
        tabla_equity = next((t for t in m["tablas_equity"] if t.get("manos") == manos_compatibles),
                            None)
        if tabla_equity is None:  # no debería pasar: se exportan todos los conjuntos posibles
            raise ValueError(f"No hay tabla exportada para las señas {', '.join(senas)}")
    else:
        tabla_equity = m["tablas_equity"][0]
    datos = leer(tabla_equity["fichero"])["datos"]
    equity = {}
    for l, lance in enumerate(m["lances"]):
        base = ((h * 4 + p) * 5 + l) * 4
        valores = datos[base:base + 4]
        equity[lance] = {nombre: None if v is None else v / (et if nombre == "tantos" else ep)
                         for nombre, v in zip(m["metricas_equity"], valores)}

    # Decisión y descartes en la mesa elegida (por defecto, la marcada como tal).
    info_mesa = next(x for x in m["mesas"] if (x["id"] == mesa if mesa else x["por_defecto"]))
    f = leer(info_mesa["fichero"])
    k = h * 4 + p
    escala = {"p_mus_despues": ep, "n_efectivo": 1, "repartos": 1, "decision": 1}
    decision = {nombre: (None if v[k] is None else v[k] / escala.get(nombre, et))
                for nombre, v in f["decision"].items() if nombre != "orden"}
    inicio, conservadas = m["descartes"]["inicio"], m["descartes"]["conservadas"]
    n_opciones = inicio[-1]
    opciones = []
    for o in range(inicio[h], inicio[h + 1]):
        i = p * n_opciones + o
        codigo, quedo = conservadas[o], []
        for r in reversed(range(tabla.baraja.n_rangos)):
            quedo += [tabla.baraja.simbolos[r]] * (codigo // 5 ** r % 5)
        valores = {c: (None if f["opciones"][c][i] is None else f["opciones"][c][i] / et)
                   for c in ("si_hay_mus", "diferencia", "radio")}
        opciones.append({"me_quedo": " ".join(quedo) or "nada", **valores})
    opciones.sort(key=lambda x: -(x["si_hay_mus"] if x["si_hay_mus"] is not None else -np.inf))
    return ConsultaWeb(texto, posicion, info_mesa["id"], tuple(senas), equity, decision, opciones)


def comprobar_manifiesto(directorio: str | Path = DIRECTORIO_DATOS) -> list[str]:
    """Problemas del manifiesto: ficheros que faltan o cuya huella no coincide."""
    directorio = Path(directorio)
    manifiesto = json.loads((directorio / "manifiesto.json").read_text(encoding="utf-8"))
    problemas = []
    for nombre, esperado in manifiesto["ficheros"].items():
        ruta = directorio / nombre
        if not ruta.exists():
            problemas.append(f"falta {nombre}")
        elif _huella(ruta) != esperado:
            problemas.append(f"{nombre} no coincide con su huella")
    return problemas

