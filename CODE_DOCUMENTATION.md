# EOD2 — Code Documentation

## Overview

EOD2 is a Python toolkit for NSE (National Stock Exchange of India) stock data management and analysis. It downloads and maintains daily OHLCV and delivery data for 2000+ stocks, applies corporate-action adjustments, and provides tools for charting, delivery analysis, backtesting, and live scanning.

---

## Project Structure

```
eod2/
├── src/
│   ├── init.py               # Daily data sync engine
│   ├── plot.py               # Interactive chart viewer
│   ├── data_get.py           # Delivery / institutional money analyser
│   ├── strategy_runner.py    # Multi-strategy backtester (v1)
│   ├── strategy_runner_V2.py # Advanced backtester with grid optimisation (v2)
│   ├── live_scanner.py       # Live NIFTY/BANKNIFTY EMA signal scanner
│   │
│   ├── funcdefs/             # Core shared library
│   │   ├── __init__.py       # Public API exports
│   │   ├── funcdefs.py       # NSE data logic, dates, adjustments, logging
│   │   ├── Config.py         # Configuration class with user.json overrides
│   │   ├── Plotter.py        # mplfinance-based chart engine (1100+ lines)
│   │   ├── Plugin.py         # Plugin registry with error isolation
│   │   ├── utils.py          # CSV loading, JSON I/O, indicators, Color class
│   │   └── diagnostic.py     # Data integrity scanner (callable or CLI)
│   │
│   ├── nse/
│   │   └── nse.py            # Unofficial NSE API wrapper
│   │
│   ├── plugin/
│   │   └── rsi.py            # Example RSI indicator plugin
│   │
│   └── NSE_eod_data/         # Data storage (git submodule / setup_data.py)
│       ├── daily/            # Per-stock OHLCV CSVs  (RELIANCE.csv, TCS.csv …)
│       ├── delivery/         # Per-stock delivery CSVs
│       ├── indices/          # Index CSVs  (nifty 50.csv, bank nifty.csv …)
│       ├── sector_watchlist.csv
│       └── metadata.json     # Sync state (last update, pending dates, version)
│
├── tests/
│   ├── context.py            # Adds src/ to sys.path for test imports
│   └── test_plotter.py       # Unit tests for Plotter (12 test classes)
│
├── setup_data.py             # One-time bootstrap for non-git users
├── pyproject.toml            # Package metadata, deps, entry points
└── requirements.txt          # Pinned runtime dependencies
```

---

## Component Reference

### `init.py` — Data Sync Engine

The main orchestrator. Run once per trading day to keep all CSVs current.

**Startup sequence:**

1. Check NSE library version (must be ≥ 1.2.4)
2. Check eod2_data version matches `EXPECTED_DATA_VERSION`
3. Install a global exception hook for structured error logging
4. Parse CLI args (`--version`, `--config`)
5. Open NSE server connection — exit immediately on network failure
6. One-time initialisation:
   - Detect and handle special post-market sessions
   - Update AmiBroker if `AMIBROKER = True` in config
   - Queue any previously-pending delivery dates for retry

**Main loop (repeats for each un-synced trading date):**

| Step | What happens |
|------|-------------|
| Get next date | `funcdefs.dates.nextDate()` — stops if up to date |
| Holiday check | Skip NSE-closed dates, update metadata, continue |
| Validate actions file | Ensure split/bonus data is current |
| Report status check | Confirm NSE has published equity + index reports |
| Download BHAV | Equity price CSV for all stocks |
| Download INDEX | Index snapshot CSV |
| Download DELIVERY | Investor participation CSV (optional — queued if missing) |
| Update database | `updateNseEOD()` + `updateIndexEOD()` — rollback on any error |
| Apply adjustments | `adjustNseStocks()` — rewrite historical prices for splits/bonuses |
| Run hook | Call `funcdefs.hook.on_complete()` if user-defined |
| Cleanup | Delete temp files, write updated `metadata.json` |

**Error recovery:**

- Any failure during the database update or adjustment step triggers a full rollback so no partial data is written.
- Missing delivery data is tracked in `metadata.json["DLV_PENDING_DATES"]` and retried automatically on the next run.

---

### `funcdefs/funcdefs.py` — Core Processing Logic

Contains the functions called by `init.py`:

