"""Datos: descarga velas M15 desde MetaTrader 5 y las guarda en caché (data/).

Cada símbolo genera:
  data/<SYM>_M15.csv.gz   hora UTC, open, high, low, close, spread (en puntos)
  data/<SYM>_meta.json    punto, tamaño y valor del tick, dígitos (para los costes)
"""

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .config import settings


def server_to_utc(idx):
    """Pasa la hora del servidor de MT5 a UTC según SERVER_UTC_OFFSET y SERVER_US_DST."""
    naive = pd.DatetimeIndex(idx)
    off = np.full(len(naive), settings.server_utc_offset, dtype=float)
    if settings.server_us_dst:
        years = sorted(set(naive.year))
        for y in years:
            mar = pd.Timestamp(y, 3, 1)
            s = mar + pd.Timedelta(days=(6 - mar.weekday()) % 7 + 7)
            nov = pd.Timestamp(y, 11, 1)
            e = nov + pd.Timedelta(days=(6 - nov.weekday()) % 7)
            off[(naive >= s) & (naive < e)] += 1
    return (naive - pd.to_timedelta(off, unit="h")).tz_localize("UTC")


def connect():
    import MetaTrader5 as mt5

    kw = {}
    if settings.mt5_path:
        kw["path"] = settings.mt5_path
    if settings.mt5_login:
        kw.update(login=settings.mt5_login, password=settings.mt5_password, server=settings.mt5_server)
    if not mt5.initialize(**kw):
        raise SystemExit(f"No se pudo conectar con MT5: {mt5.last_error()}. Revisa el .env.")
    return mt5


def download(symbols=None, until=None):
    """Descarga (o completa) el historial M15 de cada símbolo."""
    mt5 = connect()
    settings.data_dir.mkdir(exist_ok=True)
    start = datetime.fromisoformat(settings.history_from).replace(tzinfo=timezone.utc)
    end = until or datetime.now(timezone.utc)
    try:
        for sym in symbols or settings.symbols:
            if not mt5.symbol_select(sym, True):
                raise SystemExit(f"Símbolo desconocido en tu broker: {sym}")
            info = mt5.symbol_info(sym)
            # MT5 limita cada petición: se pide por trozos de 6 meses
            parts, t0 = [], start
            while t0 < end:
                t1 = min(t0 + pd.DateOffset(months=6), end)
                r = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M15, t0, t1)
                if r is not None and len(r):
                    parts.append(pd.DataFrame(r))
                t0 = t1
            if not parts:
                raise SystemExit(f"{sym}: MT5 no devolvió historial ({mt5.last_error()}). "
                                 "Abre el gráfico M15 del símbolo en MT5 para que lo descargue y repite.")
            df = pd.concat(parts).drop_duplicates("time").sort_values("time")
            df.index = server_to_utc(pd.to_datetime(df.pop("time"), unit="s"))
            df = df[["open", "high", "low", "close", "spread"]]
            df.to_csv(settings.data_dir / f"{sym}_M15.csv.gz")
            meta = {"point": info.point, "digits": info.digits, "tick_size": info.trade_tick_size,
                    "tick_value": info.trade_tick_value, "contract_size": info.trade_contract_size,
                    "currency_profit": info.currency_profit}
            (settings.data_dir / f"{sym}_meta.json").write_text(json.dumps(meta, indent=2))
            print(f"{sym}: {len(df)} velas M15 ({df.index[0]:%Y-%m-%d} → {df.index[-1]:%Y-%m-%d}), "
                  f"spread mediano {df.spread.median():.0f} puntos", flush=True)
    finally:
        mt5.shutdown()


def load(sym):
    df = pd.read_csv(settings.data_dir / f"{sym}_M15.csv.gz", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    meta = json.loads((settings.data_dir / f"{sym}_meta.json").read_text())
    return df, meta


def round_trip_cost(df, meta):
    """Coste de ida y vuelta en precio: spread prudente + comisión por lote convertida a precio.

    MT5 guarda en cada vela el spread mínimo del periodo, que en cuentas de spread bajo suele ser 0;
    por eso se toma el mayor entre la media, el percentil 75 y MIN_SPREAD_POINTS.
    """
    pts = max(float(df.spread.mean()), float(df.spread.quantile(0.75)), settings.min_spread_points)
    spread = pts * meta["point"]
    per_price_unit = meta["tick_value"] / meta["tick_size"]   # dinero por 1 unidad de precio y lote
    commission = settings.commission_per_lot / per_price_unit if per_price_unit > 0 else 0.0
    return spread + commission


def make_demo(symbols=("DEMO_FX", "DEMO_METAL", "DEMO_INDEX"), years=4, seed=1):
    """Datos sintéticos (paseo aleatorio con rachas de volatilidad) para probar el laboratorio sin MT5."""
    rng = np.random.default_rng(seed)
    settings.data_dir.mkdir(exist_ok=True)
    end = pd.Timestamp.now(tz="UTC").floor("D")
    idx = pd.date_range(end - pd.DateOffset(years=years), end, freq="15min")
    idx = idx[idx.day_of_week < 5]
    specs = {"DEMO_FX": (1.10, 0.00008, 1e-5), "DEMO_METAL": (2000.0, 0.0012, 0.01), "DEMO_INDEX": (15000.0, 0.0011, 0.1)}
    for sym in symbols:
        p0, vol, point = specs.get(sym, (100.0, 0.001, 0.01))
        regime = np.exp(np.convolve(rng.normal(0, 0.35, len(idx)), np.ones(400) / 20, mode="same"))
        ret = rng.standard_t(4, len(idx)) * vol * regime / np.sqrt(2)
        close = p0 * np.exp(np.cumsum(ret))
        openp = np.r_[close[0], close[:-1]]
        wick = np.abs(rng.normal(0, vol * 0.6, len(idx))) * close
        df = pd.DataFrame({"open": openp, "high": np.maximum(openp, close) + wick,
                           "low": np.minimum(openp, close) - wick, "close": close,
                           "spread": rng.integers(8, 20, len(idx))}, index=idx)
        df.to_csv(settings.data_dir / f"{sym}_M15.csv.gz")
        meta = {"point": point, "digits": 5, "tick_size": point, "tick_value": 1.0, "contract_size": 1,
                "currency_profit": "USD"}
        (settings.data_dir / f"{sym}_meta.json").write_text(json.dumps(meta, indent=2))
        print(f"{sym}: {len(df)} velas M15 sintéticas")
