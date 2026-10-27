"""Configuración: lee el .env y deja los ajustes en un único objeto."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _list(name, default=""):
    return [s.strip() for s in os.getenv(name, default).split(",") if s.strip()]


@dataclass
class Settings:
    mt5_login: int | None = int(os.getenv("MT5_LOGIN")) if os.getenv("MT5_LOGIN") else None
    mt5_password: str = os.getenv("MT5_PASSWORD", "")
    mt5_server: str = os.getenv("MT5_SERVER", "")
    mt5_path: str = os.getenv("MT5_TERMINAL_PATH", "")
    symbols: list = field(default_factory=lambda: _list("SYMBOLS", "EURUSD,USDJPY,XAUUSD"))
    history_from: str = os.getenv("HISTORY_FROM", "2022-01-01")
    # Hora del servidor: UTC+2 en invierno y +3 cuando EE. UU. cambia de hora (lo habitual en brokers "NY close")
    server_utc_offset: int = int(os.getenv("SERVER_UTC_OFFSET", "2"))
    server_us_dst: bool = os.getenv("SERVER_US_DST", "true").lower() == "true"
    # Comisión de ida y vuelta por lote, en la divisa de la cuenta
    commission_per_lot: float = float(os.getenv("COMMISSION_PER_LOT", "5"))
    # Spread mínimo supuesto (puntos): algunos brokers guardan 0 en el historial aunque el real no lo sea
    min_spread_points: float = float(os.getenv("MIN_SPREAD_POINTS", "2"))
    currency: str = os.getenv("CURRENCY", "USD")
    capital: float = float(os.getenv("CAPITAL", "10000"))
    risk_pct: float = float(os.getenv("RISK_PCT", "0.5"))

    data_dir: Path = ROOT / "data"
    results_dir: Path = ROOT / "results"


settings = Settings()