| Function | Purpose |
|----------|---------|
| `configure_logger()` | Sets up file + stream logging handlers |
| `is_version_compatible()` | Semantic version check (major.minor.patch) |
| `load_module()` | Dynamic module import, optionally returns a class |
| `log_unhandled_exception()` | Global exception hook for structured logging |
| `dates.nextDate()` | Advance to next un-processed trading date |
| `checkForHolidays()` | Return True if current date is a market holiday |
| `check_special_sessions()` | Detect post-market / Muhurat trading sessions |
| `validateNseActionsFile()` | Verify the corporate-actions file is up to date |
| `updateNseEOD()` | Write equity OHLCV rows to per-stock CSVs |
| `updateIndexEOD()` | Write index rows to per-index CSVs |
| `adjustNseStocks()` | Restate historical prices for splits and bonuses |
| `rollback()` | Undo all writes for the current date |
| `cleanup()` | Remove downloaded temporary files |

---

### `funcdefs/Config.py` — Configuration

A plain class whose attributes are the defaults. At instantiation it reads `src/funcdefs/user.json` (if present) and merges any matching UPPERCASE keys.

**Important settings:**

| Attribute | Default | Used by |
|-----------|---------|--------|
| `PLOT_DAYS` | 160 | plot.py — days on daily chart |
| `PLOT_WEEKS` | 140 | plot.py — weeks on weekly chart |
| `PLOT_CHART_STYLE` | `tradingview` | plot.py — mplfinance theme |
| `DLV_AVG_LEN` / `VOL_AVG_LEN` | 30 | utils.py — rolling-average window |
| `DLV_L1 / L2 / L3` | 1 / 1.5 / 2 | Delivery level thresholds |
| `DGET_AVG_DAYS` / `DGET_DAYS` | 30 | data_get.py — analysis window |
| `PLOT_RS_INDEX` | `nifty 50` | Plotter.py — RS reference index |
| `AMIBROKER` | False | init.py — AmiBroker export toggle |
| `PLOT_PLUGINS` | `{}` | plot.py — plugin registry |
| `WATCH` | `{SECTORS: …}` | plot.py / data_get.py — watchlists |
| `VERSION` | `9.1.2` | init.py — EOD2 version |
| `EXPECTED_DATA_VERSION` | `3.2` | init.py — required data schema |

To override, create `src/funcdefs/user.json`:
```json
{
    "PLOT_DAYS": 250,
    "DLV_L3": 2.5,
    "WATCH": { "MY_STOCKS": "my_stocks.txt" }
}
```
`WATCH` entries are **merged** with defaults; all other keys **replace** defaults.

---

### `funcdefs/utils.py` — Utilities

| Function / Class | Purpose |
|-----------------|---------|
| `Color` | ANSI terminal colour class; `Color.num(val, config)` for threshold-based colouring |
| `DateEncoder` | `json.JSONEncoder` subclass that serialises `datetime` as ISO strings |
| `loadJson(path)` | Read and parse a JSON file |
| `writeJson(path, data)` | Serialise data to JSON using `DateEncoder` |
| `randomChar(n)` | Return n random lowercase letters |
| `getDataFrame(path, tf, period)` | Load a stock CSV; resample to weekly if `tf="weekly"` |
| `getDeliveryLevels(df, config)` | Add DQ, TQ, IM_F, MCOverrides columns for delivery colouring |
| `getLevels(df, mean)` | Identify support/resistance levels (2-bar pivot method) |
| `getLevels_v2(df, mean)` | Same, using 3-bar pivots with touch-count filter |
| `relativeStrength(close, idx)` | Dorsey RS: `(close / index_close) * 100` |
| `mansfieldRelativeStrength(close, idx, period)` | Mansfield RS: normalised to SMA |

> `manfieldRelativeStrength` is retained as a backwards-compatible alias.

---

### `funcdefs/Plotter.py` — Chart Engine

Large class (~1100 lines) wrapping `mplfinance`. Handles:

- Candlestick / OHLC / line chart rendering
- Technical indicator overlays: SMA, EMA, RS, Mansfield RS
- Delivery candle colouring via `MCOverrides`
- Support/resistance line detection and display
- Interactive line-drawing tools (trend lines, horizontal lines, arbitrary segments)
- Undo stack (last 20 operations)
- LRU cache for DataFrames (max 6 entries)
- Screenshot / batch PNG export
- Preset save/load
- Crosshair cursor

