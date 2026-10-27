<p align="right">🇪🇸 Español · <a href="#english">🇬🇧 English</a></p>

# 🧪 Trading Lab

Laboratorio para probar estrategias de trading **con honestidad**: walk-forward, costes reales, simulación de spreads,
Monte Carlo y un análisis de si el resultado es equilibrado o depende de un solo instrumento.

Funciona con **estrategias en Python** y con **expertos de MetaTrader 5 (.mq5 / .ex5)**, y saca un informe HTML
con lo que gana cada estrategia por separado y lo que ganaría el portfolio con todas en la misma cuenta.

> ⚠️ Es una herramienta de investigación, no una recomendación de inversión. Rentabilidades pasadas no garantizan rentabilidades futuras.

## Qué responde el informe

| Pregunta | Dónde |
|---|---|
| ¿Cuánto gana cada estrategia y el portfolio entero en una sola cuenta? | Resultados + curva de capital |
| ¿En qué instrumento gana más y en cuál gana menos o pierde más? | Instrumentos |
| ¿Es un resultado equilibrado o depende de un instrumento o una estrategia? | ¿Es equilibrado? |
| ¿Qué pasa si el spread o la comisión son peores? ¿A partir de qué coste deja de ganar? | Simulación de spreads |
| ¿Ha sido suerte? ¿Qué caídas son razonables? ¿Probabilidad de perder? | Monte Carlo |
| ¿Qué parámetros eligió el walk-forward en cada tramo? | Parámetros por tramo |
| ¿Cómo va mes a mes? | Mes a mes |

## Instalación

```bash
git clone https://github.com/Chiimii05/trading-lab.git
cd trading-lab
python -m venv .venv
.venv\Scripts\activate            # Windows  (en Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env              # y rellénalo
```

### El archivo `.env`

```ini
MT5_LOGIN=12345678
MT5_PASSWORD=tu_contraseña_de_INVERSOR
MT5_SERVER=TuBroker-Server
SYMBOLS=EURUSD,USDJPY,XAUUSD
```

Usa la **contraseña de inversor** (solo lectura): basta para descargar historial y usar el probador,
y con ella el laboratorio **no puede abrir ni cerrar operaciones** en tu cuenta. El `.env` está en `.gitignore`.

Otros ajustes opcionales: `CAPITAL`, `RISK_PCT` (riesgo por operación), `COMMISSION_PER_LOT`,
`HISTORY_FROM`, `SERVER_UTC_OFFSET` y `SERVER_US_DST` (hora del servidor del broker). Mira `.env.example`.

## Uso

```bash
python run.py demo                                  # datos sintéticos para probar sin MT5
python run.py download                              # historial M15 de tus SYMBOLS desde MT5
python run.py test strategies/sma_cross.py          # walk-forward de 2026 de una estrategia
python run.py test strategies/*.py                  # varias: cada una + el portfolio
python run.py test examples/ExampleMACross.mq5 --mq5-symbol EURUSD   # un experto en el probador de MT5
python run.py test a.py b.py --mode backtest --from 2024-01-01 --to 2025-01-01
```

El informe queda en `results/informe.html` (y un `.json` con los mismos datos y un `.csv` por estrategia).

Opciones de `test`: `--mode wf|backtest`, `--from`, `--to`, `--is-months` (meses de optimización, 24 por defecto),
`--step-months` (meses que se operan con cada optimización, 1), `--min-trades`, `--mq5-symbol`, `--mq5-set`, `--name`, `--title`.

## Escribir una estrategia

Un archivo `.py` con `NAME`, `GRID` (parámetros a optimizar), `DEFAULTS` y una función `run`:

```python
from lab.engine import atr, resample, run_stops

NAME = "Mi estrategia"
GRID = {"n": [20, 50], "k": [2.0, 3.0]}
DEFAULTS = {"n": 20, "k": 2.0}

def run(sym, m15, cost, n=20, k=2.0):
    h1 = resample(m15, "1h")
    entries = ...                         # +1 compra / -1 venta al cierre de la vela
    a = atr(h1, 14).to_numpy()
    return run_stops(sym, h1, cost, entries, lambda i, d, e: k * a[i])
```

`run_stops` simula entradas a la apertura siguiente, stop inicial, stop que sigue al precio (`trail_fn`), cierre por tiempo
(`max_bars`) o por condición (`exit_fn`). Para lógicas especiales puedes crear las operaciones tú con `make_trade`.
Ejemplos en [`strategies/`](strategies). Guarda tus estrategias privadas en `private/` (ignorada por git).

## Expertos de MetaTrader 5

Con un `.mq5` el laboratorio lo compila con MetaEditor, lo lanza en el probador de MT5 (OHLC de 1 minuto),
lee el informe y le aplica el mismo análisis: instrumentos, equilibrio, spreads y Monte Carlo.
**Cierra MT5 antes**: el probador no arranca desde la línea de comandos con el terminal abierto.
Los expertos se prueban con sus propios parámetros (`--mq5-set`); el walk-forward es para estrategias en Python.

## Cómo se calcula (y sus límites)

- **Sin mirar al futuro**: las señales usan velas cerradas y la entrada es a la apertura de la vela siguiente.
- **Walk-forward**: antes de cada mes se eligen los parámetros con mejor beneficio/caída en los 24 meses anteriores
  y se opera ese mes con ellos. El resultado solo incluye meses operados «a ciegas».
- **Riesgo fijo**: cada operación arriesga `RISK_PCT` del capital inicial hasta su stop, sin interés compuesto.
  Así se pueden sumar estrategias e instrumentos en una misma cuenta.
- **Costes**: spread mediano del historial + comisión por lote. Los stops se llenan a su precio o a la apertura si hay hueco;
  si una vela toca stop y objetivo, se supone el stop.
- **No incluye**: swaps, deslizamiento extra en noticias ni límites de margen. La caída máxima usa el beneficio realizado por día.
- **Monte Carlo**: remuestreo de días por bloques (mantiene la correlación entre estrategias), orden barajado y operaciones perdidas.

## Licencia

MIT. Úsalo, cámbialo y compártelo.

---

<a name="english"></a>
## 🇬🇧 English

**Trading Lab** is an honest backtesting lab for Python strategies and MetaTrader 5 experts (.mq5/.ex5).
It runs a monthly walk-forward (24-month optimisation window by default), uses real spreads and commissions,
and builds a self-contained HTML report with:

- profit of each strategy and of the whole portfolio in a single account,
- best and worst instrument for each strategy and for the portfolio,
- a **balance check** (profit concentration by instrument and strategy, correlation, positive months),
- **spread simulations** (×0.5 to ×3 costs and the break-even cost multiplier),
- **Monte Carlo** (block bootstrap, shuffled order, missed trades) with loss and drawdown probabilities.

Put your MT5 credentials in `.env` (use the read-only **investor password**), then run
`python run.py download` and `python run.py test strategies/*.py`. Try it without MT5 with `python run.py demo`.
Research tool only, not investment advice.
