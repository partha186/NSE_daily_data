# EOD2 — Developer Guide

## Getting Started


All scripts run from the `src/` directory. The working directory matters because relative paths in `Config.py`, `funcdefs.py`, and the tool scripts resolve relative to `Path(__file__).parent`.

```bash
cd src
python init.py       # data sync
python plot.py --sym RELIANCE
python data_get.py --sym RELIANCE
```

---

## Repository Layout

```
eod2/
├── src/
│   ├── funcdefs/         # Core shared library — edit here for shared logic
│   ├── plugin/           # User indicator plugins — safe to add new files here
│   ├── NSE_eod_data/     # Stock CSV data — do not commit changes here
│   └── *.py              # CLI entry points
├── tests/                # Unit tests (pytest)
├── pyproject.toml        # Package config, deps, entry points
└── requirements.txt      # Pinned runtime deps
```

---

## Module Responsibilities

| Module | Own it if you need to… |
|--------|----------------------|
| `funcdefs/funcdefs.py` | Change how data is downloaded, parsed, or written to CSV |
| `funcdefs/Config.py` | Add or change a configuration option |
| `funcdefs/utils.py` | Add a shared utility, indicator calculation, or the Color class |
| `funcdefs/Plotter.py` | Change chart rendering, add a new drawing tool, or fix chart layout |
| `funcdefs/Plugin.py` | Change how plugins are loaded or executed |
| `funcdefs/diagnostic.py` | Add a new data integrity check |
| `init.py` | Change the sync workflow or startup sequence |
| `plot.py` | Add a new CLI flag or interactive keyboard command |
| `data_get.py` | Change delivery analysis output or add a new display mode |
| `strategy_runner*.py` | Add a new strategy or change backtester logic |
| `live_scanner.py` | Change the live scanning loop, signals, or dashboard |

---

## Adding a Configuration Option

1. Add a class attribute to `Config` in [funcdefs/Config.py](funcdefs/Config.py):

```python
# ── MY SECTION ───────────────────────────────────────────────────────────────
MY_THRESHOLD = 1.5   # Description of what this controls
```

2. Document it in the docstring at the top of `Config`.

3. Users can override it in `funcdefs/user.json`:
```json
{ "MY_THRESHOLD": 2.0 }
```

No code change needed to support the override — `Config.__init__` handles it automatically.

---

## Adding a Plugin

Plugins add indicator panels below charts in `plot.py`.

1. Create `src/plugin/myplugin.py`:

```python
"""My custom indicator plugin."""

def load(parser):
    """Register CLI arguments (called once at startup)."""
    parser.add_argument("--myplugin", action="store_true", help="Enable my indicator")

def main(plotter, df, args, config, addplot_list):
    """Calculate indicator and append to addplot_list."""
    if not getattr(args, "myplugin", False):
        return

    import mplfinance as mpf
    import pandas as pd

    # Calculate your indicator on df
    values = df["Close"].rolling(14).mean()

    panel_num = len(addplot_list) + 1   # each panel gets its own subplot number
    addplot_list.append(
        mpf.make_addplot(values, panel=panel_num, color="blue", ylabel="My Indicator")
    )
```

2. Register the plugin in `src/funcdefs/user.json`:

```json
{
    "PLOT_PLUGINS": {
        "MYPLUGIN": { "name": "myplugin" }
    }
}
```

3. Test it:
```bash
python plot.py --sym RELIANCE --myplugin
```

The plugin system catches and logs failures without crashing the chart viewer. See `funcdefs/Plugin.py` for details.

---

## Writing a New CLI Tool

1. Create `src/mytool.py`.
2. Parse arguments with `argparse`.
3. Import config and utilities:

```python
import sys
from pathlib import Path
from funcdefs.Config import Config
from funcdefs.utils import Color

config = Config()
DIR = Path(__file__).parent
```

4. Add an entry point in `pyproject.toml`:

```toml
[project.scripts]
eod2-mytool = "mytool:main"
```

5. Wrap the top-level logic in a `main()` function so the entry point works:

```python
def main():
    # your logic here
    pass

if __name__ == "__main__":
    main()
```

---

## Running Tests

```bash
# From the project root
pytest

# With coverage
pytest --cov=src --cov-report=term-missing

# One file
pytest tests/test_plotter.py

# One class
pytest tests/test_plotter.py::TestJsonPersistence -v
```