Key top-level function: `processPlot(args, config)` — entry point used by `plot.py`.

---

### `funcdefs/Plugin.py` — Plugin System

Loads user-defined indicator plugins from the `src/plugin/` directory.

Each plugin file must expose:
```python
def load(parser: ArgumentParser) -> None: ...   # register CLI args
def main(*args) -> None: ...                     # add panel to chart
```

Plugins that fail to import or are missing required callables are logged as warnings and skipped — they will not crash the chart viewer.

---

### `funcdefs/diagnostic.py` — Data Integrity Scanner

Can be run as a CLI tool or imported and called programmatically.

```bash
python -m funcdefs.diagnostic                    # default threshold=5
python -m funcdefs.diagnostic --threshold 20     # show more errors
python -m funcdefs.diagnostic --dir path/daily   # custom directory
```

Checks per CSV file:
1. Datetime index type (`datetime64[ns]`)
2. Column count (9 for stocks, 10 for indices)
3. Numeric column dtypes (`float64` or `int64`)
4. NaN values in OHLCV columns
5. Duplicate date entries

Returns a `DiagnosticResult` dataclass with per-category error lists and a `print_report()` method.

---

### `plot.py` — Chart Viewer

Interactive viewer built on `Plotter`.

```bash
python plot.py --sym RELIANCE --sma 20 50 --volume
python plot.py --watch SECTORS --tf weekly --rs
python plot.py --sym RELIANCE --dlv             # delivery candle mode
python plot.py --watch SECTORS --save           # batch export PNG
python plot.py --watch SECTORS --resume         # continue from last position
```

Watchlist and preset management:
```bash
python plot.py --watch-add NAME file.txt
python plot.py --watch-rm NAME
python plot.py --ls
python plot.py --sym RELIANCE --sma 20 --preset-save my_setup
python plot.py --sym TCS --preset my_setup
```

---

### `data_get.py` — Delivery Analyser

Calculates DQ (delivery ratio), TQ (trade qty ratio), VOL (volume ratio), and IM (institutional money) signals.

Two modes:
- **Snapshot** (`--sym` / `--watch`): Latest bar only for multiple symbols side by side
- **Lookup** (`--lookup`): Last N days of all metrics for one symbol

IM is flagged when both DQ and TQ exceed `config.DLV_L1` (default: 1.0× average). The threshold is consistent across both modes.

---

### `strategy_runner.py` — Backtester v1

Long-only backtester with fixed SL/TP and brokerage commission.

**Strategies:**

| Name | Signal logic |
|------|-------------|
| `ema_crossover` | EMA 9 crosses EMA 21 |
| `rsi` | RSI 14 crosses 30 (buy) or 70 (sell) |
| `macd` | MACD line crosses signal line |
| `breakout` | Price breaks 20-day high with 1.5× volume |
| `supertrend` | Supertrend direction change (ATR 10, mult 3) |
| `bb_squeeze` | Price breaks Bollinger Band after squeeze |

```bash
python strategy_runner.py --folder NSE_eod_data/daily --strategy all
python strategy_runner.py --folder NSE_eod_data/daily --sl 0.02 --tp 0.06 --export out.csv
```

---

### `strategy_runner_V2.py` — Backtester v2

Supports long and short trades, 9 base strategies (18 with long-only variants), and brute-force parameter grid search.

**Strategies:** Keltner Channels, Bollinger Bands, Moving Average crossovers, MACD, RSI, Williams %R, Stochastic (Fast & Slow), Ichimoku.

```bash
python strategy_runner_V2.py --folder NSE_eod_data/daily
python strategy_runner_V2.py --folder NSE_eod_data/daily --optimize --strategy rsi_long
```

---

### `live_scanner.py` — Live Scanner

Polls yfinance every scan cycle for NIFTY and BANKNIFTY intraday OHLCV, detects EMA 9/21 crossovers, and displays a live `rich` dashboard with signal status and ATR-based SL/TP levels.

- Thread pool for parallel symbol fetching
- In-memory deduplication (one signal per crossover event per session)
- Caches DataFrames to reduce redundant downloads

---

### `setup_data.py` — Data Bootstrap

One-time script for users who downloaded the repo as a ZIP (no git submodule).

