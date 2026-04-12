"""
Live Signal Scanner - NIFTY & BANKNIFTY
Strategy: EMA 9/21 Crossover + ATR-based SL/TP
Display: Rich terminal dashboard (like the screenshot)

Install dependencies:
    pip install yfinance pandas numpy rich

Run:
    python live_scanner.py
"""

import yfinance as yf
import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box
import time
import threading
from queue import Queue
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────────────
SYMBOLS = {
    "NIFTY":     "^NSEI",
    "BANKNIFTY": "^NSEBANK",
}
TIMEFRAMES = {
    "30minute": "30m",
    "60minute": "1h",
}
SCAN_INTERVAL_SEC = 60       # how often to re-scan (seconds)
LOOKBACK_PERIOD   = "1d"     # only scan today's session
RR_TARGET         = 2.0      # take-profit = RR_TARGET × ATR
SL_MULTIPLIER     = 1.0      # stop-loss   = SL_MULTIPLIER × ATR
ATR_PERIOD        = 14

# PERFORMANCE OPTIMIZATIONS
CACHE_DF = {}                 # cache dataframes between scans
LAST_SCAN_TIMES = {}          # track last candle time per symbol/timeframe
WORKER_THREADS = 4            # parallel download threads

# ── LOT SIZES (NSE F&O) ──────────────────────────────────────────────────────
LOT_SIZES = {
    "NIFTY":     75,
    "BANKNIFTY": 30,
}
LOTS_TRADED = {          # ← change this to how many lots you trade
    "NIFTY":     1,
    "BANKNIFTY": 1,
}

console = Console()

# ── HELPERS ──────────────────────────────────────────────────────────────────
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def fetch_ohlcv(ticker_symbol: str, interval: str) -> pd.DataFrame | None:
    cache_key = (ticker_symbol, interval)
    
    try:
        # Only download new data if cache is empty or we have new candles
        if cache_key in CACHE_DF:
            existing_df = CACHE_DF[cache_key]
            last_ts = existing_df.index[-1]
            
            # download only last 5 candles instead of full day
            df = yf.download(
                ticker_symbol,
                period="5d" if interval == "1h" else "1d",
                interval=interval,
                progress=False,
                auto_adjust=True,
            )
        else:
            df = yf.download(
                ticker_symbol,
                period=LOOKBACK_PERIOD,
                interval=interval,
                progress=False,
                auto_adjust=True,
            )
            
        if df.empty or len(df) < 30:
            return None
            
        # flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Update cache
        CACHE_DF[cache_key] = df
        return df
    except Exception:
        return CACHE_DF.get(cache_key, None)

def detect_signals(df: pd.DataFrame, symbol: str, tf_label: str) -> list[dict]:
    """
    EMA 9/21 crossover.
    A BUY signal fires when ema9 crosses ABOVE ema21.
    A SELL signal fires when ema9 crosses BELOW ema21.
    """
    cache_key = (symbol, tf_label)
    last_scan = LAST_SCAN_TIMES.get(cache_key, df.index[0])
    
    # Only process rows that came after last scan
    new_rows = df[df.index > last_scan]
    
    if len(new_rows) < 3:
        # Not enough new data, compute full dataframe (first run)
        df = df.copy()
        df["ema9"]  = ema(df["Close"], 9)
        df["ema21"] = ema(df["Close"], 21)
        df["atr"]   = atr(df)
        process_df = df
    else:
        # Incremental update: compute only for new rows
        df = df.copy()
        df["ema9"]  = ema(df["Close"], 9)
        df["ema21"] = ema(df["Close"], 21)
        df["atr"]   = atr(df)
        process_df = new_rows
    
    df["cross_up"]   = (df["ema9"] > df["ema21"]) & (df["ema9"].shift(1) <= df["ema21"].shift(1))
    df["cross_down"]  = (df["ema9"] < df["ema21"]) & (df["ema9"].shift(1) >= df["ema21"].shift(1))
    
    found = []
    # Update last scan time
    LAST_SCAN_TIMES[cache_key] = df.index[-1]
    
    for ts, row in process_df.iterrows():
        if not (row["cross_up"] or row["cross_down"]):
            continue
        direction = "BUY" if row["cross_up"] else "SELL"
        entry     = round(float(row["Close"]), 2)
        atr_val   = float(row["atr"]) if not np.isnan(row["atr"]) else entry * 0.003
        sl_pts    = round(atr_val * SL_MULTIPLIER, 2)
        tp_pts    = round(atr_val * RR_TARGET, 2)
        rr        = f"1:{round(tp_pts / sl_pts, 1)}" if sl_pts > 0 else "1:?"

        # Convert timestamp to string
        if hasattr(ts, "strftime"):
            ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_str = str(ts)

        lot_size = LOT_SIZES.get(symbol, 1)
        lots     = LOTS_TRADED.get(symbol, 1)
        found.append({
            "time":      ts_str,
            "symbol":    symbol,
            "tf":        tf_label,
            "direction": direction,
            "entry":     entry,
            "sl_pts":    sl_pts,
            "tp_pts":    tp_pts,
            "rr":        rr,
            "result":    "OPEN",
            "pnl":       0.0,
            "pnl_inr":   0.0,
            "lot_size":  lot_size,
            "lots":      lots,
        })
    return found

