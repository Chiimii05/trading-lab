"""Informe HTML autocontenido (gráficos incrustados) con todos los resultados."""

import base64
import html
import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import analysis as an  # noqa: E402
from .config import settings  # noqa: E402

COLORS = ["#2f6fd6", "#c8a400", "#1a7f37", "#cf222e", "#8250df", "#d4740c", "#0a8f8f", "#6e7781"]
NAMES = {"beneficio": "Beneficio", "rentabilidad_pct": "Rentab. %", "caida_max_pct": "Caída máx. %",
         "rent_caida": "Rentab./caída", "sharpe_semanal_anualizado": "Sharpe", "factor_beneficio": "Factor benef.",
         "operaciones": "Operaciones", "aciertos_pct": "Aciertos %", "meses_positivos": "Meses +", "costes": "Costes"}


def _img(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return f'<img src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}">'


def _style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)


def _money(v):
    sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(settings.currency, settings.currency)
    return f"{v:,.0f} {sym}".replace(",", ".") if isinstance(v, (int, float)) else html.escape(str(v))


def _table(df, money_cols=(), color_cols=()):
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in [""] + list(df.columns))
    body = []
    for idx, row in df.iterrows():
        tds = []
        for c, v in row.items():
            txt = _money(v) if c in money_cols else ("—" if v is None or (isinstance(v, float) and pd.isna(v)) else
                                                    (f"{int(v)}" if isinstance(v, float) and v.is_integer() and c not in money_cols and abs(v) < 1000 else
                                                     f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                                                     if isinstance(v, float) else html.escape(str(v))))
            cls = ""
            if c in color_cols and isinstance(v, (int, float)) and not pd.isna(v):
                cls = ' class="pos"' if v > 0 else ' class="neg"' if v < 0 else ""
            tds.append(f"<td{cls}>{txt}</td>")
        body.append(f"<tr><th>{html.escape(str(idx))}</th>{''.join(tds)}</tr>")
    return f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def equity_chart(strategy_tr, portfolio_tr, start, end):
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for (name, tr), col in zip(strategy_tr.items(), COLORS):
        ax.plot(an.daily(tr, start, end).cumsum(), label=name, color=col, lw=1.4)
    if len(strategy_tr) > 1:
        ax.plot(an.daily(portfolio_tr, start, end).cumsum(), label="Portfolio", color="#111", lw=2.4)
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_ylabel(f"Beneficio acumulado ({settings.currency})")
    ax.legend(frameon=False, ncol=3, fontsize=9)
    _style(ax)
    return _img(fig)


def instrument_chart(inst):
    fig, ax = plt.subplots(figsize=(10, 3.2))
    ax.bar(inst.index, inst.beneficio, color=["#1a7f37" if v >= 0 else "#cf222e" for v in inst.beneficio])
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_ylabel(f"Beneficio ({settings.currency})")
    _style(ax)
    return _img(fig)


def mc_chart(mc):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.4))
    for curve in mc["_curvas"]:
        a1.plot(curve, color="#2f6fd6", alpha=0.06, lw=0.8)
    a1.axhline(0, color="#999", lw=0.8)
    a1.set_title("200 caminos posibles (remuestreo)", fontsize=10)
    a1.set_xlabel("Días")
    a2.hist(mc["_totales"], bins=60, color="#2f6fd6", alpha=0.8)
    a2.axvline(0, color="#cf222e", lw=1)
    a2.xaxis.set_major_locator(plt.MaxNLocator(5))
    a2.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", ".")))
    a2.set_title("Beneficio final en 5.000 simulaciones", fontsize=10)
    for a in (a1, a2):
        _style(a)
    return _img(fig)


