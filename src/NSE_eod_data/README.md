# NSE_eod_data — Stock Data Storage

This directory holds the End-of-Day (EOD) data for NSE (National Stock Exchange of India) stocks in CSV format. It is the data layer for the EOD2 project.

Issues and feature requests: [EOD2 repo](https://github.com/BennyThadikaran/eod2)

---

## How data gets here

- **Git users:** this directory is a git submodule. Run `git submodule update --init` after cloning.
- **ZIP users:** run `python setup_data.py` from the project root to download and extract the data.
- **Ongoing updates:** run `python src/init.py` daily to append new trading days.

Data is sourced from [NSE Website daily reports](https://www.nseindia.com/all-reports).

---

## Folder Layout

```
NSE_eod_data/
├── daily/              # OHLCV per stock  (one CSV per symbol)
├── delivery/           # Delivery data per stock
├── indices/            # Index data  (nifty 50.csv, bank nifty.csv, etc.)
├── sector_watchlist.csv  # List of available indices (used by plot.py)
└── metadata.json       # Sync state (last update date, pending delivery dates)
```

---

## File Format

### Stock CSV (`daily/RELIANCE.csv`)

```
Date,Open,High,Low,Close,Volume,Deliverable Volume,% Dly Qt to Traded Qty,DLV_QTY,QTY_PER_TRADE
2024-01-15,2800.50,2830.00,2795.00,2820.95,3456789,1234567,35.72,1234567,523
```

- All prices are **split- and bonus-adjusted** — historical data is restated whenever a corporate action occurs.
- 9 columns for stocks, 10 for indices (indices include a `Series` column).
- Date index is `datetime64[ns]`.

### metadata.json

```json
{
    "data-version": 3.2,
    "lastUpdate": "2026-04-11",
    "DLV_PENDING_DATES": [],
    "special-sessions": []
}
```

| Key | Description |
|-----|-------------|
| `data-version` | Must match `Config.EXPECTED_DATA_VERSION` — controls schema compatibility |
| `lastUpdate` | Last date successfully synced. `init.py` resumes from the next trading day |
| `DLV_PENDING_DATES` | Dates where delivery data was unavailable. Retried automatically |
| `special-sessions` | Post-market / Muhurat trading session dates |

---

## Do Not Edit Manually

- Do not add, remove, or reorder CSV columns — the diagnostic tool and rollback logic depend on the exact schema.
- Do not edit `metadata.json` unless recovering from a corrupted state. If `lastUpdate` is wrong, `init.py` will re-sync from that date.

---

## Checking Data Integrity

Run the diagnostic tool to scan for duplicate dates, type mismatches, missing values, and column count errors:

```bash
cd src
python -m funcdefs.diagnostic
```

The base repo data is updated weekly and maintained with strict integrity checks.