def update_pnl(signals: list[dict], current_prices: dict) -> list[dict]:
    """Update PnL and result for each open signal."""
    for sig in signals:
        if sig["result"] != "OPEN":
            continue
        cp = current_prices.get(sig["symbol"])
        if cp is None:
            continue
        raw_pnl = cp - sig["entry"]
        if sig["direction"] == "SELL":
            raw_pnl = -raw_pnl
        sig["pnl"]     = round(raw_pnl, 1)
        sig["pnl_inr"] = round(raw_pnl * sig["lot_size"] * sig["lots"], 0)

        # Check if TP or SL hit
        if raw_pnl >= sig["tp_pts"]:
            sig["result"] = "WIN ✓"
        elif raw_pnl <= -sig["sl_pts"]:
            sig["result"] = "LOSS ✗"
    return signals

def get_current_prices() -> dict:
    prices = {}
    # Extract current prices from already cached OHLCV data (no extra API calls)
    for name, ticker in SYMBOLS.items():
        try:
            # Check 30min cache first (freshest data)
            cache_key = (ticker, "30m")
            if cache_key in CACHE_DF:
                df = CACHE_DF[cache_key]
                prices[name] = round(float(df["Close"].iloc[-1]), 2)
                continue
                
            # Fallback to 1h timeframe
            cache_key = (ticker, "1h")
            if cache_key in CACHE_DF:
                df = CACHE_DF[cache_key]
                prices[name] = round(float(df["Close"].iloc[-1]), 2)
        except Exception:
            pass
    return prices

# ── STATS ────────────────────────────────────────────────────────────────────
def compute_stats(signals: list[dict]) -> dict:
    total   = len(signals)
    winners = sum(1 for s in signals if "WIN"  in s["result"])
    losers  = sum(1 for s in signals if "LOSS" in s["result"])
    open_   = sum(1 for s in signals if s["result"] == "OPEN")
    no_fut  = sum(1 for s in signals if s["result"] == "NO_FUTURE_DATA")

    closed_wins  = [s["pnl"] for s in signals if "WIN"  in s["result"]]
    closed_loss  = [s["pnl"] for s in signals if "LOSS" in s["result"]]
    open_pnl     = [s["pnl"] for s in signals if s["result"] == "OPEN"]

    total_pnl    = round(sum(closed_wins + closed_loss + open_pnl), 2)
    avg_win      = round(np.mean(closed_wins),  2) if closed_wins  else 0.0
    avg_loss     = round(np.mean(closed_loss),  2) if closed_loss  else 0.0
    win_rate     = round(winners / (winners + losers) * 100, 1) if (winners + losers) > 0 else 0.0

    gross_profit = sum(closed_wins)
    gross_loss   = abs(sum(closed_loss))
    pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    # ₹ totals
    total_inr = round(sum(s.get('pnl_inr', 0) for s in signals), 0)

    return dict(
        total=total, winners=winners, losers=losers,
        open=open_, no_future=no_fut,
        total_pnl=total_pnl, avg_win=avg_win, avg_loss=avg_loss,
        win_rate=win_rate, profit_factor=pf,
        total_inr=total_inr,
    )

