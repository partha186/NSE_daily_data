# plot.py — Chart Viewer Reference

## Overview

`plot.py` is an interactive candlestick chart viewer for NSE stocks. It wraps the `Plotter` class from `funcdefs/Plotter.py` and provides keyboard-driven navigation, technical indicators, delivery colouring, watchlist management, and batch PNG export.

---

## Usage

```bash
cd src

# View a single stock
python plot.py --sym RELIANCE

# View multiple stocks (navigate with n / p)
python plot.py --sym RELIANCE TCS INFY

# View all stocks in a watchlist
python plot.py --watch SECTORS

# Resume from where you left off in a watchlist
python plot.py --watch SECTORS --resume
```

---

## Command-Line Arguments

### Symbol / Watchlist

| Argument | Example | Description |
|----------|---------|-------------|
| `--sym` | `--sym RELIANCE TCS` | One or more stock symbols |
| `--watch` | `--watch SECTORS` | Load symbols from a named watchlist |
| `--resume` | `--resume` | Continue from the last-viewed position in the watchlist |

### Technical Indicators

| Argument | Example | Description |
|----------|---------|-------------|
| `--sma` | `--sma 20 50 200` | Add Simple Moving Average lines |
| `--ema` | `--ema 12 26` | Add Exponential Moving Average lines |
| `--volume` | `--volume` | Show volume bars below the chart |
| `--rs` | `--rs` | Add Dorsey Relative Strength panel (vs `PLOT_RS_INDEX`) |
| `--dlv` | `--dlv` | Colour candles by delivery level (institutional activity) |

### Time Frame

| Argument | Example | Description |
|----------|---------|-------------|
| `--tf` | `--tf weekly` | Chart timeframe: `daily` (default) or `weekly` |
| `--period` | `--period 300` | Override number of bars to load |

### Export / Save

| Argument | Example | Description |
|----------|---------|-------------|
| `--save` | `--save` | Save all charts as PNG files instead of displaying interactively |

### Watchlist Management

| Argument | Example | Description |
|----------|---------|-------------|
| `--watch-add` | `--watch-add MY stocks.txt` | Add a watchlist named MY pointing to stocks.txt |
| `--watch-rm` | `--watch-rm MY` | Remove a watchlist |
| `--ls` | `--ls` | List all available watchlists |

### Presets

A preset saves your current indicator and display settings so you can reload them without retyping.

| Argument | Example | Description |
|----------|---------|-------------|
| `--preset` | `--preset daily_scan` | Load a saved preset |
| `--preset-save` | `--preset-save daily_scan` | Save current settings as a preset |
| `--preset-rm` | `--preset-rm daily_scan` | Delete a preset |

---

## Keyboard Controls

| Key | Action |
|-----|--------|
| `n` | Next chart |
| `p` | Previous chart |
| `a` | Add current symbol to the selection list |
| `s` | Screenshot — save current chart as a PNG |
| `q` | Quit and save selection list to `selections.csv` |

---

## Delivery Mode (`--dlv`)

Colours each candle based on how that day's delivery quantity compares to its rolling average:

| Colour | Condition | Meaning |
|--------|-----------|---------|
| Dark grey | DQ ≤ 1× avg | Normal / below-average delivery |
| Red | DQ > 1× avg | Slightly above average |
| Orange | DQ ≥ 1.5× avg | High delivery |
| Royal blue | DQ ≥ 2× avg | Very high delivery (institutional interest) |

A `$$` marker is drawn below the candle when both DQ and TQ exceed the `DLV_L1` threshold — this is the Institutional Money (IM) signal.

Thresholds are configurable via `DLV_L1`, `DLV_L2`, `DLV_L3` in `user.json`.

---

## Relative Strength (`--rs`)

Adds a panel below the chart showing the stock's performance relative to an index.

- **Dorsey RS** (`--rs`): `(stock_close / index_close) × 100`. Rising = outperforming.
- **Mansfield RS**: Dorsey RS normalised to its own SMA. Displayed automatically when RS panel is active.

The reference index is `config.PLOT_RS_INDEX` (default: `nifty 50`). Override in `user.json`:
```json
{ "PLOT_RS_INDEX": "bank nifty" }
```

---

## Presets — Step by Step

### Save a preset

```bash
python plot.py --sym RELIANCE --sma 20 50 200 --volume --rs --preset-save my_setup
```

