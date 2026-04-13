# NSE End-of-Day Data Tool

An automated Python toolkit to download, maintain, visualise, and backtest NSE (National Stock Exchange of India) stock data.

- Daily OHLCV data for 2000+ NSE stocks going back to 1995
- Automatic adjustments for stock splits and bonus issues
- Delivery/institutional money analysis
- Candlestick charts with technical indicators
- Multi-strategy backtesting framework
- Live NIFTY/BANKNIFTY signal scanner

---

## Requirements

- Python 3.8 or higher
- Internet access to reach NSE servers

---

## Installation

### Option 1 — Git clone (recommended)

```bash

# Install dependencies
pip install -r requirements.txt

# Optional extras
pip install -r requirements.txt "yfinance>=0.2" "rich>=13.0"   # live scanner
```

The `eod2_data` submodule (stock CSV files) is included automatically via git.

### Option 2 — Download ZIP (no git)

1. Download and extract the ZIP from GitHub
2. Run the bootstrap script to fetch stock data:

```bash
cd eod2
pip install -r requirements.txt
python setup_data.py
```

`setup_data.py` downloads the entire `eod2_data` folder (~15 MB) from GitHub and extracts it into `src/NSE_eod_data/`.

### Option 3 — Editable install via pyproject.toml

```bash
pip install -e .                   # core only
pip install -e ".[scanner]"        # + live scanner (yfinance, rich)
pip install -e ".[backtest]"       # + advanced backtester (ta)
pip install -e ".[all]"            # everything
```

---

## Project Structure

```
eod2/
├── src/
│   ├── init.py               # Daily data sync — run this every day
│   ├── plot.py               # Candlestick chart viewer
│   ├── data_get.py           # Delivery / institutional money analyser
│   │
│   ├── funcdefs/             # Core library (imported by all tools)
│   │   ├── __init__.py       # Package exports
│   │   ├── funcdefs.py       # Data processing, date handling, adjustments
│   │   ├── Config.py         # All configuration defaults + user overrides
│   │   ├── Plotter.py        # Chart rendering engine
│   │   ├── Plugin.py         # Plugin loader
│   │   ├── utils.py          # JSON I/O, CSV loading, indicators, Color
│   │   └── diagnostic.py     # Data integrity checker
│   │
│   ├── nse/                  # NSE API wrapper
│   ├── plugin/               # User-defined indicator plugins
│   │   └── rsi.py            # Example RSI plugin
│   │
│   └── NSE_eod_data/         # Stock data (CSV files)
│       ├── daily/            # OHLCV per stock  (e.g. RELIANCE.csv)
│       ├── delivery/         # Delivery data per stock
│       ├── indices/          # Index data (nifty 50.csv, etc.)
│       └── metadata.json     # Sync state (last update, pending dates)
│
├── tests/                    # Unit tests
├── setup_data.py             # One-time data bootstrap for ZIP users
├── pyproject.toml            # Package metadata and dependencies
├── requirements.txt          # Pinned runtime dependencies
└── README.md
```

---

## Quick Start

### Step 1 — Sync data for the first time

```bash
cd src
python init.py
```

This connects to NSE, downloads all missing trading days up to today, and updates `NSE_eod_data/`. On first run it processes many historical dates; subsequent runs take seconds.

### Step 2 — View a chart

```bash
python plot.py --sym RELIANCE
python plot.py --sym RELIANCE --sma 20 50 200 --volume
python plot.py --watch SECTORS --tf weekly
```

### Step 3 — Analyse delivery data

```bash
python data_get.py --sym RELIANCE TCS INFY
python data_get.py --lookup RELIANCE
python data_get.py --watch SECTORS
```

### Step 4 — Backtest a strategy

```bash
python strategy_runner.py --folder NSE_eod_data/daily --strategy ema_crossover
python strategy_runner.py --folder NSE_eod_data/daily --strategy all --export results.csv
```

### Step 5 — Run the live scanner (requires `yfinance`, `rich`)

```bash
python live_scanner.py
```

---

## Tools

### `init.py` — Daily Data Sync

Downloads NSE equity, index, and delivery data and keeps every stock's CSV up to date.

```bash
python src/init.py               # sync all missing days
python src/init.py --version     # show EOD2 and data version
python src/init.py --config      # show current configuration
```

- Automatically skips weekends and NSE holidays
- Retries delivery data if NSE releases it late
- Rolls back any partial writes on error
- Applies split and bonus adjustments to historical prices

### `plot.py` — Chart Viewer

Interactive candlestick charts with keyboard navigation.

```bash
# Single / multiple stocks
python plot.py --sym RELIANCE
python plot.py --sym RELIANCE TCS INFY

# From a watchlist
python plot.py --watch SECTORS

# With indicators
python plot.py --sym RELIANCE --sma 20 50 200 --ema 12 26 --volume

# Delivery candle colouring (institutional activity)
python plot.py --sym RELIANCE --dlv

# Relative strength vs NIFTY 50
python plot.py --sym RELIANCE --rs

# Weekly timeframe
python plot.py --sym RELIANCE --tf weekly

# Save charts as PNG files
python plot.py --watch SECTORS --save

# Resume from last position
python plot.py --watch SECTORS --resume
```