# ── RICH DISPLAY ─────────────────────────────────────────────────────────────
def build_display(signals: list[dict], stats: dict, last_scan: str) -> str:
    """Returns a renderable Rich object."""
    from rich.console import Group

    # ── Stats header ──
    pf_str = f"{stats['profit_factor']}" if stats['profit_factor'] != float("inf") else "∞"
    pnl_color = "green" if stats["total_pnl"] >= 0 else "red"

    header_lines = (
        f"[bold white]Total Signals[/] : {stats['total']}\n"
        f"[bold white]Winners[/]       : [green]{stats['winners']}[/]  |  "
        f"[bold white]Losers[/]: [red]{stats['losers']}[/]\n"
        f"[bold white]Win Rate[/]      : [cyan]{stats['win_rate']}%[/]\n"
        f"[bold white]Total PnL[/]     : [{pnl_color}]+{stats['total_pnl']} pts  (₹{stats['total_inr']:,.0f})[/{pnl_color}]\n"
        f"[bold white]Avg Win[/]       : [green]+{stats['avg_win']} pts[/]  |  "
        f"[bold white]Avg Loss[/]: [red]{stats['avg_loss']} pts[/]\n"
        f"[bold white]Profit Factor[/] : [yellow]{pf_str}[/]\n"
    )

    stats_panel = Panel(
        header_lines,
        title=f"[bold cyan]NIFTY / BANKNIFTY Signal Scanner[/]  •  [dim]{last_scan}[/]",
        border_style="cyan",
    )

    # ── Sub-stats ──
    sub = (
        f"  [dim]NO_FUTURE_DATA : {stats['no_future']}[/]\n"
        f"  [yellow]⏳ OPEN         : {stats['open']}[/]"
    )
    sub_panel = Panel(sub, border_style="dim", padding=(0, 1))

    # ── Signals table ──
    table = Table(
        show_header=True,
        header_style="bold white",
        box=box.SIMPLE_HEAD,
        style="on black",
        row_styles=["", "dim"],
        expand=True,
    )
    table.add_column("Signal Time",  style="white",   min_width=21)
    table.add_column("Symbol",       style="yellow",  min_width=10)
    table.add_column("Dir",          style="cyan",    min_width=5)
    table.add_column("TF",           style="white",   min_width=10)
    table.add_column("Entry",        justify="right", style="white",  min_width=10)
    table.add_column("PnL (pts)",     justify="right", min_width=9)
    table.add_column("PnL (INR)",     justify="right", min_width=12)
    table.add_column("RR",           justify="right", style="dim white", min_width=6)
    table.add_column("Result",       justify="right", min_width=12)

    for sig in reversed(signals):  # newest first
        pnl_val   = sig["pnl"]
        inr_val   = sig.get("pnl_inr", 0)
        pnl_color = "green" if pnl_val >= 0 else "red"
        pnl_str   = f"[{pnl_color}]{'+' if pnl_val >= 0 else ''}{pnl_val}[/{pnl_color}]"

        res = sig["result"]
        if res == "OPEN":
            res_str = "[yellow]⏳ OPEN[/]"
        elif "WIN" in res:
            res_str = "[bold green]WIN ✓[/]"
        elif "LOSS" in res:
            res_str = "[bold red]LOSS ✗[/]"
        else:
            res_str = f"[dim]{res}[/]"

        sign = "+" if inr_val >= 0 else ""
        inr_str   = f"[green]{sign}Rs{inr_val:,.0f}[/]" if inr_val >= 0 else f"[red]{sign}Rs{inr_val:,.0f}[/]"
        dir_str = "[green]▲ BUY[/]" if sig["direction"] == "BUY" else "[red]▼ SELL[/]"

        table.add_row(
            sig["time"],
            sig["symbol"],
            dir_str,
            sig["tf"],
            str(sig["entry"]),
            pnl_str,
            inr_str,
            sig["rr"],
            res_str,
        )

    return Group(stats_panel, sub_panel, table)

# ── MAIN LOOP ────────────────────────────────────────────────────────────────
def _worker(queue, results):
    while True:
        item = queue.get()
        if item is None:
            break
        sym_name, ticker, tf_label, yf_interval = item
        df = fetch_ohlcv(ticker, yf_interval)
        if df is not None:
            sigs = detect_signals(df, sym_name, tf_label)
            results.extend(sigs)
        queue.task_done()

def scan_all() -> list[dict]:
    """Fetch data for all symbols × timeframes in parallel and return new signals."""
    new_signals = []
    queue = Queue()
    threads = []
    
    # Start worker threads
    for _ in range(WORKER_THREADS):
        t = threading.Thread(target=_worker, args=(queue, new_signals), daemon=True)
        t.start()
        threads.append(t)
    
    # Add all tasks
    for sym_name, ticker in SYMBOLS.items():
        for tf_label, yf_interval in TIMEFRAMES.items():
            queue.put((sym_name, ticker, tf_label, yf_interval))
    
    # Wait for all tasks to complete
    queue.join()
    
    # Stop workers
    for _ in range(WORKER_THREADS):
        queue.put(None)
    for t in threads:
        t.join()
        
    return new_signals

def dedup(signals: list[dict]) -> list[dict]:
    """Remove duplicate signals (same time + symbol + tf + direction)."""
    seen = set()
    result = []
    for s in signals:
        key = (s["time"], s["symbol"], s["tf"], s["direction"])
        if key not in seen:
            seen.add(key)
            result.append(s)
    return result

def main():
    console.print("\n[bold cyan]Starting Live Scanner...[/]\n")
    all_signals: list[dict] = []
    from datetime import date
    today_str = date.today().strftime("%Y-%m-%d")

    with Live(console=console, refresh_per_second=1, screen=True) as live:
        while True:
            # 1. Scan for new signals
            new   = scan_all()
            all_signals = dedup(all_signals + new)

            # Keep only today's signals
            all_signals = [s for s in all_signals if s["time"].startswith(today_str)]

            # 2. Get current prices
            prices = get_current_prices()

            # 3. Update PnL
            all_signals = update_pnl(all_signals, prices)

            # 4. Compute stats & render
            stats    = compute_stats(all_signals)
            ts       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            display  = build_display(all_signals, stats, ts)
            live.update(display)

            # 5. Wait before next scan
            time.sleep(SCAN_INTERVAL_SEC)
            

if __name__ == "__main__":
    main()