`tests/context.py` adds `src/` to `sys.path` so imports work without installing the package. Every test file should start with:

```python
import context   # noqa: F401
```

---

## Writing Tests

Use the existing `tests/test_plotter.py` as a reference. Key conventions:

- One `unittest.TestCase` subclass per logical area.
- `setUp` / `tearDown` for resource management.
- Prefer testing real behaviour over heavy mocking. Mock only at system boundaries (file I/O, network calls).
- Descriptive method names: `test_<what>_<scenario>_<expected_result>`.

```python
import unittest
import context   # noqa: F401
from funcdefs.utils import Color

class TestColor(unittest.TestCase):
    def setUp(self):
        from funcdefs.Config import Config
        self.config = Config()

    def test_num_returns_white_at_or_above_level3(self):
        result = Color.num(self.config.DLV_L3, self.config)
        self.assertIn(Color.WHITE, result)

    def test_num_returns_cyan_below_level1(self):
        result = Color.num(0.5, self.config)
        self.assertIn(Color.CYAN, result)
```

---

## Code Style

- Follow existing code style — no enforced linter, but keep imports grouped (`stdlib` → `third-party` → `local`).
- Docstrings on all public functions and classes. Keep them factual and concise.
- No type annotations required but welcome on new code.
- Prefer explicit over clever — this codebase is read by traders, not just engineers.

---

## Data Format Reference

### Daily stock CSV (`NSE_eod_data/daily/SYMBOL.csv`)

```
Date,Open,High,Low,Close,Volume,Deliverable Volume,% Dly Qt to Traded Qty,DLV_QTY,QTY_PER_TRADE
2024-01-15,100.50,101.25,100.25,100.95,1234567,456789,37.00,456789,123
```

- 9 columns for stocks, 10 for indices (indices have a `Series` column)
- All prices adjusted for splits and bonuses
- `DLV_QTY` and `QTY_PER_TRADE` are used by `data_get.py` and delivery colouring

### metadata.json (`NSE_eod_data/metadata.json`)

```json
{
    "data-version": 3.2,
    "lastUpdate": "2026-04-11",
    "DLV_PENDING_DATES": [],
    "special-sessions": []
}
```

Do not edit manually unless recovering from a corrupted state. The `lastUpdate` field controls which dates `init.py` will try to sync next.

---

## Common Pitfalls

**Importing `funcdefs` from outside `src/`**
All paths in `funcdefs` resolve relative to `Path(__file__).parent` which is `src/`. Running scripts from outside `src/` causes file-not-found errors. Always `cd src` first, or use absolute paths.

**Mutating the config object**
`Config` is instantiated once per tool run. Do not store state in it or modify it at runtime — it is read-only configuration.

**Adding `exit()` calls**
Use `sys.exit()` for intentional exits so tests can catch `SystemExit`. Never use bare `exit()`.

**Modifying NSE_eod_data/ directly**
The diagnostic tool and rollback logic depend on the exact CSV format. Do not add, remove, or reorder columns manually.

---

## Dependency Notes

| Package | Why it's needed | Optional? |
|---------|----------------|-----------|
| `nse[server]` | Download NSE data | No |
| `mplfinance` | Candlestick charts | No |
| `fast-csv-loader` | Fast CSV reading (C extension) | No |
| `pandas` | Data manipulation | No |
| `tzlocal` | Local timezone detection | No |
| `httpx` | HTTP client (used by nse) | No |
| `numpy` | Numerical operations | No |
| `python-dateutil` | Date parsing | No |
| `backports.zoneinfo` | Python 3.8 zoneinfo compatibility | Python < 3.9 only |
| `yfinance` | Live scanner data | `[scanner]` extra |
| `rich` | Live scanner dashboard | `[scanner]` extra |
| `ta` | strategy_runner_V2 indicators | `[backtest]` extra |

---

## Release Checklist

1. Update `Config.VERSION` in [funcdefs/Config.py](funcdefs/Config.py)
2. Update `version` in [pyproject.toml](../pyproject.toml)
3. If the CSV schema changed, increment `EXPECTED_DATA_VERSION`
4. Run tests: `pytest`
5. Update `INIT_PY_REFERENCE.md` if the sync workflow changed
6. Update `CODE_DOCUMENTATION.md` if new modules were added
7. Tag the release in git