**Keyboard controls while viewing:**

| Key | Action |
|-----|--------|
| `n` | Next chart |
| `p` | Previous chart |
| `a` | Add symbol to selection list |
| `q` | Quit and save selections |
| `s` | Screenshot current chart |

### `data_get.py` — Delivery Analyser

Detect institutional money (IM) signals by comparing delivery and volume against rolling averages.

```bash
# Snapshot of latest metrics for one or more symbols
python data_get.py --sym RELIANCE TCS INFY

# Full history for a single symbol
python data_get.py --lookup RELIANCE

# Use a watchlist file
python data_get.py --watch SECTORS

# Manage watchlists
python data_get.py --watch-add MY_LIST my_stocks.txt
python data_get.py --watch-rm MY_LIST
python data_get.py --ls
```

**Metric columns:**

| Column | Meaning |
|--------|---------|
| DQ | Delivery Qty ÷ rolling average |
| TQ | Traded Qty per trade ÷ rolling average |
| VOL | Volume ÷ rolling average |
| IM | $$ when both DQ and TQ exceed the threshold |

Color coding: WHITE (≥ 2×) › ORANGE (≥ 1.5×) › RED (> 1×) › CYAN (≤ 1×)

### `strategy_runner.py` — Backtester (v1)

Run six pre-built strategies across all stock CSVs and get P&L stats.

```bash
python strategy_runner.py --folder NSE_eod_data/daily
python strategy_runner.py --folder NSE_eod_data/daily --strategy ema_crossover
python strategy_runner.py --folder NSE_eod_data/daily --sl 0.02 --tp 0.06
python strategy_runner.py --folder NSE_eod_data/daily --export results.csv
```

Available strategies: `ema_crossover`, `rsi`, `macd`, `breakout`, `supertrend`, `bb_squeeze`, `all`


### `funcdefs/diagnostic.py` — Data Integrity Check

Scans all CSV files for duplicates, type mismatches, missing values, and column count errors.

```bash
python -m funcdefs.diagnostic
python -m funcdefs.diagnostic --threshold 20
python -m funcdefs.diagnostic --dir path/to/daily
```

---

## Configuration

All settings live in `src/funcdefs/Config.py`. Override any value by creating `src/funcdefs/user.json`:

```json
{
    "PLOT_DAYS": 200,
    "PLOT_CHART_STYLE": "charles",
    "DGET_AVG_DAYS": 20,
    "DLV_L3": 2.5,
    "AMIBROKER": false,
    "WATCH": {
        "MY_LIST": "my_stocks.txt"
    }
}
```

Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `PLOT_DAYS` | 160 | Days of data shown on daily charts |
| `PLOT_WEEKS` | 140 | Weeks shown on weekly charts |
| `PLOT_CHART_STYLE` | `tradingview` | Chart theme |
| `DLV_L1 / L2 / L3` | 1 / 1.5 / 2 | Delivery level thresholds (× average) |
| `DGET_AVG_DAYS` | 30 | Rolling average period for delivery analysis |
| `AMIBROKER` | false | Export data to AmiBroker on each sync |
| `PLOT_RS_INDEX` | `nifty 50` | Index used for Relative Strength calculation |

---

## Data Format

Each stock is stored as a CSV file in `src/NSE_eod_data/daily/`:

```
Date,Open,High,Low,Close,Volume,Deliverable Volume,% Dly Qt to Traded Qty,DLV_QTY,QTY_PER_TRADE
2024-01-15,100.50,101.25,100.25,100.95,1234567,456789,37.00,456789,123
```

Prices are adjusted for all historical splits and bonus issues.

---

## Plugins

Add custom indicator panels to `plot.py` by placing a Python file in `src/plugin/` and registering it in `user.json`:


## Scheduling (run daily)

**Linux / Mac — cron:**
```bash
# Run at 9:30 PM IST on weekdays
30 15 * * 1-5 cd /path/to/eod2/src && python init.py >> ~/eod2.log 2>&1
```

**Windows — Task Scheduler:**
Create a task that runs `python src/init.py` from the project directory at market close (3:30 PM IST + buffer).

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: nse` | Library not installed | `pip install "nse[server]"` |
| `NSE version mismatch` | Outdated nse library | `pip install -U nse` |
| `fast-csv-loader not found` | Missing C extension | `pip install fast-csv-loader` |
| `ConnectionError` on init.py | NSE server unreachable | Check network, retry later |
| Delivery data never updates | NSE delayed release | System retries automatically next run |
| Chart shows no RS line | Index file missing | Run `init.py` to sync index data |

---



