"""Análisis: walk-forward, métricas, instrumentos, equilibrio, spreads y Monte Carlo.

Todas las funciones trabajan con un DataFrame de operaciones con estas columnas:
  strategy, sym, entry_t, exit_t, dir, pnl (dinero, costes incluidos), cost_pnl (dinero de costes)
"""

import itertools

import numpy as np
import pandas as pd

from .config import settings

SPREAD_MULTS = [0.5, 1.0, 1.5, 2.0, 3.0]


# ------------------------------------------------------------------ operaciones
def trades_frame(trades, strategy):
    """Lista de Trade (en R) → DataFrame en dinero con el riesgo por operación del .env."""
    risk = settings.capital * settings.risk_pct / 100
    if not trades:
        return pd.DataFrame(columns=["strategy", "sym", "entry_t", "exit_t", "dir", "pnl", "cost_pnl"])
    df = pd.DataFrame([vars(x) for x in trades])
    df["strategy"] = strategy
    df["pnl"] = df.pop("r") * risk
    df["cost_pnl"] = df.pop("cost_r") * risk
    return df[["strategy", "sym", "entry_t", "exit_t", "dir", "pnl", "cost_pnl"]]


def score(tr, min_trades=30):
    """Criterio de optimización: beneficio / caída máxima (como un OnTester típico)."""
    if len(tr) < min_trades:
        return -np.inf
    eq = tr.sort_values("exit_t").pnl.cumsum()
    dd = (eq.cummax() - eq).max()
    return eq.iloc[-1] / max(dd, 1e-9 + settings.capital * 0.001)


# ------------------------------------------------------------------ walk-forward
def walk_forward(strategy, data, costs, start, end, is_months=24, step_months=1, min_trades=30, log=print):
    """Optimiza en los `is_months` anteriores a cada tramo y opera ese tramo con los mejores parámetros.

    Cada combinación se simula una sola vez sobre toda la historia (las señales solo usan el pasado)
    y después se trocea por fechas de entrada; así el walk-forward es rápido y sin mirar al futuro.
    """
    grid = strategy.GRID
    combos = [dict(zip(grid, v)) for v in itertools.product(*grid.values())]
    runs = []
    for p in combos:
        tr = pd.concat([trades_frame(strategy.run(sym, df, costs[sym], **p), strategy.NAME)
                        for sym, df in data.items()], ignore_index=True)
        runs.append((p, tr))
        log(f"   {strategy.NAME} {p}: {len(tr)} operaciones")
    oos, chosen = [], []
    for m0 in pd.date_range(start, end, freq=f"{step_months}MS"):
        m1 = min(m0 + pd.DateOffset(months=step_months), end)
        is0 = m0 - pd.DateOffset(months=is_months)
        p, tr = max(runs, key=lambda pr: score(pr[1][(pr[1].entry_t >= is0) & (pr[1].entry_t < m0)], min_trades))
        oos.append(tr[(tr.entry_t >= m0) & (tr.entry_t < m1)])
        chosen.append({"desde": m0.strftime("%Y-%m-%d"), **p})
    return pd.concat(oos, ignore_index=True), chosen


def backtest(strategy, data, costs, start, end, params=None):
    p = params or getattr(strategy, "DEFAULTS", {})
    tr = pd.concat([trades_frame(strategy.run(sym, df, costs[sym], **p), strategy.NAME)
                    for sym, df in data.items()], ignore_index=True)
    return tr[(tr.entry_t >= start) & (tr.entry_t < end)]


# ------------------------------------------------------------------ métricas
def daily(tr, start, end):
    days = pd.date_range(start.normalize(), (end - pd.Timedelta(seconds=1)).normalize(), freq="D")
    if tr.empty:
        return pd.Series(0.0, index=days)
    return tr.pnl.groupby(pd.to_datetime(tr.exit_t).dt.normalize()).sum().reindex(days, fill_value=0.0)


def metrics(tr, start, end):
    p = daily(tr, start, end)
    eq = settings.capital + p.cumsum()
    dd_pct = float(((eq.cummax() - eq) / eq.cummax()).max() * 100)
    total = float(p.sum())
    wk = p.resample("W").sum()
    sharpe = float(wk.mean() / wk.std() * np.sqrt(52)) if wk.std() > 0 else 0.0
    gp, gl = tr.pnl[tr.pnl > 0].sum(), -tr.pnl[tr.pnl < 0].sum()
    months = p.resample("MS").sum()
    return {
        "beneficio": round(total, 2),
        "rentabilidad_pct": round(total / settings.capital * 100, 2),
        "caida_max_pct": round(dd_pct, 2),
        "rent_caida": round(total / settings.capital * 100 / dd_pct, 2) if dd_pct > 0 else None,
        "sharpe_semanal_anualizado": round(sharpe, 2),
        "factor_beneficio": round(gp / gl, 2) if gl > 0 else None,
        "operaciones": int(len(tr)),
        "aciertos_pct": round(float((tr.pnl > 0).mean() * 100), 1) if len(tr) else 0.0,
        "meses_positivos": f"{int((months > 0).sum())}/{len(months)}",
        "costes": round(float(tr.cost_pnl.sum()), 2),
    }


def by_instrument(tr):
    if tr.empty:
        return pd.DataFrame()
    g = tr.groupby("sym").pnl
    out = pd.DataFrame({"beneficio": g.sum().round(2), "operaciones": g.size(),
                        "aciertos_pct": (g.apply(lambda s: (s > 0).mean() * 100)).round(1)})
    return out.sort_values("beneficio", ascending=False)


