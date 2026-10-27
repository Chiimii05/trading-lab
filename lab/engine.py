"""Motor de simulación: operaciones, indicadores básicos y un simulador genérico con stop.

Convenciones
- Cada operación arriesga un % fijo del capital inicial hasta su stop (sin interés compuesto),
  así se pueden sumar estrategias e instrumentos en una misma cuenta.
- El resultado se mide en R: (salida - entrada) * dirección / distancia al stop, menos el coste.
- Las señales se calculan con velas cerradas y se entra a la apertura de la vela siguiente.
- Un stop tocado se llena a su precio, o a la apertura si el precio salta por encima.
  Si la vela de entrada ya toca el stop, se da por perdida (criterio prudente).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Trade:
    sym: str
    entry_t: pd.Timestamp
    exit_t: pd.Timestamp
    dir: int
    r: float          # resultado en R con costes
    cost_r: float     # parte del resultado que son costes (en R), para simular otros spreads


def make_trade(sym, t_in, t_out, d, entry, exit_px, dist, cost):
    return Trade(sym, t_in, t_out, d, ((exit_px - entry) * d - cost) / dist, cost / dist)


def resample(m15, rule):
    """Cambia de marco temporal. El día va de 22:00 a 22:00 UTC (cierre de Nueva York)."""
    # con fechas UTC, pandas solo aplica el desfase si el periodo va en horas ("24h"), no en días
    if rule == "1D":
        rule, kw = "24h", {"origin": "epoch", "offset": "22h"}
    else:
        kw = {}
    return m15.resample(rule, **kw).agg({"open": "first", "high": "max", "low": "min",
                                         "close": "last"}).dropna()


def atr(df, n):
    pc = df.close.shift()
    tr = np.maximum(df.high - df.low, np.maximum((df.high - pc).abs(), (df.low - pc).abs()))
    return tr.rolling(n).mean()


def local_hours(idx, tz):
    """Hora decimal y día en una zona horaria (p. ej. 'Europe/London')."""
    loc = idx.tz_convert(tz)
    return np.asarray(loc.hour + loc.minute / 60.0), np.asarray(loc.normalize())


def run_stops(sym, df, cost, entries, stop_fn, trail_fn=None, max_bars=None, exit_fn=None, financing=0.0):
    """Simulador genérico, una posición a la vez por símbolo.

    entries:  array con +1 / -1 donde la señal aparece al CIERRE de esa vela.
    stop_fn(i, d, entry) -> distancia inicial al stop (en precio).
    trail_fn(k, d, stop) -> nuevo stop tras el cierre de la vela k (opcional, stops que siguen al precio).
    exit_fn(k, d) -> True para cerrar a la apertura de la vela k (opcional, p. ej. cierre horario).
    max_bars: cierre al cierre de la vela tras N velas (opcional).
    financing: coste anual de mantener la posición abierta (swap), en fracción del precio, por noche (opcional).
    """
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    t, n = df.index, len(df)
    trades, i = [], 0
    while i < n - 1:
        d = int(entries[i])
        if d == 0:
            i += 1
            continue
        j = i + 1
        entry = o[j]
        dist = stop_fn(i, d, entry)
        if not np.isfinite(dist) or dist <= 0:
            i += 1
            continue
        stop = entry - d * dist
        exit_px, k = None, j
        while k < n:
            if exit_fn and k > j and exit_fn(k, d):
                exit_px = o[k]
                break
            if (d > 0 and l[k] <= stop) or (d < 0 and h[k] >= stop):
                exit_px = stop if k == j else (min(o[k], stop) if d > 0 else max(o[k], stop))
                break
            if trail_fn:
                stop = trail_fn(k, d, stop)
            if max_bars and k - j + 1 >= max_bars:
                exit_px = c[k]
                break
            k += 1
        if exit_px is None:
            exit_px, k = c[n - 1], n - 1
        nights = (t[k] - t[j]).days if financing else 0
        trades.append(make_trade(sym, t[j], t[k], d, entry, exit_px, dist, cost + entry * financing * nights / 365))
        i = k   # la señal de la vela de salida ya puede abrir la siguiente
    return trades
