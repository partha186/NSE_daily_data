"""
strategy_runner.py
==================
Runs multiple trading strategies on all CSV stock files in a folder.
Outputs buy/sell signals and backtest results (P&L, win rate, etc.)

Usage:
    python strategy_runner.py --folder eod2_data/daily
    python strategy_runner.py --folder eod2_data/daily --strategy all
    python strategy_runner.py --folder eod2_data/daily --strategy ema_crossover
    python strategy_runner.py --folder eod2_data/daily --strategy rsi
    python strategy_runner.py --folder eod2_data/daily --strategy macd
    python strategy_runner.py --folder eod2_data/daily --strategy breakout
    python strategy_runner.py --folder eod2_data/daily --strategy supertrend
    python strategy_runner.py --folder eod2_data/daily --export results.csv

Available strategies:
    ema_crossover   - EMA 9/21 crossover
    rsi             - RSI 14 overbought/oversold
    macd            - MACD signal line crossover
    breakout        - 20-day high breakout with volume confirmation
    supertrend      - Supertrend (ATR-based trend following)
    bb_squeeze      - Bollinger Band squeeze breakout
    all             - Run all strategies (default)
"""

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────
#  INDICATORS
# ─────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast=12, slow=26, signal=9):
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
    _atr = atr(df, period)
    hl2 = (df["High"] + df["Low"]) / 2
    upper_band = hl2 + multiplier * _atr
    lower_band = hl2 - multiplier * _atr

    supertrend_vals = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)

    for i in range(1, len(df)):
        prev_close = df["Close"].iloc[i - 1]
        curr_close = df["Close"].iloc[i]

        # Lower band
        if lower_band.iloc[i] > lower_band.iloc[i - 1] or prev_close < supertrend_vals.iloc[i - 1]:
            final_lower = lower_band.iloc[i]
        else:
            final_lower = lower_band.iloc[i - 1]

        # Upper band
        if upper_band.iloc[i] < upper_band.iloc[i - 1] or prev_close > supertrend_vals.iloc[i - 1]:
            final_upper = upper_band.iloc[i]
        else:
            final_upper = upper_band.iloc[i - 1]

        prev_dir = direction.iloc[i - 1] if i > 1 else 1

        if prev_dir == -1 and curr_close > final_upper:
            direction.iloc[i] = 1
            supertrend_vals.iloc[i] = final_lower
        elif prev_dir == 1 and curr_close < final_lower:
            direction.iloc[i] = -1
            supertrend_vals.iloc[i] = final_upper
        else:
            direction.iloc[i] = prev_dir
            supertrend_vals.iloc[i] = final_lower if prev_dir == 1 else final_upper

    return supertrend_vals, direction


def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    bandwidth = (upper - lower) / mid
    return upper, mid, lower, bandwidth


# ─────────────────────────────────────────────
#  SIGNAL GENERATORS
# ─────────────────────────────────────────────

def signals_ema_crossover(df: pd.DataFrame) -> pd.Series:
    """EMA 9 crosses above EMA 21 → BUY; crosses below → SELL"""
    e9 = ema(df["Close"], 9)
    e21 = ema(df["Close"], 21)
    signal = pd.Series(0, index=df.index)
    signal[(e9 > e21) & (e9.shift() <= e21.shift())] = 1   # BUY
    signal[(e9 < e21) & (e9.shift() >= e21.shift())] = -1  # SELL
    return signal


def signals_rsi(df: pd.DataFrame, oversold=30, overbought=70) -> pd.Series:
    """RSI crosses above oversold → BUY; crosses below overbought → SELL"""
    r = rsi(df["Close"])
    signal = pd.Series(0, index=df.index)
    signal[(r > oversold) & (r.shift() <= oversold)] = 1
    signal[(r < overbought) & (r.shift() >= overbought)] = -1
    return signal


def signals_macd(df: pd.DataFrame) -> pd.Series:
    """MACD crosses above signal line → BUY; crosses below → SELL"""
    macd_line, signal_line, _ = macd(df["Close"])
    signal = pd.Series(0, index=df.index)
    signal[(macd_line > signal_line) & (macd_line.shift() <= signal_line.shift())] = 1
    signal[(macd_line < signal_line) & (macd_line.shift() >= signal_line.shift())] = -1
    return signal