def by_month(tr, start, end):
    p = daily(tr, start, end)
    return p.resample("MS").sum().round(2)


# ------------------------------------------------------------------ equilibrio
def balance(portfolio_tr, strategy_tr, start, end):
    """¿Es un resultado equilibrado? Reglas simples y explicadas, sin caja negra."""
    inst = by_instrument(portfolio_tr)
    checks = []
    if not inst.empty and inst.beneficio.clip(lower=0).sum() > 0:
        pos = inst.beneficio.clip(lower=0)
        top_share = float(pos.max() / pos.sum() * 100)
        checks.append(("Ningún instrumento aporta más del 40 % del beneficio",
                       top_share <= 40, f"el mejor aporta el {top_share:.0f} %"))
        n_pos = int((inst.beneficio > 0).sum())
        checks.append(("Al menos la mitad de los instrumentos ganan",
                       n_pos >= len(inst) / 2, f"{n_pos} de {len(inst)} en positivo"))
    strat_pnl = {k: float(v.pnl.sum()) for k, v in strategy_tr.items()}
    pos_s = {k: max(v, 0) for k, v in strat_pnl.items()}
    if len(strat_pnl) > 1 and sum(pos_s.values()) > 0:
        top_s = max(pos_s.values()) / sum(pos_s.values()) * 100
        checks.append(("Ninguna estrategia aporta más del 60 % del beneficio",
                       top_s <= 60, f"la mejor aporta el {top_s:.0f} %"))
        wk = pd.DataFrame({k: daily(v, start, end).resample("W").sum() for k, v in strategy_tr.items()})
        corr = wk.corr().where(~np.eye(len(wk.columns), dtype=bool)).stack().mean()
        checks.append(("Correlación semanal media entre estrategias por debajo de 0,3",
                       bool(corr < 0.3), f"correlación media {corr:.2f}"))
    m = by_month(portfolio_tr, start, end)
    if len(m):
        share = float((m > 0).mean() * 100)
        checks.append(("Más de la mitad de los meses en positivo", share > 50, f"{share:.0f} % de meses positivos"))
    ok = sum(c[1] for c in checks)
    verdict = ("Equilibrado" if ok == len(checks) else
               "Bastante equilibrado" if ok >= len(checks) - 1 else "Poco equilibrado")
    return verdict, checks


# ------------------------------------------------------------------ spreads
def spread_table(strategy_tr, portfolio_tr, start, end):
    """Resultado con el coste multiplicado (×0,5 … ×3) y multiplicador en el que deja de ganar."""
    rows = {}
    for name, tr in {**strategy_tr, "Portfolio": portfolio_tr}.items():
        base, cost = float(tr.pnl.sum()), float(tr.cost_pnl.sum())
        row = {f"×{m:g}": round(base - (m - 1) * cost, 2) for m in SPREAD_MULTS}
        row["deja_de_ganar_en"] = (f"×{1 + base / cost:.1f}" if cost > 0 and base > 0 else "ya pierde" if base <= 0 else "—")
        rows[name] = row
    return pd.DataFrame(rows).T


# ------------------------------------------------------------------ Monte Carlo
def _max_dd(paths):
    eq = settings.capital + np.cumsum(paths, axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.full((len(eq), 1), settings.capital), eq], axis=1), axis=1)[:, 1:]
    return ((peak - eq) / peak).max(axis=1) * 100


def monte_carlo(tr, start, end, sims=5000, block=5, seed=7):
    """Tres pruebas sobre la serie diaria (mantiene la correlación entre estrategias del mismo día):

    - remuestreo por bloques de `block` días con reemplazo: ¿qué rango de resultados es razonable?
    - orden barajado: mismo beneficio total, ¿qué caídas podrían haber salido?
    - operaciones perdidas: se quita al azar el 10 % de las operaciones (fallos de conexión, rechazos…)
    """
    rng = np.random.default_rng(seed)
    p = daily(tr, start, end).to_numpy()
    n = len(p)
    if n == 0 or tr.empty:
        return None
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, max(n - block, 1), size=(sims, nb))
    boot = p[(starts[:, :, None] + np.arange(block)).reshape(sims, -1)[:, :n]]
    shuf = rng.permuted(np.tile(p, (sims, 1)), axis=1)
    keep = rng.random((sims, len(tr))) > 0.10
    skipped = (keep * tr.pnl.to_numpy()).sum(axis=1)

    def pct(a):
        return {f"p{q}": round(float(np.percentile(a, q)), 2) for q in (5, 25, 50, 75, 95)}

    boot_total, boot_dd = boot.sum(axis=1), _max_dd(boot)
    return {
        "remuestreo_beneficio": pct(boot_total),
        "remuestreo_caida_max_pct": pct(boot_dd),
        "prob_perder_pct": round(float((boot_total < 0).mean() * 100), 1),
        "prob_caida_mayor_10_pct": round(float((boot_dd > 10).mean() * 100), 1),
        "barajado_caida_max_pct": pct(_max_dd(shuf)),
        "sin_10pct_operaciones_beneficio": pct(skipped),
        "_curvas": np.cumsum(boot[:200], axis=1),   # para el gráfico de abanico
        "_totales": boot_total,
    }
