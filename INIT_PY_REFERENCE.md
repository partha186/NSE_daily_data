# init.py — Reference Guide

## Location

`src/init.py`

## Purpose

Daily data synchronisation script. Connects to NSE, downloads equity, index, and delivery data for all missing trading dates, applies corporate-action adjustments (splits, bonuses), and keeps `NSE_eod_data/` current.

---

## Usage

```bash
cd src

# Sync all missing days (normal daily use)
python init.py

# Show EOD2 version and data version
python init.py --version

# Print current configuration
python init.py --config
```

---

## Startup Sequence (runs once)

### 1. Version checks

```
NSE library version >= 1.2.4  →  OK / exit with upgrade instructions
eod2_data version == EXPECTED_DATA_VERSION  →  OK / exit with setup instructions
```

If either check fails the script prints the corrective action and exits before touching any data.

### 2. Global exception hook

```python
sys.excepthook = funcdefs.log_unhandled_exception
```

Any uncaught exception writes a structured log entry (including EOD2 version, NSE version, last update date) to `error.log` before the process exits.

### 3. CLI argument parsing

| Argument | Effect |
|----------|--------|
| `-v` / `--version` | Print EOD2 + data version and exit |
| `-c` / `--config` | Print all configuration settings and exit |

### 4. NSE server connection

```python
nse = NSE(funcdefs.DIR, server=True)
```

Fails fast on `TimeoutError`, `ConnectionError`, or `ConnectError`. Does not enter the main loop if NSE is unreachable.

### 5. One-time initialisation

| Task | What it does |
|------|-------------|
| Special sessions | Detects post-market / Muhurat sessions; updates metadata if changed |
| AmiBroker update | Converts CSV data to AmiBroker format if `AMIBROKER = True` and records are stale |
| Pending delivery | Loads `DLV_PENDING_DATES` from metadata and schedules a retry for each queued date |

---

## Main Loop

The loop runs for every un-synced trading date from `lastUpdate` to today, then exits.

### Step 1 — Get next date

```python
if not funcdefs.dates.nextDate():
    nse.exit()
    sys.exit(0)
```

Advances the internal date pointer. Exits cleanly when no more dates need processing.

### Step 2 — Holiday check

```python
if funcdefs.checkForHolidays(nse):
    funcdefs.meta["lastUpdate"] = funcdefs.dates.dt
    writeJson(metaPath, funcdefs.meta)
    continue
```

Skips weekends and NSE trading holidays. Updates `lastUpdate` so progress is not lost.

### Step 3 — Validate corporate actions file

```python
funcdefs.validateNseActionsFile(nse)
```

Ensures the file listing upcoming splits and bonuses is current. Required for the adjustment step later.

### Step 4 — Report status check (today's date only)

Asks NSE whether the following reports are published:

| Report key | Type | Required |
|------------|------|----------|
| `CM-UDIFF-BHAVCOPY-CSV` | Equity prices | Critical |
| `INDEX-SNAPSHOT` | Index data | Critical |
| `CM-BHAVDATA-FULL` | Delivery data | Optional (retried if absent) |

If a critical report is not yet available the loop waits or exits, depending on the time of day.

### Step 5 — Download data

Three files are downloaded to a temporary location:

| Variable | Content |
|----------|---------|
| `BHAV_FILE` | OHLCV for every NSE-listed equity |
| `INDEX_FILE` | OHLCV for all tracked indices |
| `DELIVERY_FILE` | Delivery qty, traded qty, DLV% for each equity |

If `DELIVERY_FILE` cannot be downloaded (report not yet published by NSE), the date is queued in `DLV_PENDING_DATES` for automatic retry.

On Saturday, a missing file is silently skipped (some reports are not published on Saturdays).

### Step 6 — Database update

```python
funcdefs.updateNseEOD(BHAV_FILE, DELIVERY_FILE)
funcdefs.updateIndexEOD(INDEX_FILE)
```

Appends one row per stock/index to the respective CSV in `NSE_eod_data/`.

**On any exception:**
1. `funcdefs.rollback()` — removes all rows written for this date
2. Temporary files deleted
3. `lastUpdate` recorded (to avoid re-processing the same date)
4. Process exits

### Step 7 — Adjustments

```python
funcdefs.adjustNseStocks()
```

Rewrites historical price and volume columns for any stocks that had a split or bonus effective on this date. Uses the pre-validated corporate-actions file.

**On any exception:** same rollback procedure as Step 6.

### Step 8 — User hook

```python
if funcdefs.hook and hasattr(funcdefs.hook, "on_complete"):
    funcdefs.hook.on_complete()
```