Steps:
1. If `src/NSE_eod_data/` already has data, renames it to `eod2_data_backup/` for safety
2. Downloads `eod2_data-main.zip` from GitHub (~15 MB, streamed in 15 MB chunks)
3. Extracts into `src/NSE_eod_data/` (strips the `eod2_data-main/` path prefix)
4. Deletes the zip file

---

## Data Flow — Full Pipeline

```
NSE Website
    │
    ▼
nse library (nse/nse.py)
    │  equityBhavcopy()   → BHAV_FILE   (equity prices)
    │  indicesBhavcopy()  → INDEX_FILE  (index data)
    │  deliveryBhavcopy() → DELIVERY_FILE (delivery data)
    │
    ▼
init.py — validation + parsing
    │  check NSE actions file (splits, bonuses)
    │  verify report status (critical vs optional)
    │
    ▼
funcdefs.py — database update
    │  updateNseEOD()   → appends rows to daily/SYMBOL.csv
    │  updateIndexEOD() → appends rows to indices/INDEX.csv
    │
    ▼
funcdefs.py — adjustments
    │  adjustNseStocks() → rewrites historical prices for splits/bonuses
    │
    ▼
NSE_eod_data/  (persistent CSV storage)
    │
    ├──► plot.py          (chart viewer)
    ├──► data_get.py      (delivery analysis)
    ├──► strategy_runner  (backtesting)
    └──► live_scanner.py  (real-time signals)
```

---

## Error Handling Strategy

| Error type | What happens |
|------------|-------------|
| NSE library version mismatch | Log + exit with `pip install -U nse` instructions |
| Data version mismatch | Log + exit with `python setup_data.py` instructions |
| Network error on connect | Log warning + exit; user retries when network is back |
| Download failure mid-sync | Rollback all writes for current date; retry next run |
| Missing delivery report | Queue date in `DLV_PENDING_DATES`; retry next run automatically |
| NSE holiday | Skip date, update `lastUpdate`, continue loop |
| Plugin import failure | Log warning, skip plugin; chart viewer continues normally |
| Diagnostic CSV parse error | Record in `exceptions` list, continue scanning other files |

---

## Configuration File Reference

**Location:** `src/funcdefs/user.json`

```json
{
    "AMIBROKER": false,
    "PLOT_DAYS": 200,
    "PLOT_WEEKS": 150,
    "PLOT_CHART_STYLE": "charles",
    "DLV_L1": 1,
    "DLV_L2": 1.5,
    "DLV_L3": 2,
    "DGET_AVG_DAYS": 20,
    "DGET_DAYS": 30,
    "PLOT_PLUGINS": {
        "RSI": { "name": "rsi", "OB": 80, "OS": 20 }
    },
    "WATCH": {
        "MY_STOCKS": "my_stocks.txt"
    }
}
```

All keys must be UPPERCASE. Unknown keys are silently ignored (no validation errors). `WATCH` entries are merged with built-in defaults.

---

## Testing

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=src --cov-report=term-missing

# Single test class
pytest tests/test_plotter.py::TestJsonPersistence
```

Tests live in `tests/`. `tests/context.py` adds `src/` to `sys.path` so imports work without installation.

Current coverage: `Plotter.py` is well-tested (12 test classes). Core `funcdefs.py`, `init.py`, `data_get.py`, and the strategy runners do not yet have test coverage.

---

## Adding a New Feature

1. Identify which module owns the logic:
   - Data processing → `funcdefs/funcdefs.py`
   - Configuration → `funcdefs/Config.py` (add attribute + comment)
   - Shared utility → `funcdefs/utils.py`
   - Chart feature → `funcdefs/Plotter.py`
   - New CLI tool → new file in `src/`

2. Add the feature with docstrings.

3. Export from `funcdefs/__init__.py` if it should be part of the public API.

4. Add a test in `tests/`.

5. Update `CODE_DOCUMENTATION.md` and/or the relevant tool's `.md` file.

---

## Related Links

- EOD2 Wiki: [https://github.com/BennyThadikaran/eod2/wiki](https://github.com/BennyThadikaran/eod2/wiki)
- NSE library: [https://github.com/BennyThadikaran/nse-python](https://github.com/BennyThadikaran/nse-python)
- mplfinance: [https://github.com/matplotlib/mplfinance](https://github.com/matplotlib/mplfinance)