This saves `my_setup` to `funcdefs/user.json` under the `PRESET` key.

### Load a preset

```bash
python plot.py --watch SECTORS --preset my_setup
```

All indicator settings from `my_setup` are applied automatically. You can still add extra flags alongside `--preset`.

### Remove a preset

```bash
python plot.py --preset-rm my_setup
```

---

## Watchlists — Step by Step

Watchlists are simple text files with one symbol per line, stored anywhere on disk.

### Create a watchlist file

```
# my_nifty50.txt
RELIANCE
TCS
HDFCBANK
INFY
ICICIBANK
```

### Register it with plot.py

```bash
python plot.py --watch-add NIFTY50 my_nifty50.txt
```

The name `NIFTY50` is stored (uppercase) in `funcdefs/user.json`.

### Use it

```bash
python plot.py --watch NIFTY50 --sma 50 200
```

### List all watchlists

```bash
python plot.py --ls
```

### Remove a watchlist

```bash
python plot.py --watch-rm NIFTY50
```

---

## Batch PNG Export

Use `--save` to export every chart as a PNG without displaying the interactive viewer. Useful for overnight batch jobs.

```bash
# Save all SECTORS charts (daily, with SMAs)
python plot.py --watch SECTORS --sma 20 50 200 --save

# Save weekly charts
python plot.py --watch SECTORS --tf weekly --save
```

Files are written to the current directory as `SYMBOL.png`.

---

## Resume

When using a watchlist, your position (which chart you were viewing last) is saved automatically to `funcdefs/user.json`. Use `--resume` to pick up where you left off.

```bash
# First session — view 12 of 50, quit at chart 12
python plot.py --watch SECTORS

# Next session — start at chart 13
python plot.py --watch SECTORS --resume
```

---

## Selection List

Press `a` while viewing any chart to mark that symbol. When you press `q` to quit, all marked symbols are written to `selections.csv` (one symbol per line) in the current directory.

```
# selections.csv example
RELIANCE
INFY
TCS
```

---

## Configuration

All chart defaults come from `src/funcdefs/Config.py`. Override in `src/funcdefs/user.json`:

```json
{
    "PLOT_DAYS": 200,
    "PLOT_WEEKS": 150,
    "PLOT_CHART_STYLE": "charles",
    "PLOT_CHART_TYPE": "candle",
    "PLOT_RS_COLOR": "darkorange",
    "PLOT_M_RS_COLOR": "darkred",
    "PLOT_SCREENSHOT_DPI": 150,
    "PLOT_SAVE_DPI": 300
}
```

Available chart styles: `binance`, `binancedark`, `blueskies`, `brasil`, `charles`, `checkers`, `classic`, `default`, `ibd`, `kenan`, `mike`, `nightclouds`, `sas`, `starsandstripes`, `tradingview`, `yahoo`.

---

## Plugins

Register indicator plugins in `user.json`:

```json
{
    "PLOT_PLUGINS": {
        "RSI": {
            "name": "rsi",
            "OB": 80,
            "OS": 20
        }
    }
}
```

Each plugin adds a panel below the main chart. See `src/plugin/rsi.py` for an example. Writing a plugin:

1. Create `src/plugin/myplugin.py`
2. Define `load(parser)` — adds any CLI flag your plugin needs
3. Define `main(*args)` — calculates the indicator and calls `make_addplot()`
4. Register it in `user.json` under `PLOT_PLUGINS`

---

## Output Files

| File | Created when | Contents |
|------|-------------|----------|
| `selections.csv` | On quit (`q`) | One symbol per line for all marked stocks |
| `funcdefs/user.json` | On watchlist / preset change | Watchlists, presets, resume position |
| `SYMBOL.png` | With `--save` flag | PNG chart image at `PLOT_SAVE_DPI` resolution |

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Symbol not found | CSV missing from `NSE_eod_data/daily/` | Run `python init.py` to sync |
| RS panel shows nothing | Index file missing | Run `python init.py` to sync index data |
| Delivery colours not showing | `--dlv` flag missing, or no delivery data | Add `--dlv`; check CSV has `DLV_QTY` column |
| Chart too small / overlapping labels | Too many SMAs or small screen | Reduce number of indicators or increase `PLOT_SIZE` in config |
| Resume not working | Different watchlist name used | Must use identical `--watch NAME` each time |
| Screenshot blank | Display driver issue (headless server) | Use `--save` for batch export instead |