Calls user-defined post-sync code (notifications, exports, triggers). Failure here does not abort the sync — the error is logged as a warning and the loop continues.

### Step 9 — Cleanup and metadata update

1. Delete downloaded temporary files
2. Remove very old raw bhavcopy archives (today's sync only)
3. Write updated `metadata.json`:
   - `lastUpdate` ← current date
   - `DLV_PENDING_DATES` ← updated list (retry successes removed)
   - `special-sessions` ← updated if changed

---

## Key Variables

| Variable | Type | Description |
|----------|------|-------------|
| `nse` | `NSE` | Open connection to NSE data source |
| `logger` | `logging.Logger` | Root logger; writes to console and `error.log` |
| `funcdefs.dates.dt` | `datetime` | Date currently being processed |
| `funcdefs.dates.today` | `datetime` | Today's date |
| `funcdefs.meta` | `dict` | Loaded from / written back to `metadata.json` |
| `BHAV_FILE` | `Path` | Downloaded equity CSV (temp) |
| `INDEX_FILE` | `Path` | Downloaded index CSV (temp) |
| `DELIVERY_FILE` | `Path` | Downloaded delivery CSV (temp) |

---

## metadata.json Structure

```json
{
    "data-version": 3.2,
    "lastUpdate": "2026-04-11",
    "DLV_PENDING_DATES": ["2026-04-08"],
    "special-sessions": []
}
```

| Key | Description |
|-----|-------------|
| `data-version` | Must match `Config.EXPECTED_DATA_VERSION` |
| `lastUpdate` | Last date successfully processed |
| `DLV_PENDING_DATES` | Dates missing delivery data — retried automatically |
| `special-sessions` | Post-market / Muhurat session dates |

---

## Error Reference

| Situation | What the script does |
|-----------|---------------------|
| NSE library outdated | Logs error + exits. Fix: `pip install -U nse` |
| Data version mismatch | Logs error + exits. Fix: `python setup_data.py` or `git pull` |
| No network connection | Logs warning + exits. Retry when online |
| Download failure | Rollback + exit. Retry next run |
| Delivery data missing | Queue in `DLV_PENDING_DATES`. Auto-retry next run |
| Adjustment failure | Rollback + exit. Check `error.log` |
| Market holiday | Skip date, update `lastUpdate`, continue loop |

---

## Function Reference

| Function | Where | Called at |
|----------|-------|-----------|
| `funcdefs.dates.nextDate()` | `funcdefs.py` | Start of each iteration |
| `funcdefs.checkForHolidays(nse)` | `funcdefs.py` | After getting next date |
| `funcdefs.check_special_sessions(nse)` | `funcdefs.py` | Startup only |
| `funcdefs.validateNseActionsFile(nse)` | `funcdefs.py` | Each iteration |
| `nse.equityBhavcopy(date)` | `nse/nse.py` | Download phase |
| `nse.indicesBhavcopy(date)` | `nse/nse.py` | Download phase |
| `nse.deliveryBhavcopy(date)` | `nse/nse.py` | Download phase |
| `funcdefs.updateNseEOD(bhav, dlv)` | `funcdefs.py` | Database update |
| `funcdefs.updateIndexEOD(idx)` | `funcdefs.py` | Database update |
| `funcdefs.adjustNseStocks()` | `funcdefs.py` | Adjustment phase |
| `funcdefs.rollback()` | `funcdefs.py` | On any update/adjust error |
| `funcdefs.cleanup()` | `funcdefs.py` | Finalization |
| `writeJson(path, data)` | `funcdefs/utils.py` | After metadata update |

---

## Common Issues

**Script runs and exits immediately without syncing**
- All dates already up to date. Check `metadata.json["lastUpdate"]`.

**Pending dates never clear**
- NSE may not have published the delivery report. The system retries automatically. Check the NSE website or wait until the next trading day.

**Rollback happened — what to do**
- Check `error.log` for the root cause.
- The failed date's data was not written. Simply rerun `init.py` to retry.

**`ImportError: funcdefs` not found**
- Always run from the `src/` directory: `cd src && python init.py`.

---

## Scheduling

Run once per trading day after market close (NSE closes at 15:30 IST; reports are usually available by 18:00–19:00 IST).

**Linux / Mac cron:**
```bash
30 18 * * 1-5 cd /path/to/eod2/src && python init.py >> ~/eod2.log 2>&1
```

**Windows Task Scheduler:**
Program: `python`  
Arguments: `src/init.py`  
Start in: `C:\path\to\eod2`  
Trigger: Daily, 6:30 PM, weekdays only