def signals_breakout(df: pd.DataFrame, period: int = 20, vol_mult: float = 1.5) -> pd.Series:
    """Price breaks above N-day high with above-average volume → BUY"""
    roll_high = df["Close"].rolling(period).max().shift(1)
    avg_vol = df["Volume"].rolling(period).mean().shift(1) if "Volume" in df.columns else None

    signal = pd.Series(0, index=df.index)
    breakout = df["Close"] > roll_high

    if avg_vol is not None:
        vol_confirm = df["Volume"] > vol_mult * avg_vol
        signal[breakout & vol_confirm] = 1
    else:
        signal[breakout] = 1

    # Exit: price drops below 10-day EMA
    e10 = ema(df["Close"], 10)
    signal[(df["Close"] < e10) & (df["Close"].shift() >= e10.shift())] = -1
    return signal


def signals_supertrend(df: pd.DataFrame) -> pd.Series:
    """Supertrend direction change → BUY/SELL"""
    _, direction = supertrend(df)
    signal = pd.Series(0, index=df.index)
    signal[(direction == 1) & (direction.shift() == -1)] = 1
    signal[(direction == -1) & (direction.shift() == 1)] = -1
    return signal


def signals_bb_squeeze(df: pd.DataFrame) -> pd.Series:
    """Price breaks above upper BB after squeeze (low bandwidth) → BUY"""
    upper, mid, lower, bw = bollinger_bands(df["Close"])
    squeeze = bw < bw.rolling(50).quantile(0.2)  # bandwidth in bottom 20% = squeeze
    signal = pd.Series(0, index=df.index)
    breakout_up = (df["Close"] > upper) & squeeze.shift(1)
    breakout_dn = (df["Close"] < lower) & squeeze.shift(1)
    signal[breakout_up] = 1
    signal[breakout_dn] = -1
    return signal


STRATEGIES = {
    "ema_crossover": signals_ema_crossover,
    "rsi":           signals_rsi,
    "macd":          signals_macd,
    "breakout":      signals_breakout,
    "supertrend":    signals_supertrend,
    "bb_squeeze":    signals_bb_squeeze,
}


# ─────────────────────────────────────────────
#  BACKTESTER
# ─────────────────────────────────────────────

def backtest(df: pd.DataFrame, signals: pd.Series,
             sl_pct: float = 0.03, tp_pct: float = 0.09) -> dict:
    """
    Simple long-only backtester with stop-loss and take-profit.

    sl_pct : stop loss  (default 3%)
    tp_pct : take profit (default 9%)
    """
    trades = []
    position = None  # {"entry_date", "entry_price"}

    for date, sig in signals.items():
        close = df.loc[date, "Close"]

        if position is None:
            if sig == 1:
                position = {"entry_date": date, "entry_price": close}
        else:
            entry = position["entry_price"]
            sl_price = entry * (1 - sl_pct)
            tp_price = entry * (1 + tp_pct)

            hit_sl = close <= sl_price
            hit_tp = close >= tp_price
            got_sell = sig == -1

            if hit_tp or hit_sl or got_sell:
                exit_price = tp_price if hit_tp else (sl_price if hit_sl else close)
                pnl_pct = (exit_price - entry) / entry * 100
                reason = "TP" if hit_tp else ("SL" if hit_sl else "Signal")

                trades.append({
                    "entry_date":  position["entry_date"],
                    "exit_date":   date,
                    "entry_price": round(entry, 2),
                    "exit_price":  round(exit_price, 2),
                    "pnl_pct":     round(pnl_pct, 2),
                    "reason":      reason,
                    "win":         pnl_pct > 0,
                })
                position = None

    if not trades:
        return {
            "total_trades": 0,
            "win_rate":     0.0,
            "avg_pnl":      0.0,
            "total_pnl":    0.0,
            "max_win":      0.0,
            "max_loss":     0.0,
            "trades":       [],
        }

    tdf = pd.DataFrame(trades)
    return {
        "total_trades": len(tdf),
        "win_rate":     round(tdf["win"].mean() * 100, 1),
        "avg_pnl":      round(tdf["pnl_pct"].mean(), 2),
        "total_pnl":    round(tdf["pnl_pct"].sum(), 2),
        "max_win":      round(tdf["pnl_pct"].max(), 2),
        "max_loss":     round(tdf["pnl_pct"].min(), 2),
        "trades":       trades,
    }


