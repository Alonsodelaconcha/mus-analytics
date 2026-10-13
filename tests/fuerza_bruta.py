"""Equity por fuerza bruta: referencia independiente del motor exacto.

Recorre todas las ternas de manos (X, Y, Z) de los otros tres asientos en
orden de asiento (no "compañero primero", como el motor), con pesos
∏ C(n_r, k_r) calculados directamente, y decide ganadores y tantos con las
funciones vectorizadas de :mod:`mus.simulacion`, ya contrastadas con la
resolución escalar. No comparte con :mod:`mus.equity` ni la enumeración ni
la lógica de umbrales.
"""

from math import comb

import numpy as np

from mus.evaluacion import Lance, pareja_de
from mus.simulacion import ganadores_lance, tantos_lance
from mus.tablas import TablaManos


def _pesos(mazos: np.ndarray, conteos: np.ndarray) -> np.ndarray:
    """w[i, j] = ∏_r C(mazos[i, r], conteos[j, r]); 0 si algún mazo es negativo."""
    t = np.array([[comb(d, k) for k in range(5)] for d in range(9)], dtype=np.float64)
    validos = (mazos >= 0).all(axis=1)
    m = np.clip(mazos, 0, None)
    w = np.prod(t[m[:, None, :], conteos[None, :, :]], axis=2)
    return w * validos[:, None]


def equity_fuerza_bruta(tabla: TablaManos, heroe: int, posicion: int,
                        mascaras: dict[int, np.ndarray] | None = None) -> dict[Lance, tuple]:
    """(p_se_juega, p_gana_individual, p_gana_pareja, tantos_netos) por lance."""
    mascaras = mascaras or {}
    conteos = tabla.conteos.astype(np.int64)
    n = tabla.n_manos
    otros = [s for s in (1, 2, 3, 4) if s != posicion]
    m = [mascaras.get(s, np.ones(n)) for s in otros]
    restante = np.array(tabla.baraja.copias) - conteos[heroe]
    w_x = _pesos(restante[None, :], conteos)[0] * m[0]

    acumulado = {l: np.zeros(4) for l in Lance}
    total = 0.0
    mi_pareja = pareja_de(posicion)
    for x in np.nonzero(w_x)[0]:
        mazo2 = restante - conteos[x]
        w_y = _pesos(mazo2[None, :], conteos)[0] * m[1]
        mazo3 = mazo2[None, :] - conteos                         # (Y, R)
        w = w_x[x] * w_y[:, None] * _pesos(mazo3, conteos) * m[2][None, :]
        ys, zs = np.nonzero(w)
        pesos = w[ys, zs]
        repartos = np.empty((len(ys), 4), dtype=np.int64)
        repartos[:, posicion - 1] = heroe
        repartos[:, otros[0] - 1] = x
        repartos[:, otros[1] - 1] = ys
        repartos[:, otros[2] - 1] = zs
        total += pesos.sum()
        for lance in Lance:
            g = ganadores_lance(tabla, repartos, lance)
            t = tantos_lance(tabla, repartos, lance, g)
            nuestra = (g > 0) & np.array([pareja_de(int(s)) == mi_pareja if s else False
                                          for s in range(5)])[g]
            acumulado[lance] += [pesos[g > 0].sum(), pesos[g == posicion].sum(),
                                 pesos[nuestra].sum(), (pesos * np.where(nuestra, t, -t)).sum()]
    return {l: tuple(v / total) for l, v in acumulado.items()}


def p_habla_exacta(tabla: TablaManos, heroe: int, posicion: int, dan_mus: np.ndarray) -> float:
    """P(dan mus todos los asientos anteriores a ``posicion`` | mi mano), exacta.

    ``dan_mus[s, h]`` = P(el asiento s + 1 da mus con la mano h). Recorre las
    manos de los asientos anteriores con sus pesos combinatorios (las cartas
    que ya tienen los demás no se pueden repetir).
    """
    if posicion == 1:
        return 1.0
    conteos = tabla.conteos.astype(np.int64)
    restante = np.array(tabla.baraja.copias) - conteos[heroe]
    w_x = _pesos(restante[None, :], conteos)[0]
    if posicion == 2:
        return float(w_x @ dan_mus[0] / w_x.sum())
    numerador = denominador = 0.0
    for x in np.nonzero(w_x)[0]:
        mazo2 = restante - conteos[x]
        w_y = _pesos(mazo2[None, :], conteos)[0]
        if posicion == 3:
            numerador += w_x[x] * dan_mus[0, x] * (w_y @ dan_mus[1])
            denominador += w_x[x] * w_y.sum()
        else:
            w_yz = w_y[:, None] * _pesos(mazo2[None, :] - conteos, conteos)
            numerador += w_x[x] * dan_mus[0, x] * (dan_mus[1] @ w_yz @ dan_mus[2])
            denominador += w_x[x] * w_yz.sum()
    return float(numerador / denominador)
