"""Mesas sintéticas y rápidas para los tests de corte y de exportación web.

La tabla de equity de juguete solo premia tener juego, y la política de
descarte es la mejor respuesta a ella: así las simulaciones tardan poco y no
dependen de las tablas de resultados/cache.
"""

import numpy as np

from mus.cortar import MesaConCorte, PoliticaCorte, simular_corte
from mus.descarte import OBJETIVOS, construir_tabla_descartes
from mus.equity import TablaEquity
from mus.evaluacion import Lance
from mus.tras_mus import equity_simulada, mejor_respuesta

TD = construir_tabla_descartes()
TABLA = TD.tabla
CEROS = np.zeros((TABLA.n_manos, 4, 5))
_tantos = CEROS.copy()
_tantos[:, :, list(Lance).index(Lance.JUEGO)] = TABLA.tiene_juego[:, None]
JUEGO = TablaEquity(TABLA, CEROS, _tantos.copy(), CEROS, _tantos)
DESCARTE = mejor_respuesta(TD, JUEGO, OBJETIVOS["tantos"])
CORTA_CON_JUEGO = PoliticaCorte(np.broadcast_to(TABLA.tiene_juego.astype(float), (4, 330)).copy())


def mesa_de(corte: PoliticaCorte, n: int = 50_000) -> MesaConCorte:
    sim = simular_corte(corte, DESCARTE, n, semilla=1)
    return MesaConCorte(TABLA.reglas, OBJETIVOS["tantos"], corte, DESCARTE, sim,
                        equity_simulada(sim.mesa, JUEGO), JUEGO, (), True, n, 1)
