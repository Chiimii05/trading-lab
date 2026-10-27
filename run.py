"""Laboratorio de pruebas de estrategias de trading.

Ejemplos
  python run.py demo                                       # datos sintéticos para probar sin MT5
  python run.py download                                   # descarga el historial M15 de los SYMBOLS del .env
  python run.py test strategies/sma_cross.py               # walk-forward de 2026 de una estrategia
  python run.py test private/strategies/*.py               # varias: cada una y el portfolio en una cuenta
  python run.py test mi_robot.mq5 --mq5-symbol EURUSD      # un experto de MT5 en el probador
  python run.py test a.py b.py --mode backtest --from 2025-01-01 --to 2026-01-01
"""

import argparse
import glob
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

from lab import analysis as an
from lab import data, report
from lab.config import ROOT, settings

# la consola de Windows no siempre usa UTF-8
sys.stdout.reconfigure(encoding="utf-8")


def load_strategy(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT))
    spec.loader.exec_module(mod)
    for attr in ("NAME", "GRID", "run"):
        if not hasattr(mod, attr):
            raise SystemExit(f"{path}: a la estrategia le falta {attr} (mira strategies/sma_cross.py)")
    return mod


def cmd_test(a):
    start = pd.Timestamp(a.date_from, tz="UTC")
    end = pd.Timestamp(a.date_to, tz="UTC")
    files = [f for pat in a.files for f in (glob.glob(pat) or [pat])]
    py_files = [f for f in files if f.endswith(".py")]
    mq_files = [f for f in files if f.lower().endswith((".mq5", ".ex5"))]

    loaded = {s: data.load(s) for s in settings.symbols} if py_files else {}
    frames = {s: df for s, (df, _) in loaded.items()}
    costs = {s: data.round_trip_cost(df, meta) for s, (df, meta) in loaded.items()}

    strategy_tr, chosen = {}, {}
    for f in py_files:
        st = load_strategy(f)
        print(f"▶ {st.NAME}", flush=True)
        if a.mode == "wf":
            tr, ch = an.walk_forward(st, frames, costs, start, end, is_months=a.is_months,
                                     step_months=a.step_months, min_trades=a.min_trades)
            chosen[st.NAME] = ch
        else:
            tr = an.backtest(st, frames, costs, start, end)
        strategy_tr[st.NAME] = tr
    for f in mq_files:
        from lab import mt5_tester
        name = Path(f).stem
        print(f"▶ {name} (probador de MT5)", flush=True)
        rep = mt5_tester.run_tester(f, a.mq5_symbol or settings.symbols[0], start, end, set_file=a.mq5_set)
        strategy_tr[name] = mt5_tester.parse_report(rep, name)

    if not strategy_tr:
        raise SystemExit("No hay estrategias que probar.")
    settings.results_dir.mkdir(exist_ok=True)
    out = settings.results_dir / (a.name + ".html")
    mode = (f"Walk-forward (optimiza {a.is_months} meses, opera {a.step_months})" if a.mode == "wf" and py_files
            else "Backtest con parámetros fijos")
    notes = [
        f"Cada operación arriesga el {settings.risk_pct} % de {settings.capital:,.0f} € hasta su stop, sin interés compuesto.".replace(",", "."),
        "Costes: spread mediano del historial + comisión de " f"{settings.commission_per_lot} por lote ida y vuelta. Sin swaps.",
        "Las señales usan solo velas cerradas; la entrada es a la apertura de la vela siguiente.",
        "Si una vela toca el stop y el objetivo a la vez, se supone el stop (criterio prudente).",
        "La caída máxima se calcula con el beneficio realizado al cierre de cada día.",
        "Un experto .mq5 se prueba en el probador de MT5 con sus propios parámetros (sin walk-forward).",
    ]
    res = report.build(out, a.title, mode, strategy_tr, start, end, chosen, notes)
    for n, tr in strategy_tr.items():
        tr.to_csv(settings.results_dir / f"{a.name}_trades_{Path(n).stem.replace(' ', '_')}.csv", index=False)
    summary = {"verdict": res["verdict"], "metrics": res["metrics"].to_dict(orient="index"),
               "instruments": res["instruments"].to_dict(), "best_worst": res["best_worst"].to_dict(orient="index"),
               "spreads": res["spreads"].to_dict(orient="index"), "montecarlo": res["mc"], "params": chosen}
    (settings.results_dir / f"{a.name}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str),
                                                          encoding="utf-8")
    print(res["metrics"][["Beneficio", "Rentab. %", "Caída máx. %", "Operaciones", "Aciertos %"]].to_string())
    print(f"\nEquilibrio: {res['verdict']}\nInforme: {out}")


def main():
    p = argparse.ArgumentParser(description="Laboratorio de pruebas de estrategias")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download", help="descarga historial M15 desde MT5")
    d.add_argument("symbols", nargs="*")
    sub.add_parser("demo", help="crea datos sintéticos para probar sin MT5 (usa SYMBOLS=DEMO_FX,DEMO_METAL,DEMO_INDEX)")
    t = sub.add_parser("test", help="prueba estrategias .py y/o expertos .mq5")
    t.add_argument("files", nargs="+")
    t.add_argument("--mode", choices=["wf", "backtest"], default="wf")
    t.add_argument("--from", dest="date_from", default="2026-01-01")
    t.add_argument("--to", dest="date_to", default=pd.Timestamp.now().strftime("%Y-%m-%d"))
    t.add_argument("--is-months", type=int, default=24, help="meses de optimización antes de cada tramo")
    t.add_argument("--step-months", type=int, default=1, help="meses que se operan con cada optimización")
    t.add_argument("--min-trades", type=int, default=30)
    t.add_argument("--mq5-symbol", help="símbolo del gráfico para el probador")
    t.add_argument("--mq5-set", help="archivo .set con los parámetros del experto")
    t.add_argument("--name", default="informe")
    t.add_argument("--title", default="Laboratorio de estrategias")
    a = p.parse_args()
    if a.cmd == "download":
        data.download(a.symbols or None)
    elif a.cmd == "demo":
        data.make_demo()
    else:
        cmd_test(a)


if __name__ == "__main__":
    main()