# ─────────────────────────────────────────────
#  FILE LOADER
# ─────────────────────────────────────────────

def load_csv(fpath: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(fpath, parse_dates=True)

        # Normalize column names
        df.columns = [c.strip().title() for c in df.columns]

        # Try common date column names
        for col in ["Date", "Timestamp", "Mtimestamp", "Time"]:
            if col in df.columns:
                df = df.rename(columns={col: "Date"})
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()
                break

        # Try to map common OHLCV column names
        rename_map = {}
        col_lower = {c.lower(): c for c in df.columns}
        for target, candidates in {
            "Open":   ["open", "ch_opening_price", "open_price"],
            "High":   ["high", "ch_trade_high_price", "high_price"],
            "Low":    ["low",  "ch_trade_low_price",  "low_price"],
            "Close":  ["close", "ch_closing_price", "close_price", "last", "ltp"],
            "Volume": ["volume", "ch_tot_trd_qnty", "tottrdqty", "qty_traded"],
        }.items():
            for cand in candidates:
                if cand in col_lower:
                    rename_map[col_lower[cand]] = target
                    break

        df = df.rename(columns=rename_map)

        required = ["Open", "High", "Low", "Close"]
        if not all(c in df.columns for c in required):
            return None

        df = df[df["Close"].notna()]
        df[required] = df[required].apply(pd.to_numeric, errors="coerce")

        return df if len(df) >= 50 else None

    except Exception:
        return None


# ─────────────────────────────────────────────
#  LATEST SIGNALS EXTRACTOR
# ─────────────────────────────────────────────

def latest_signal(signals: pd.Series) -> str:
    last = signals[signals != 0]
    if last.empty:
        return "NONE"
    val = last.iloc[-1]
    date = last.index[-1]
    label = "BUY" if val == 1 else "SELL"
    return f"{label} ({date.strftime('%d-%b-%Y')})"


# ─────────────────────────────────────────────
#  PRINTER
# ─────────────────────────────────────────────

class c:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[1;92m"
    RED    = "\033[1;91m"
    YELLOW = "\033[1;93m"
    CYAN   = "\033[0;96m"
    WHITE  = "\033[1;37m"
    DIM    = "\033[2m"

    @staticmethod
    def pnl(v):
        if v > 0:
            return f"{c.GREEN}+{v}%{c.RESET}"
        elif v < 0:
            return f"{c.RED}{v}%{c.RESET}"
        return f"{c.DIM}{v}%{c.RESET}"

    @staticmethod
    def signal(s):
        if "BUY" in s:
            return f"{c.GREEN}{s}{c.RESET}"
        if "SELL" in s:
            return f"{c.RED}{s}{c.RESET}"
        return f"{c.DIM}{s}{c.RESET}"


def print_result(symbol: str, strategy: str, bt: dict, sig: str):
    win_color = c.GREEN if bt["win_rate"] >= 50 else c.RED
    print(
        f"{c.CYAN}{symbol[:14].upper().ljust(15)}{c.RESET}"
        f"{c.YELLOW}{strategy.ljust(16)}{c.RESET}"
        f"Trades:{c.WHITE}{str(bt['total_trades']).rjust(4)}{c.RESET}  "
        f"WinRate:{win_color}{str(bt['win_rate']).rjust(6)}%{c.RESET}  "
        f"AvgPnL:{c.pnl(bt['avg_pnl']).rjust(10)}  "
        f"TotalPnL:{c.pnl(bt['total_pnl']).rjust(10)}  "
        f"Signal:{c.signal(sig).rjust(25)}"
    )


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def run(folder: str, strategy_name: str = "all",
        sl_pct: float = 0.03, tp_pct: float = 0.09,
        export: str | None = None):

    folder_path = Path(folder)
    csv_files = sorted(folder_path.glob("*.csv"))

    if not csv_files:
        print(f"No CSV files found in: {folder_path}")
        return

    strategies_to_run = STRATEGIES if strategy_name == "all" else {
        strategy_name: STRATEGIES[strategy_name]
    }

    print(f"\n{c.BOLD}{c.WHITE}{'─'*110}{c.RESET}")
    print(
        f"{c.BOLD}{c.WHITE}"
        f"{'SYMBOL'.ljust(15)}{'STRATEGY'.ljust(16)}"
        f"{'TRADES'.ljust(12)}{'WIN%'.ljust(12)}"
        f"{'AVG PnL'.ljust(12)}{'TOTAL PnL'.ljust(14)}{'LATEST SIGNAL'}"
        f"{c.RESET}"
    )
    print(f"{c.BOLD}{c.WHITE}{'─'*110}{c.RESET}")

    all_results = []
    skipped = []

    for fpath in csv_files:
        symbol = fpath.stem.upper()
        df = load_csv(fpath)

        if df is None:
            skipped.append(symbol)
            continue

        for strat_name, strat_fn in strategies_to_run.items():
            try:
                signals = strat_fn(df)
                bt = backtest(df, signals, sl_pct=sl_pct, tp_pct=tp_pct)
                sig = latest_signal(signals)

                print_result(symbol, strat_name, bt, sig)

                all_results.append({
                    "symbol":       symbol,
                    "strategy":     strat_name,
                    "total_trades": bt["total_trades"],
                    "win_rate":     bt["win_rate"],
                    "avg_pnl":      bt["avg_pnl"],
                    "total_pnl":    bt["total_pnl"],
                    "max_win":      bt["max_win"],
                    "max_loss":     bt["max_loss"],
                    "latest_signal": sig,
                })
            except Exception as e:
                print(f"{c.RED}ERROR{c.RESET} {symbol} / {strat_name}: {e}")

    print(f"{c.BOLD}{c.WHITE}{'─'*110}{c.RESET}")

    # Summary
    if all_results:
        rdf = pd.DataFrame(all_results)
        print(f"\n{c.BOLD}{c.WHITE}── SUMMARY ──{c.RESET}")
        for strat in rdf["strategy"].unique():
            sdf = rdf[rdf["strategy"] == strat]
            avg_wr = sdf["win_rate"].mean()
            avg_pnl = sdf["avg_pnl"].mean()
            buys = sdf["latest_signal"].str.contains("BUY").sum()
            sells = sdf["latest_signal"].str.contains("SELL").sum()
            print(
                f"  {c.YELLOW}{strat.ljust(16)}{c.RESET}"
                f"Avg WinRate: {c.GREEN if avg_wr>=50 else c.RED}{avg_wr:.1f}%{c.RESET}  "
                f"Avg PnL: {c.pnl(round(avg_pnl,2))}  "
                f"Active BUYs: {c.GREEN}{buys}{c.RESET}  "
                f"Active SELLs: {c.RED}{sells}{c.RESET}"
            )

    if skipped:
        print(f"\n{c.DIM}Skipped (missing OHLC or too few rows): {', '.join(skipped)}{c.RESET}")

    # Export
    if export and all_results:
        out = Path(export)
        pd.DataFrame(all_results).to_csv(out, index=False)
        print(f"\n{c.GREEN}Results exported to: {out.resolve()}{c.RESET}")

    print()


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Multi-strategy backtest runner for NSE CSV files"
    )
    parser.add_argument(
        "--folder", required=True,
        help="Path to folder containing stock CSV files"
    )
    parser.add_argument(
        "--strategy", default="all",
        choices=list(STRATEGIES.keys()) + ["all"],
        help="Strategy to run (default: all)"
    )
    parser.add_argument(
        "--sl", type=float, default=0.03,
        help="Stop loss %% as decimal (default: 0.03 = 3%%)"
    )
    parser.add_argument(
        "--tp", type=float, default=0.09,
        help="Take profit %% as decimal (default: 0.09 = 9%%)"
    )
    parser.add_argument(
        "--export", default=None,
        help="Export results to CSV file path"
    )

    args = parser.parse_args()

    if args.strategy not in list(STRATEGIES.keys()) + ["all"]:
        parser.error(f"Unknown strategy: {args.strategy}")

    run(
        folder=args.folder,
        strategy_name=args.strategy,
        sl_pct=args.sl,
        tp_pct=args.tp,
        export=args.export,
    )