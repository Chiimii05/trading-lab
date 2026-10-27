"""Ejemplo: RSI(2) extremo en H1 a favor de la media de 200, salida al volver o tras N velas."""

import numpy as np

from lab.engine import atr, resample, run_stops

NAME = "Ejemplo RSI(2)"
GRID = {"level": [5, 10], "k": [1.5, 2.5], "max_bars": [12, 24]}
DEFAULTS = {"level": 10, "k": 2.0, "max_bars": 24}


def rsi(close, n):
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / down)


def run(sym, m15, cost, level=10, k=2.0, max_bars=24):
    h1 = resample(m15, "1h")
    r = rsi(h1.close, 2)
    trend = h1.close > h1.close.rolling(200).mean()
    ent = np.where(trend & (r < level), 1, np.where(~trend & (r > 100 - level), -1, 0))
    a = atr(h1, 14).to_numpy()
    return run_stops(sym, h1, cost, ent, lambda i, d, e: k * a[i], max_bars=max_bars)
