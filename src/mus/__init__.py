"""Mus Analytics: motor de estadísticas y estrategia para el mus.

Módulos:
    reglas: configuración de reglas (variante, orden del juego, puntuación).
    cartas: baraja y representación canónica de manos.
    evaluacion: claves de cada lance y resolución entre 4 jugadores.
    tablas: evaluaciones precalculadas de todas las manos distintas.
    simulacion: reparto Monte Carlo vectorizado e intervalos de confianza.
    analisis: distribuciones exactas, verificación y exportación.
"""

from mus.cartas import Mano, enumerar_manos, parsear_mano
from mus.evaluacion import Lance, Pares, resolver_lance, resolver_mano
from mus.reglas import REGLAS_POR_DEFECTO, Puntuacion, ReglasMus, Variante
from mus.tablas import TablaManos, construir_tabla

__all__ = [
    "Lance", "Mano", "Pares", "Puntuacion", "REGLAS_POR_DEFECTO", "ReglasMus",
    "TablaManos", "Variante", "construir_tabla", "enumerar_manos", "parsear_mano",
    "resolver_lance", "resolver_mano",
]

__version__ = "0.1.0"