def build(path, title, mode, strategy_tr, start, end, chosen_params, notes=()):
    portfolio_tr = pd.concat(strategy_tr.values(), ignore_index=True)
    multi = len(strategy_tr) > 1

    met = pd.DataFrame({n: an.metrics(t, start, end) for n, t in strategy_tr.items()}).T
    if multi:
        met.loc["Portfolio (todas en la misma cuenta)"] = an.metrics(portfolio_tr, start, end)
    met = met.rename(columns=NAMES)

    inst = an.by_instrument(portfolio_tr)
    best_worst = pd.DataFrame({
        n: {"Gana más en": f"{bi.index[0]} ({_money(bi.beneficio.iloc[0])})",
            "Gana menos / pierde más en": f"{bi.index[-1]} ({_money(bi.beneficio.iloc[-1])})"}
        for n, t in {**strategy_tr, **({"Portfolio": portfolio_tr} if multi else {})}.items()
        if not (bi := an.by_instrument(t)).empty}).T
    inst_by_strat = pd.DataFrame({n: an.by_instrument(t).beneficio for n, t in strategy_tr.items()}).fillna(0)
    if multi:
        inst_by_strat["Portfolio"] = inst_by_strat.sum(axis=1)

    verdict, checks = an.balance(portfolio_tr, strategy_tr, start, end)
    months = pd.DataFrame({n: an.by_month(t, start, end) for n, t in strategy_tr.items()})
    if multi:
        months["Portfolio"] = months.sum(axis=1)
    months.index = months.index.strftime("%Y-%m")
    spreads = an.spread_table(strategy_tr, portfolio_tr, start, end)
    mc = an.monte_carlo(portfolio_tr, start, end)
    pm = met.iloc[-1]

    checks_html = "".join(f'<li class="{"ok" if ok else "ko"}">{"✔" if ok else "✘"} {html.escape(t)} '
                          f'<span>({html.escape(d)})</span></li>' for t, ok, d in checks)
    params_html = "".join(f"<h3>{html.escape(n)}</h3>{_table(pd.DataFrame(p).set_index(pd.DataFrame(p).columns[0]))}"
                          for n, p in chosen_params.items() if p)
    mc_html = ""
    if mc:
        mc_tab = pd.DataFrame({
            "Beneficio (remuestreo)": mc["remuestreo_beneficio"],
            "Caída máx. % (remuestreo)": mc["remuestreo_caida_max_pct"],
            "Caída máx. % (orden barajado)": mc["barajado_caida_max_pct"],
            "Beneficio sin el 10 % de operaciones": mc["sin_10pct_operaciones_beneficio"]}).T
        mc_tab.columns = ["p5", "p25", "Mediano (p50)", "p75", "p95"]
        mc_html = f"""<h2>Monte Carlo</h2>
<p>¿Ha sido suerte? Se rehace el periodo 5.000 veces cambiando el orden y la mezcla de los días.
Probabilidad de acabar en pérdidas: <b>{mc['prob_perder_pct']} %</b>.
Probabilidad de una caída mayor del 10 %: <b>{mc['prob_caida_mayor_10_pct']} %</b>.<br>
Cómo leer la tabla: p5 = solo un 5 % de las simulaciones queda por debajo. En el beneficio, p5 es el caso malo;
en la caída máxima, el caso malo es p95.</p>
{mc_chart(mc)}{_table(mc_tab)}"""

    css = """body{font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#24292f;max-width:1080px;margin:0 auto;padding:24px;background:#fff}
h1{margin:0 0 4px}h2{margin-top:36px;border-bottom:1px solid #d8dee4;padding-bottom:6px}.sub{color:#6e7781}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:20px 0}
.card{border:1px solid #d8dee4;border-radius:10px;padding:14px}.card b{display:block;font-size:24px;margin-top:4px}
.tw{overflow-x:auto}table{border-collapse:collapse;font-size:13px;margin:8px 0;width:100%}th,td{padding:6px 10px;border-bottom:1px solid #eaeef2;text-align:right;white-space:nowrap}
thead th{background:#f6f8fa}tbody th{text-align:left}.pos{color:#1a7f37}.neg{color:#cf222e}img{max-width:100%}
ul.checks{list-style:none;padding:0}ul.checks li{margin:6px 0}.ok{color:#1a7f37}.ko{color:#cf222e}ul.checks span{color:#6e7781}
.verdict{display:inline-block;padding:4px 12px;border-radius:20px;background:#f6f8fa;font-weight:600}"""
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{css}</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="sub">{html.escape(mode)} · {start:%d/%m/%Y} → {end:%d/%m/%Y} · capital {_money(settings.capital)} ·
riesgo {settings.risk_pct} % por operación · generado {datetime.now():%d/%m/%Y %H:%M}</div>
<div class="cards">
<div class="card">{'Portfolio' if multi else 'Estrategia'}: beneficio<b class="{'pos' if pm['Beneficio'] >= 0 else 'neg'}">{_money(pm['Beneficio'])}</b></div>
<div class="card">Rentabilidad<b>{pm['Rentab. %']} %</b></div>
<div class="card">Caída máxima<b>{pm['Caída máx. %']} %</b></div>
<div class="card">Equilibrio<b>{verdict}</b></div></div>

<h2>Resultados</h2>{_table(met, money_cols=("Beneficio", "Costes"), color_cols=("Beneficio",))}
{equity_chart(strategy_tr, portfolio_tr, start, end)}

<h2>Instrumentos</h2>{_table(best_worst)}
{instrument_chart(inst)}
{_table(inst_by_strat, money_cols=tuple(inst_by_strat.columns), color_cols=tuple(inst_by_strat.columns))}

<h2>¿Es equilibrado? <span class="verdict">{verdict}</span></h2><ul class="checks">{checks_html}</ul>

<h2>Mes a mes</h2>{_table(months, money_cols=tuple(months.columns), color_cols=tuple(months.columns))}

<h2>Simulación de spreads</h2>
<p>Resultado si los costes (spread + comisión) fueran distintos de los supuestos. «Deja de ganar en»: multiplicador de costes a partir del cual el resultado pasa a negativo.</p>
{_table(spreads, money_cols=tuple(c for c in spreads.columns if c.startswith("×")), color_cols=tuple(c for c in spreads.columns if c.startswith("×")))}
{mc_html}
{('<h2>Parámetros elegidos en cada tramo (walk-forward)</h2>' + params_html) if params_html else ''}
<h2>Supuestos</h2><ul>{''.join(f'<li>{html.escape(n)}</li>' for n in notes)}</ul>
</body></html>"""
    path.write_text(doc, encoding="utf-8")
    return {"verdict": verdict, "metrics": met, "instruments": inst_by_strat, "best_worst": best_worst,
            "spreads": spreads, "mc": {k: v for k, v in (mc or {}).items() if not k.startswith("_")}, "months": months}
