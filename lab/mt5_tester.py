"""Prueba un experto .mq5 (o .ex5) con el probador de estrategias de MetaTrader 5.

1. Compila el .mq5 con MetaEditor y lo copia a MQL5/Experts/Lab/ del terminal.
2. Lanza terminal64.exe con un archivo de configuración [Tester] y espera a que termine.
3. Lee el informe HTML y convierte las operaciones al formato del laboratorio
   (strategy, sym, entry_t, exit_t, dir, pnl, cost_pnl) para usar el mismo análisis.

MT5 tiene que estar CERRADO: el probador no arranca desde la línea de comandos con el terminal abierto.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from .config import settings
from .data import server_to_utc


def _terminal_paths():
    exe = Path(settings.mt5_path) if settings.mt5_path else None
    roots = Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal"
    for d in roots.glob("*"):
        origin = d / "origin.txt"
        if not origin.exists():
            continue
        install = Path(origin.read_bytes().decode("utf-16", errors="ignore").strip())
        if exe is None or install == exe.parent:
            return install / "terminal64.exe", install / "MetaEditor64.exe", d
    raise SystemExit("No encuentro el terminal de MT5. Pon MT5_TERMINAL_PATH en el .env.")


def _running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq terminal64.exe"], capture_output=True, text=True).stdout
    return "terminal64.exe" in out


def compile_expert(src, editor, data_dir):
    dest_dir = data_dir / "MQL5" / "Experts" / "Lab"
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = Path(src)
    if src.suffix.lower() == ".ex5":
        shutil.copy2(src, dest_dir / src.name)
        return dest_dir / src.name
    dst = dest_dir / src.name
    shutil.copy2(src, dst)
    log = dest_dir / (src.stem + ".compile.log")
    subprocess.run([str(editor), f"/compile:{dst}", f"/log:{log}"], capture_output=True)
    ex5 = dst.with_suffix(".ex5")
    text = log.read_bytes().decode("utf-16", errors="ignore") if log.exists() else ""
    if not ex5.exists() or re.search(r"\b[1-9]\d* errors?\b", text):
        raise SystemExit(f"No compila {src.name}:\n{text[-2000:]}")
    return ex5


def run_tester(src, symbol, start, end, set_file=None, model=1, deposit=None, timeout=3600):
    """Lanza el probador. model: 0 todos los ticks, 1 OHLC de 1 minuto, 4 ticks reales."""
    terminal, editor, data_dir = _terminal_paths()
    if _running():
        raise SystemExit("Cierra MetaTrader 5 antes de lanzar el probador desde el laboratorio.")
    ex5 = compile_expert(src, editor, data_dir)
    lines = ["[Common]"]
    if settings.mt5_login:
        lines += [f"Login={settings.mt5_login}", f"Password={settings.mt5_password}", f"Server={settings.mt5_server}"]
    lines += ["[Tester]", f"Expert=Lab\\{ex5.name}", f"Symbol={symbol}", "Period=M15", f"Model={model}",
              f"FromDate={start:%Y.%m.%d}", f"ToDate={end:%Y.%m.%d}", "ForwardMode=0",
              f"Deposit={int(deposit or settings.capital)}", "Optimization=0", "Visual=0",
              "Report=lab_report", "ReplaceReport=1", "ShutdownTerminal=1"]
    if set_file:
        tester_dir = data_dir / "MQL5" / "Profiles" / "Tester"
        tester_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(set_file, tester_dir / Path(set_file).name)
        lines.append(f"ExpertParameters={Path(set_file).name}")
    ini = settings.results_dir / "tester.ini"
    settings.results_dir.mkdir(exist_ok=True)
    # el .ini lleva la contraseña: se escribe, se usa y se borra
    ini.write_text("\n".join(lines), encoding="utf-16")
    try:
        subprocess.run([str(terminal), f"/config:{ini}"], timeout=timeout)
    finally:
        ini.unlink(missing_ok=True)
    for name in ("lab_report.htm", "lab_report.html"):
        for base in (data_dir, terminal.parent):
            if (base / name).exists():
                return base / name
    raise SystemExit("El probador no generó informe. Mira el diario del probador en MT5.")


def parse_report(path, strategy_name):
    """Convierte la tabla de operaciones (deals) del informe en operaciones cerradas."""
    raw = Path(path).read_bytes()
    html = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", errors="ignore")
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S | re.I):
        cells = [re.sub(r"<[^>]+>", "", c).replace("\xa0", " ").strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)]
        # fila de operación: Hora, Operación, Símbolo, Tipo, Dirección, Volumen, Precio, Orden,
        # Comisión, Swap, Beneficio, Balance, Comentario
        if len(cells) >= 12 and re.match(r"\d{4}\.\d{2}\.\d{2}", cells[0]) and cells[4].lower() in ("in", "out", "in/out"):
            rows.append(cells[:13])
    if not rows:
        raise SystemExit("No encuentro operaciones en el informe del probador.")
    num = lambda s: float(s.replace(" ", "") or 0)
    deals = pd.DataFrame([{"t": r[0], "sym": r[2], "type": r[3].lower(), "dir": r[4].lower(), "vol": num(r[5]),
                           "price": num(r[6]), "comm": num(r[8]), "swap": num(r[9]), "profit": num(r[10])}
                          for r in rows])
    deals["t"] = server_to_utc(pd.to_datetime(deals.t, format="%Y.%m.%d %H:%M:%S"))

    spreads = {}
    for sym in deals.sym.unique():
        meta_f, data_f = settings.data_dir / f"{sym}_meta.json", settings.data_dir / f"{sym}_M15.csv.gz"
        if meta_f.exists() and data_f.exists():
            meta = json.loads(meta_f.read_text())
            med = pd.read_csv(data_f, usecols=["spread"]).spread.median()
            spreads[sym] = med * meta["point"] * meta["tick_value"] / meta["tick_size"]   # dinero por lote

    out, open_in = [], {}
    for d in deals.itertuples():
        if d.dir == "in":
            open_in.setdefault(d.sym, []).append(d)
            continue
        ins = open_in.get(d.sym) or []
        first = ins.pop(0) if ins else d
        entry_comm = first.comm if first is not d else 0.0
        pnl = d.profit + d.swap + d.comm + entry_comm
        spread_cost = spreads.get(d.sym, 0.0) * d.vol
        out.append({"strategy": strategy_name, "sym": d.sym, "entry_t": first.t, "exit_t": d.t,
                    "dir": 1 if first.type == "buy" else -1, "pnl": pnl,
                    "cost_pnl": abs(d.comm + entry_comm) + spread_cost})
    return pd.DataFrame(out)
