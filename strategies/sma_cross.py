"""Ejemplo: cruce de medias en H4 con stop por ATR que sigue al precio.

Plantilla para tus estrategias: un módulo con NAME, GRID, DEFAULTS y una función
run(sym, m15, cost, **params) que devuelve una lista de lab.engine.Trade.
"""

import numpy as np

from lab.engine import atr, resample, run_stops

NAME = "Ejemplo cruce de medias"
GRID = {"fast": [10, 20], "slow": [50, 100], "k": [2.0, 3.0]}
DEFAULTS = {"fast": 20, "slow": 100, "k": 3.0}


def run(sym, m15, cost, fast=20, slow=100, k=3.0):
    h4 = resample(m15, "4h")
    f, s = h4.close.rolling(fast).mean(), h4.close.rolling(slow).mean()
    above = (f > s).astype(int)
    cross = above.diff().fillna(0).to_numpy()          # +1 cruce al alza, -1 a la baja
    a, c = atr(h4, 14).to_numpy(), h4.close.to_numpy()

    def trail(i, d, stop):
        return max(stop, c[i] - k * a[i]) if d > 0 else min(stop, c[i] + k * a[i])

    return run_stops(sym, h4, cost, np.sign(cross), lambda i, d, e: k * a[i], trail_fn=trail)
