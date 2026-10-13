"""Fase 5: el entrenador. Valoración de las respuestas y peso de cada situación.

El entrenador no calcula nada nuevo del juego: plantea una mano, compara la
respuesta con los datos que ya publica la web y dice cuántos tantos se pierden
frente a la mejor opción. Este módulo es la versión en Python de esa
valoración. Lee **solo los ficheros publicados** (``web/public/datos``), con
los mismos enteros que lee el navegador, y sirve para dos cosas:

- generar ``web/test/referencia/entrenador.json``, con la valoración y el peso
  de todas las situaciones, que los tests de la web comparan sin tolerancia
  con lo que calcula el núcleo en TypeScript;
- ``python -m mus entrenador``, que imprime lo que enseña la pantalla para
  una mano, para cotejarlo con ``python -m mus cortar``.

Reglas de la valoración (las mismas que la calculadora, ``web/src/vista``):

- **¿Mus o corto?** Si la decisión es indiferente (el IC 95 % de la ventaja
  contiene el 0) o la ventaja es menor que :data:`UMBRAL_IGUAL`, da igual y no
  se pierde nada. Si no, quien elige lo contrario pierde la ventaja.
- **¿Qué tiras?** La mejor opción y las "casi iguales" (dentro de su margen
  de error o a menos de :data:`UMBRAL_DESCARTE`) no pierden nada; las demás,
  su diferencia con la mejor.

Todo va en enteros: milésimas de tanto y diezmilésimas de probabilidad, como
en los ficheros. Los pesos son productos de enteros, exactos también en
JavaScript (caben de sobra en 2⁵³).

Situaciones «como en la mesa» (pesos):

- ¿Mus o corto?: combinaciones de la mano × P(te toca hablar con ella).
- ¿Qué tiras?: combinaciones × P(te toca hablar) × P(dan mus los de después),
  y solo si el entrenador no recomienda cortar con esa mano: quien se entrena
  es quien decide con ella, y el modelo le supone la mejor respuesta (el
  ``factor_corte`` de la mesa describe cuánto cortan los demás).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mus.cartas import parsear_mano
from mus.tablas import construir_tabla

UMBRAL_IGUAL = 30
"""Milésimas de tanto. Por debajo, cortar y dar mus dan igual (menos de un tanto
cada 30 manos). Es ``UMBRAL_IGUAL`` de ``web/src/vista/vista.ts``."""
UMBRAL_CLARA = 150
"""A partir de aquí la decisión es "clara"; por debajo, "por poco"."""
UMBRAL_DESCARTE = 20
"""Dos descartes son "casi iguales" si difieren menos que esto o que su margen."""
UMBRAL_AJUSTADA = 200
"""Una situación es "ajustada" si hay una opción peor de verdad, pero por menos
de esto: menos de 2 tantos cada 10 manos."""

MODOS = ("mesa", "ajustadas")
"""Modos de sorteo que dependen solo de los datos (el repaso de fallos depende
de las respuestas de cada usuario y vive en la web)."""
EJERCICIOS = ("corte", "descarte")

VEREDICTOS = {1: "mus", -1: "corta", 0: "igual"}
INTENSIDADES = {2: "clara", 1: "por-poco", 0: "igual"}

HABLAN_ANTES = (
    "Eres mano: hablas el primero.",
    "La mano ha dado mus.",
    "Los dos anteriores han dado mus.",
    "Los tres anteriores han dado mus.",
)
"""Qué ha pasado antes de que te toque hablar, por posición."""


def contexto(nombre_mesa: str) -> str:
    """Contra qué se compara cada respuesta, en lenguaje de jugador."""
    return (f"La mejor jugada contra una mesa «{nombre_mesa}», sin contar envites, señas ni las "
            "cartas que piden los demás.")


# --- Valoración ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ValoracionCorte:
    """Qué vale cada respuesta a «¿Mus o corto?» (tantos en milésimas)."""

    veredicto: int
    """1 = dar mus, −1 = cortar, 0 = da igual (:data:`VEREDICTOS`)."""
    intensidad: int
    """2 = clara, 1 = por poco, 0 = da igual (:data:`INTENSIDADES`)."""
    perdidos_mus: int
    """Lo que pierde quien da mus frente a la mejor opción."""
    perdidos_corto: int
    """Lo que pierde quien corta."""


def valorar_decision(decision: int, ventaja: int) -> ValoracionCorte:
    """Valora «¿Mus o corto?» a partir de la decisión del motor y la ventaja de dar mus.

    Args:
        decision: 1 = mus, −1 = cortar, 0 = indiferente (el IC contiene el 0).
        ventaja: dar mus − cortar, en milésimas de tanto.
    """
    if decision == 0 or abs(ventaja) < UMBRAL_IGUAL:
        return ValoracionCorte(0, 0, 0, 0)
    intensidad = 2 if abs(ventaja) >= UMBRAL_CLARA else 1
    if ventaja > 0:
        return ValoracionCorte(1, intensidad, 0, ventaja)
    return ValoracionCorte(-1, intensidad, -ventaja, 0)


@dataclass(frozen=True)
class ValoracionOpcion:
    """Qué vale una forma de descartarse (tantos en milésimas)."""

    indice: int
    """Posición de la opción en el orden canónico de las opciones de la mano."""
    puesto: int
    """0 = la mejor; 1 = la segunda..."""
    si_hay_mus: int
    diferencia: int
    radio: int
    vale: bool
    """La mejor o casi igual que la mejor: no se pierde nada."""
    perdidos: int


def valorar_descartes(si_hay_mus: Sequence[int | None], diferencia: Sequence[int | None],
                      radio: Sequence[int | None]) -> list[ValoracionOpcion]:
    """Valora las formas de descartarse de una mano, de mejor a peor.

    Las tres listas van en el orden canónico de las opciones. Se ordena por
    tantos esperados si hay mus; a igualdad, gana el orden canónico (la
    ordenación es estable, como la de la web). Las opciones sin valor se omiten.
    """
    con_valor = [i for i in range(len(si_hay_mus))
                 if si_hay_mus[i] is not None and diferencia[i] is not None
                 and radio[i] is not None]
    orden = sorted(con_valor, key=lambda i: -si_hay_mus[i])
    resultado = []
    for puesto, i in enumerate(orden):
        d, r = diferencia[i], radio[i]
        vale = puesto == 0 or abs(d) <= r or abs(d) < UMBRAL_DESCARTE
        resultado.append(ValoracionOpcion(i, puesto, si_hay_mus[i], d, r, vale,
                                          0 if vale else abs(d)))
    return resultado


# --- Los datos de una mesa -------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class MesaEntrenador:
    """Lo que el entrenador necesita de un tipo de mesa, leído de los ficheros.

    Los índices de mano son los del manifiesto (los de :class:`mus.tablas.TablaManos`)
    y las posiciones van de 1 a 4.
    """

    id: str
    nombre: str
    manos: tuple[str, ...]
    combinaciones: tuple[int, ...]
    """Combinaciones de cartas de cada mano: su frecuencia es esto entre C(40, 4)."""
    inicio: tuple[int, ...]
    lances: tuple[str, ...]
    decision: dict[str, list[int | None]]
    opciones: dict[str, list[int | None]]
    por_lance: dict[str, list[int | None]]
    escala_probabilidad: int
    escala_tantos: int

    @property
    def n_manos(self) -> int:
        return len(self.manos)

    @property
    def n_opciones(self) -> int:
        return self.inicio[-1]

    def _caso(self, h: int, posicion: int) -> int:
        if not 1 <= posicion <= 4:
            raise ValueError("La posición debe estar entre 1 y 4")
        return h * 4 + posicion - 1

    def corte(self, h: int, posicion: int) -> ValoracionCorte | None:
        """Valoración de «¿Mus o corto?»; ``None`` si esa decisión no está calculada."""
        k = self._caso(h, posicion)
        decision, ventaja = self.decision["decision"][k], self.decision["ventaja"][k]
        return None if ventaja is None or decision is None else valorar_decision(decision, ventaja)

    def ventaja_por_lance(self, h: int, posicion: int) -> list[tuple[int, int]] | None:
        """(ventaja, radio) de dar mus en cada lance, en milésimas; ``None`` si no hay dato."""
        k, n = self._caso(h, posicion), len(self.lances)
        ventajas = self.por_lance["ventaja"][k * n:(k + 1) * n]
        radios = self.por_lance["radio"][k * n:(k + 1) * n]
        if any(v is None for v in ventajas) or any(r is None for r in radios):
            return None
        return list(zip(ventajas, radios))

    def descartes(self, h: int, posicion: int) -> list[ValoracionOpcion]:
        """Valoración de cada forma de descartarse, de mejor a peor."""
        self._caso(h, posicion)
        base = (posicion - 1) * self.n_opciones
        tramo = slice(base + self.inicio[h], base + self.inicio[h + 1])
        return valorar_descartes(self.opciones["si_hay_mus"][tramo],
                                 self.opciones["diferencia"][tramo], self.opciones["radio"][tramo])

    def peso_corte(self, h: int, posicion: int, modo: str) -> int:
        """Peso con que se plantea «¿Mus o corto?» con esa mano y posición.

        - ``mesa``: combinaciones × P(te toca hablar), en diezmilésimas.
        - ``ajustadas``: combinaciones, si hay una opción mejor por menos de
          :data:`UMBRAL_AJUSTADA`; si no, 0.
        """
        v = self.corte(h, posicion)
        k = self._caso(h, posicion)
        if v is None:
            return 0
        if modo == "mesa":
            return self.combinaciones[h] * (self.decision["p_habla"][k] or 0)
        if modo == "ajustadas":
            perdidos = max(v.perdidos_mus, v.perdidos_corto)
            return self.combinaciones[h] if 0 < perdidos < UMBRAL_AJUSTADA else 0
        raise ValueError(f"Modo desconocido: {modo!r}. Válidos: {', '.join(MODOS)}")

    def peso_descarte(self, h: int, posicion: int, modo: str) -> int:
        """Peso con que se plantea «¿Qué tiras?» con esa mano y posición.

        - ``mesa``: combinaciones × P(te toca hablar) × P(dan mus los de después),
          y 0 si el entrenador recomienda cortar con esa mano.
        - ``ajustadas``: combinaciones, si la opción peor de verdad más barata
          cuesta menos de :data:`UMBRAL_AJUSTADA`; si no, 0.
        """
        opciones = self.descartes(h, posicion)
        if not opciones:
            return 0
        if modo == "mesa":
            v = self.corte(h, posicion)
            if v is None or v.veredicto == -1:
                return 0
            k = self._caso(h, posicion)
            return (self.combinaciones[h] * (self.decision["p_habla"][k] or 0)
                    * (self.decision["p_mus_despues"][k] or 0))
        if modo == "ajustadas":
            costes = [o.perdidos for o in opciones if not o.vale]
            return self.combinaciones[h] if costes and min(costes) < UMBRAL_AJUSTADA else 0
        raise ValueError(f"Modo desconocido: {modo!r}. Válidos: {', '.join(MODOS)}")

    def pesos(self, ejercicio: str, modo: str) -> list[int]:
        """Pesos de todas las situaciones, en orden (mano, posición)."""
        if ejercicio not in EJERCICIOS:
            raise ValueError(f"Ejercicio desconocido: {ejercicio!r}")
        peso = self.peso_corte if ejercicio == "corte" else self.peso_descarte
        return [peso(h, p, modo) for h in range(self.n_manos) for p in (1, 2, 3, 4)]

    def decisiones_por_mano(self, ejercicio: str) -> tuple[int, int]:
        """Fracción de las manos de una partida en que se llega a esa decisión, como
        (numerador, denominador): en cada mano se ocupa una de las cuatro posiciones,
        con la misma probabilidad. Con ella se pasa de "tantos perdidos por decisión"
        a "tantos perdidos por mano jugada"."""
        escala = self.escala_probabilidad if ejercicio == "corte" else self.escala_probabilidad ** 2
        return sum(self.pesos(ejercicio, "mesa")), 4 * sum(self.combinaciones) * escala


def cargar_mesa(directorio: str | Path, id_mesa: str | None = None) -> MesaEntrenador:
    """Lee de los ficheros publicados lo que usa el entrenador para un tipo de mesa
    (por defecto, el marcado como tal en el manifiesto)."""
    directorio = Path(directorio)
    m = json.loads((directorio / "manifiesto.json").read_text(encoding="utf-8"))
    info = next((x for x in m["mesas"] if (x["id"] == id_mesa if id_mesa else x["por_defecto"])),
                None)
    if info is None:
        raise ValueError(f"Tipo de mesa desconocido: {id_mesa!r}. Válidos: "
                         f"{', '.join(x['id'] for x in m['mesas'])}")
    f = json.loads((directorio / info["fichero"]).read_text(encoding="utf-8"))
    tabla = construir_tabla()
    textos = tuple(mano.texto(tabla.baraja) for mano in tabla.manos)
    if tuple(m["manos"]) != textos:
        raise ValueError("Las manos de los datos no van en el orden del motor")
    return MesaEntrenador(
        info["id"], info["nombre"], textos, tuple(int(c) for c in tabla.combinaciones),
        tuple(m["descartes"]["inicio"]), tuple(m["lances"]),
        {k: v for k, v in f["decision"].items() if k != "orden"},
        {k: v for k, v in f["opciones"].items() if k != "orden"},
        {k: v for k, v in f["por_lance"].items() if k != "orden"},
        m["escalas"]["probabilidad"], m["escalas"]["tantos"])


def ids_de_mesas(directorio: str | Path) -> list[str]:
    m = json.loads((Path(directorio) / "manifiesto.json").read_text(encoding="utf-8"))
    return [x["id"] for x in m["mesas"]]


# --- Referencia para los tests de la web -------------------------------------------------------


def referencia(directorio: str | Path) -> dict:
    """Valoración y peso de todas las situaciones de cada tipo de mesa.

    Es el contenido de ``web/test/referencia/entrenador.json``. Arrays planos:
    los de ``corte`` y los pesos, en orden (mano, posición); los de las opciones
    de ``descarte``, en orden (posición, opción), con las opciones en el orden
    del manifiesto. ``mejor`` es el índice de la mejor opción dentro de las de
    su mano (−1 si no hay ninguna valorada).
    """
    mesas = {}
    for id_mesa in ids_de_mesas(directorio):
        mesa = cargar_mesa(directorio, id_mesa)
        casos = [(h, p) for h in range(mesa.n_manos) for p in (1, 2, 3, 4)]
        cortes = [mesa.corte(h, p) or ValoracionCorte(0, 0, 0, 0) for h, p in casos]
        perdidos = [0] * (4 * mesa.n_opciones)
        vale = [0] * (4 * mesa.n_opciones)
        mejor = []
        for h, p in casos:
            opciones = mesa.descartes(h, p)
            mejor.append(opciones[0].indice if opciones else -1)
            base = (p - 1) * mesa.n_opciones + mesa.inicio[h]
            for o in opciones:
                perdidos[base + o.indice] = o.perdidos
                vale[base + o.indice] = int(o.vale)
        mesas[id_mesa] = {
            "corte": {
                "veredicto": [c.veredicto for c in cortes],
                "intensidad": [c.intensidad for c in cortes],
                "perdidos_mus": [c.perdidos_mus for c in cortes],
                "perdidos_corto": [c.perdidos_corto for c in cortes],
                "pesos": {modo: mesa.pesos("corte", modo) for modo in MODOS},
                "decisiones_por_mano": list(mesa.decisiones_por_mano("corte")),
            },
            "descarte": {
                "perdidos": perdidos,
                "vale": vale,
                "mejor": mejor,
                "pesos": {modo: mesa.pesos("descarte", modo) for modo in MODOS},
                "decisiones_por_mano": list(mesa.decisiones_por_mano("descarte")),
            },
        }
    return {
        "umbrales": {"igual": UMBRAL_IGUAL, "clara": UMBRAL_CLARA, "descarte": UMBRAL_DESCARTE,
                     "ajustada": UMBRAL_AJUSTADA},
        "veredictos": {str(k): v for k, v in VEREDICTOS.items()},
        "intensidades": {str(k): v for k, v in INTENSIDADES.items()},
        "modos": list(MODOS),
        "orden": {"corte": "mano, posicion", "pesos": "mano, posicion",
                  "descarte": "posicion, opcion (en el orden de manifiesto.descartes)",
                  "mejor": "mano, posicion"},
        "hablan_antes": list(HABLAN_ANTES),
        "contexto": contexto("{mesa}"),
        "mesas": mesas,
    }


# --- Consulta de una mano ----------------------------------------------------------------------


@dataclass(frozen=True)
class OpcionConsulta:
    me_quedo: str
    valoracion: ValoracionOpcion


@dataclass(frozen=True)
class ConsultaEntrenador:
    """Lo que enseña el entrenador para una mano y posición (cifras desescaladas)."""

    mano: str
    posicion: int
    mesa: str
    nombre_mesa: str
    corte: ValoracionCorte | None
    ventaja: float | None
    radio: float | None
    por_lance: dict[str, tuple[float, float]] | None
    p_habla: float | None
    p_mus_despues: float | None
    opciones: list[OpcionConsulta]
    probabilidad: dict[str, dict[str, float]]
    """Por ejercicio y modo: probabilidad de que una situación sorteada sea esta."""


def consultar(directorio: str | Path, mano: str, posicion: int,
              id_mesa: str | None = None) -> ConsultaEntrenador:
    """Valoración de una mano y posición, leída de los ficheros de la web."""
    mesa = cargar_mesa(directorio, id_mesa)
    tabla = construir_tabla()
    texto = parsear_mano(mano).texto(tabla.baraja)
    h = mesa.manos.index(texto)
    k = mesa._caso(h, posicion)
    et, ep = mesa.escala_tantos, mesa.escala_probabilidad

    def leer(nombre: str, escala: int) -> float | None:
        v = mesa.decision[nombre][k]
        return None if v is None else v / escala

    manifiesto = json.loads((Path(directorio) / "manifiesto.json").read_text(encoding="utf-8"))
    conservadas = manifiesto["descartes"]["conservadas"]
    opciones = []
    for o in mesa.descartes(h, posicion):
        codigo, quedo = conservadas[mesa.inicio[h] + o.indice], []
        for r in reversed(range(tabla.baraja.n_rangos)):
            quedo += [tabla.baraja.simbolos[r]] * (codigo // 5 ** r % 5)
        opciones.append(OpcionConsulta(" ".join(quedo) or "nada", o))
    lances = mesa.ventaja_por_lance(h, posicion)
    probabilidad = {}
    for ejercicio in EJERCICIOS:
        probabilidad[ejercicio] = {}
        for modo in MODOS:
            pesos = mesa.pesos(ejercicio, modo)
            probabilidad[ejercicio][modo] = pesos[k] / sum(pesos) if sum(pesos) else 0.0
    return ConsultaEntrenador(
        texto, posicion, mesa.id, mesa.nombre, mesa.corte(h, posicion), leer("ventaja", et),
        leer("radio", et),
        None if lances is None else {l: (v / et, r / et) for l, (v, r) in zip(mesa.lances, lances)},
        leer("p_habla", ep), leer("p_mus_despues", ep), opciones, probabilidad)
