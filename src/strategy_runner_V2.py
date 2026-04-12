"""
strategy_runner_v2.py
=====================
Runs all strategies from your reference code on local NSE CSV files.
Includes: KeltnerChannel, BollingerBands, MA, MACD, RSI, WilliamsR,
          Stochastic Fast/Slow, Ichimoku — each in Long+Short and Long-only mode.

Install deps:
    pip install pandas ta numpy

Usage:
    # Run all strategies on all CSVs
    python strategy_runner_v2.py --folder eod2_data/daily

    # Single strategy
    python strategy_runner_v2.py --folder eod2_data/daily --strategy rsi_long

    # Custom SL, starting capital, export results
    python strategy_runner_v2.py --folder eod2_data/daily --sl -3 --capital 100000 --export results.csv

    # Find best strategy per stock (slow — tests all param combos)
    python strategy_runner_v2.py --folder eod2_data/daily --optimize
"""

import argparse
import warnings
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import ta

warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────
#  STRATEGIES  (long+short and long-only pairs)
# ─────────────────────────────────────────────

def strategy_KeltnerChannel(df, **kwargs):
    n = kwargs.get("n", 10)
    data = df.copy()
    kb = ta.volatility.KeltnerChannel(data.High, data.Low, data.Close, n)
    data["K_UB"] = kb.keltner_channel_hband().round(4)
    data["K_LB"] = kb.keltner_channel_lband().round(4)
    data["CP"] = data.Close.shift(3)
    data["LONG"]       = (data.Close <= data.K_LB) & (data.CP > data.K_LB)
    data["EXIT_LONG"]  = (data.Close >= data.K_UB) & (data.CP < data.K_UB)
    data["SHORT"]      = (data.Close >= data.K_UB) & (data.CP < data.K_UB)
    data["EXIT_SHORT"] = (data.Close <= data.K_LB) & (data.CP > data.K_LB)
    for col in ["LONG", "EXIT_LONG", "SHORT", "EXIT_SHORT"]:
        data[col] = data[col].shift(1)
    return data

def strategy_KeltnerChannel_long(df, **kwargs):
    data = strategy_KeltnerChannel(df, **kwargs)
    data["SHORT"] = False; data["EXIT_SHORT"] = False
    return data

def strategy_BollingerBands(df, **kwargs):
    n = kwargs.get("n", 20); n_rng = kwargs.get("n_rng", 2)
    data = df.copy()
    boll = ta.volatility.BollingerBands(data.Close, n, n_rng)
    data["BOLL_L_IND"] = boll.bollinger_lband_indicator()
    data["BOLL_U_IND"] = boll.bollinger_hband_indicator()
    data["LONG"]       = data.BOLL_L_IND == 1
    data["EXIT_LONG"]  = data.BOLL_U_IND == 1
    data["SHORT"]      = data.BOLL_U_IND == 1
    data["EXIT_SHORT"] = data.BOLL_L_IND == 1
    for col in ["LONG", "EXIT_LONG", "SHORT", "EXIT_SHORT"]:
        data[col] = data[col].shift(1)
    return data

def strategy_BollingerBands_long(df, **kwargs):
    data = strategy_BollingerBands(df, **kwargs)
    data["SHORT"] = False; data["EXIT_SHORT"] = False
    return data

def strategy_MA(df, **kwargs):
    n = kwargs.get("n", 20); ma_type = kwargs.get("ma_type", "sma").lower()
    data = df.copy()
    if ma_type == "ema":
        data["MA"] = ta.trend.EMAIndicator(data.Close, n).ema_indicator().round(4)
    else:
        data["MA"] = ta.trend.SMAIndicator(data.Close, n).sma_indicator().round(4)
    data["CP"] = data.Close.shift(3)
    data["LONG"]       = (data.Close > data.MA) & (data.CP <= data.MA)
    data["EXIT_LONG"]  = (data.Close < data.MA) & (data.CP >= data.MA)
    data["SHORT"]      = (data.Close < data.MA) & (data.CP >= data.MA)
    data["EXIT_SHORT"] = (data.Close > data.MA) & (data.CP <= data.MA)
    for col in ["LONG", "EXIT_LONG", "SHORT", "EXIT_SHORT"]:
        data[col] = data[col].shift(1)
    return data

def strategy_MA_long(df, **kwargs):
    data = strategy_MA(df, **kwargs)
    data["SHORT"] = False; data["EXIT_SHORT"] = False
    return data

def strategy_MACD(df, **kwargs):
    n_slow = kwargs.get("n_slow", 22); n_fast = kwargs.get("n_fast", 10); n_sign = kwargs.get("n_sign", 8)
    data = df.copy()
    _macd = ta.trend.MACD(data.Close, n_slow, n_fast, n_sign)
    data["MACD_DIFF"] = _macd.macd_diff().round(4)
    data["MACD_PREV"] = data.MACD_DIFF.shift()
    data["LONG"]       = (data.MACD_DIFF > 0) & (data.MACD_PREV <= 0)
    data["EXIT_LONG"]  = (data.MACD_DIFF < 0) & (data.MACD_PREV >= 0)
    data["SHORT"]      = (data.MACD_DIFF < 0) & (data.MACD_PREV >= 0)
    data["EXIT_SHORT"] = (data.MACD_DIFF > 0) & (data.MACD_PREV <= 0)
    for col in ["LONG", "EXIT_LONG", "SHORT", "EXIT_SHORT"]:
        data[col] = data[col].shift(1)
    return data

def strategy_MACD_long(df, **kwargs):
    data = strategy_MACD(df, **kwargs)
    data["SHORT"] = False; data["EXIT_SHORT"] = False
    return data

def strategy_RSI(df, **kwargs):
    n = kwargs.get("n", 14)
    data = df.copy()
    data["RSI"] = ta.momentum.RSIIndicator(data.Close, n).rsi().round(4)
    data["RSI_P"] = data.RSI.shift(1)
    data["LONG"]       = (data.RSI < 30) & (data.RSI_P >= 30)
    data["EXIT_LONG"]  = (data.RSI > 70) & (data.RSI_P <= 70)
    data["SHORT"]      = (data.RSI > 70) & (data.RSI_P <= 70)
    data["EXIT_SHORT"] = (data.RSI < 30) & (data.RSI_P >= 30)
    for col in ["LONG", "EXIT_LONG", "SHORT", "EXIT_SHORT"]:
        data[col] = data[col].shift(1)
    return data

def strategy_RSI_long(df, **kwargs):
    data = strategy_RSI(df, **kwargs)
    data["SHORT"] = False; data["EXIT_SHORT"] = False
    return data

def strategy_WR(df, **kwargs):
    n = kwargs.get("n", 14)
    data = df.copy()
    data["WR"] = ta.momentum.WilliamsRIndicator(data.High, data.Low, data.Close, n).williams_r().round(4)
    data["WR_P"] = data.WR.shift(1)
    data["LONG"]       = (data.WR < -80) & (data.WR_P >= -80)
    data["EXIT_LONG"]  = (data.WR > -20) & (data.WR_P <= -20)
    data["SHORT"]      = (data.WR > -20) & (data.WR_P <= -20)
    data["EXIT_SHORT"] = (data.WR < -80) & (data.WR_P >= -80)
    for col in ["LONG", "EXIT_LONG", "SHORT", "EXIT_SHORT"]:
        data[col] = data[col].shift(1)
    return data

def strategy_WR_long(df, **kwargs):
    data = strategy_WR(df, **kwargs)
    data["SHORT"] = False; data["EXIT_SHORT"] = False
    return data

def strategy_Stochastic_fast(df, **kwargs):
    k = kwargs.get("k", 20); d = kwargs.get("d", 5)
    data = df.copy()
    sto = ta.momentum.StochasticOscillator(data.High, data.Low, data.Close, k, d)
    data["K"] = sto.stoch().round(4)
    data["D"] = sto.stoch_signal().round(4)
    data["DIFF"] = data.K - data.D
    data["DIFF_P"] = data.DIFF.shift(1)
    data["LONG"]       = (data.DIFF > 0) & (data.DIFF_P <= 0)
    data["EXIT_LONG"]  = (data.DIFF < 0) & (data.DIFF_P >= 0)
    data["SHORT"]      = (data.DIFF < 0) & (data.DIFF_P >= 0)
    data["EXIT_SHORT"] = (data.DIFF > 0) & (data.DIFF_P <= 0)
    for col in ["LONG", "EXIT_LONG", "SHORT", "EXIT_SHORT"]:
        data[col] = data[col].shift(1)
    return data

def strategy_Stochastic_fast_long(df, **kwargs):
    data = strategy_Stochastic_fast(df, **kwargs)
    data["SHORT"] = False; data["EXIT_SHORT"] = False
    return data

def strategy_Stochastic_slow(df, **kwargs):
    k = kwargs.get("k", 20); d = kwargs.get("d", 5); dd = kwargs.get("dd", 3)
    data = df.copy()
    sto = ta.momentum.StochasticOscillator(data.High, data.Low, data.Close, k, d)
    data["K"] = sto.stoch().round(4)
    data["D"] = sto.stoch_signal().round(4)
    data["DD"] = ta.trend.SMAIndicator(data.D, dd).sma_indicator().round(4)
    data["DIFF"] = data.D - data.DD
    data["DIFF_P"] = data.DIFF.shift(1)
    data["LONG"]       = (data.DIFF > 0) & (data.DIFF_P <= 0)
    data["EXIT_LONG"]  = (data.DIFF < 0) & (data.DIFF_P >= 0)
    data["SHORT"]      = (data.DIFF < 0) & (data.DIFF_P >= 0)
    data["EXIT_SHORT"] = (data.DIFF > 0) & (data.DIFF_P <= 0)
    for col in ["LONG", "EXIT_LONG", "SHORT", "EXIT_SHORT"]:
        data[col] = data[col].shift(1)
    return data

def strategy_Stochastic_slow_long(df, **kwargs):
    data = strategy_Stochastic_slow(df, **kwargs)
    data["SHORT"] = False; data["EXIT_SHORT"] = False
    return data

def strategy_Ichimoku(df, **kwargs):
    n_conv = kwargs.get("n_conv", 9); n_base = kwargs.get("n_base", 26); n_span_b = kwargs.get("n_span_b", 52)
    data = df.copy()
    ich = ta.trend.IchimokuIndicator(data.High, data.Low, n_conv, n_base, n_span_b)
    data["BASE"] = ich.ichimoku_base_line().round(4)
    data["CONV"] = ich.ichimoku_conversion_line().round(4)
    data["DIFF"] = data.CONV - data.BASE
    data["DIFF_P"] = data.DIFF.shift()
    data["LONG"]       = (data.DIFF > 0) & (data.DIFF_P <= 0)
    data["EXIT_LONG"]  = (data.DIFF < 0) & (data.DIFF_P >= 0)
    data["SHORT"]      = (data.DIFF < 0) & (data.DIFF_P >= 0)
    data["EXIT_SHORT"] = (data.DIFF > 0) & (data.DIFF_P <= 0)
    for col in ["LONG", "EXIT_LONG", "SHORT", "EXIT_SHORT"]:
        data[col] = data[col].shift(1)
    return data

def strategy_Ichimoku_long(df, **kwargs):
    data = strategy_Ichimoku(df, **kwargs)
    data["SHORT"] = False; data["EXIT_SHORT"] = False
    return data


# Registry
STRATEGIES = {
    "keltner":            strategy_KeltnerChannel,
    "bollinger":          strategy_BollingerBands,
    "ma":                 strategy_MA,
    "macd":               strategy_MACD,
    "rsi":                strategy_RSI,
    "wr":                 strategy_WR,
    "stoch_fast":         strategy_Stochastic_fast,
    "stoch_slow":         strategy_Stochastic_slow,
    "ichimoku":           strategy_Ichimoku,
}

# Default params for optimization search
OPTIMIZE_PARAMS = {
    "keltner_long":       {"n": range(5, 30, 5)},
    "bollinger_long":     {"n": range(5, 30, 5), "n_rng": [1, 2, 3, 4]},
    "ma_long":            {"n": range(10, 110, 10), "ma_type": ["sma", "ema"]},
    "macd_long":          {"n_slow": range(20, 26), "n_fast": range(10, 16), "n_sign": range(5, 11)},
    "rsi_long":           {"n": range(3, 15)},
    "wr_long":            {"n": range(3, 15)},
    "stoch_fast_long":    {"k": range(15, 26), "d": range(5, 11)},
    "stoch_slow_long":    {"k": range(15, 26), "d": range(5, 11), "dd": range(1, 6)},
    "ichimoku_long":      {"n_conv": range(5, 16), "n_base": range(20, 36), "n_span_b": [26]},
}


# ─────────────────────────────────────────────
#  BACKTESTER
# ─────────────────────────────────────────────

def run_backtest(bt_df: pd.DataFrame, capital: float = 10000,
                 stop_loss_pct: float | None = None) -> dict:
    """
    Backtest long+short signals with optional stop loss.
    Uses Open price for entries/exits (next candle open after signal).
    """
    balance = capital
    position = 0
    last_signal = "hold"
    last_price = 0
    c = 0

    trade_starts, trade_ends, trade_sides = [], [], []
    trade_days, trade_pnl, trade_ret = [], [], []
    cum_value = []

    for _, row in bt_df.iterrows():
        open_p = row.get("Open", row.Close)

        # ── EXIT ──
        if row.EXIT_LONG and last_signal == "long":
            pnl = (open_p - last_price) * position
            _record_trade(trade_ends, trade_days, trade_pnl, trade_ret,
                          row.name, c, pnl, open_p, last_price, "long")
            balance += open_p * position
            position = 0; last_signal = "hold"; c = 0

        elif row.EXIT_SHORT and last_signal == "short":
            pnl = (open_p - last_price) * position
            _record_trade(trade_ends, trade_days, trade_pnl, trade_ret,
                          row.name, c, pnl, open_p, last_price, "short")
            balance += pnl
            position = 0; last_signal = "hold"; c = 0

        # ── ENTRY ──
        if row.LONG and last_signal != "long":
            last_signal = "long"; last_price = open_p
            trade_starts.append(row.name); trade_sides.append("long")
            position = int(balance / open_p)
            balance -= position * open_p
            c = 0

        elif row.SHORT and last_signal != "short":
            last_signal = "short"; last_price = open_p
            trade_starts.append(row.name); trade_sides.append("short")
            position = int(balance / open_p) * -1
            c = 0

        # ── STOP LOSS ──
        if stop_loss_pct and last_signal == "long" and c > 0:
            ret = (row.Low / last_price - 1) * 100
            if ret <= stop_loss_pct:
                sl_price = last_price * (1 + stop_loss_pct / 100)
                pnl = (sl_price - last_price) * position
                _record_trade(trade_ends, trade_days, trade_pnl, trade_ret,
                              row.name, c + 1, pnl, sl_price, last_price, "long")
                balance += sl_price * position
                position = 0; last_signal = "hold"; c = 0

        elif stop_loss_pct and last_signal == "short" and c > 0:
            ret = (last_price / row.High - 1) * 100
            if ret <= stop_loss_pct:
                sl_price = last_price * (1 - stop_loss_pct / 100)
                pnl = (sl_price - last_price) * position
                _record_trade(trade_ends, trade_days, trade_pnl, trade_ret,
                              row.name, c + 1, pnl, sl_price, last_price, "short")
                balance += pnl
                position = 0; last_signal = "hold"; c = 0

        # ── MARKET VALUE ──
        if last_signal == "hold":
            mv = balance
        elif last_signal == "long":
            c += 1; mv = position * row.Close + balance
        else:
            c += 1; mv = (row.Close - last_price) * position + balance

        cum_value.append(mv)

    # Build trade dataframe
    size = min(len(trade_starts), len(trade_ends))
    if size == 0:
        return _empty_result(capital, cum_value)

    tdf = pd.DataFrame({
        "START": trade_starts[:size],
        "END":   trade_ends[:size],
        "SIDE":  trade_sides[:size],
        "DAYS":  trade_days[:size],
        "PNL":   trade_pnl[:size],
        "RET":   trade_ret[:size],
    })

    cum_series = pd.Series(cum_value, index=bt_df.index)
    total_ret = (cum_series.iloc[-1] / capital - 1) * 100
    drawdown = _max_drawdown(cum_series)

    wins = tdf[tdf.PNL > 0]
    losses = tdf[tdf.PNL < 0]

    return {
        "total_trades":  len(tdf),
        "win_rate":      round(len(wins) / len(tdf) * 100, 1),
        "avg_ret":       round(tdf.RET.mean(), 2),
        "avg_ret_win":   round(wins.RET.mean(), 2) if len(wins) else 0,
        "avg_ret_loss":  round(losses.RET.mean(), 2) if len(losses) else 0,
        "total_return":  round(total_ret, 2),
        "max_drawdown":  round(drawdown, 2),
        "final_balance": round(cum_series.iloc[-1], 2),
        "trade_df":      tdf,
        "cum_value":     cum_series,
        "latest_signal": _latest_signal(bt_df),
    }


def _record_trade(ends, days, pnl_list, ret_list, date, c, pnl, exit_p, entry_p, side):
    ends.append(date); days.append(c); pnl_list.append(round(pnl, 2))
    if side == "long":
        ret_list.append(round((exit_p / entry_p - 1) * 100, 2))
    else:
        ret_list.append(round((entry_p / exit_p - 1) * 100, 2))


def _max_drawdown(cum: pd.Series) -> float:
    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max * 100
    return round(dd.min(), 2)


def _empty_result(capital, cum_value):
    return {
        "total_trades": 0, "win_rate": 0, "avg_ret": 0,
        "avg_ret_win": 0, "avg_ret_loss": 0, "total_return": 0,
        "max_drawdown": 0, "final_balance": capital,
        "trade_df": pd.DataFrame(), "cum_value": pd.Series(cum_value),
        "latest_signal": "NONE",
    }


def _latest_signal(df):
    last_long  = df[df.LONG == True].index
    last_short = df[df.SHORT == True].index
    signals = []
    if len(last_long):  signals.append(("BUY",  last_long[-1]))
    if len(last_short): signals.append(("SELL", last_short[-1]))
    if not signals: return "NONE"
    sig = max(signals, key=lambda x: x[1])
    return f"{sig[0]} ({sig[1].strftime('%d-%b-%Y')})"


# ─────────────────────────────────────────────
#  CSV LOADER
# ─────────────────────────────────────────────

def load_csv(fpath: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(fpath, parse_dates=True)
        df.columns = [c.strip().title() for c in df.columns]

        for col in ["Date", "Timestamp", "Mtimestamp", "Time"]:
            if col in df.columns:
                df = df.rename(columns={col: "Date"})
                df["Date"] = pd.to_datetime(df["Date"])
                df = df.set_index("Date").sort_index()
                break

        rename_map = {}
        col_lower = {c.lower(): c for c in df.columns}
        for target, candidates in {
            "Open":   ["open", "ch_opening_price"],
            "High":   ["high", "ch_trade_high_price"],
            "Low":    ["low",  "ch_trade_low_price"],
            "Close":  ["close", "ch_closing_price", "last", "ltp"],
            "Volume": ["volume", "ch_tot_trd_qnty", "tottrdqty"],
        }.items():
            for cand in candidates:
                if cand in col_lower:
                    rename_map[col_lower[cand]] = target
                    break

        df = df.rename(columns=rename_map)
        required = ["High", "Low", "Close"]
        if not all(c in df.columns for c in required):
            return None
        if "Open" not in df.columns:
            df["Open"] = df["Close"].shift(1).fillna(df["Close"])

        df[["Open","High","Low","Close"]] = df[["Open","High","Low","Close"]].apply(
            pd.to_numeric, errors="coerce"
        )
        df = df[df["Close"].notna()]
        return df if len(df) >= 60 else None
    except Exception:
        return None


# ─────────────────────────────────────────────
#  OPTIMIZER
# ─────────────────────────────────────────────

def optimize(df: pd.DataFrame, capital: float, sl: float | None) -> dict | None:
    best = None
    for strat_name, param_space in OPTIMIZE_PARAMS.items():
        func = STRATEGIES[strat_name]
        keys = list(param_space.keys())
        combos = [dict(zip(keys, vals)) for vals in product(*param_space.values())]
        for params in combos:
            try:
                bt_df = func(df, **params)
                result = run_backtest(bt_df, capital, sl)
                score = result["total_return"] - abs(result["max_drawdown"])
                if result["total_trades"] >= 3 and (best is None or score > best["score"]):
                    best = {
                        "strategy": strat_name,
                        "params":   params,
                        "score":    round(score, 2),
                        **{k: result[k] for k in
                           ["total_trades","win_rate","avg_ret","total_return","max_drawdown","latest_signal"]}
                    }
            except Exception:
                continue
    return best


# ─────────────────────────────────────────────
#  COLORS
# ─────────────────────────────────────────────

class c:
    R = "\033[0m"; B = "\033[1m"
    G = "\033[1;92m"; RED = "\033[1;91m"
    Y = "\033[1;93m"; CY = "\033[0;96m"
    W = "\033[1;37m"; DIM = "\033[2m"

    @staticmethod
    def pnl(v):
        s = f"+{v}%" if v > 0 else f"{v}%"
        return f"{c.G if v > 0 else (c.RED if v < 0 else c.DIM)}{s}{c.R}"

    @staticmethod
    def sig(s):
        if "BUY" in s:  return f"{c.G}{s}{c.R}"
        if "SELL" in s: return f"{c.RED}{s}{c.R}"
        return f"{c.DIM}{s}{c.R}"


# ─────────────────────────────────────────────
#  MAIN RUNNER
# ─────────────────────────────────────────────

def run(folder: str, strategy_name: str = "all",
        capital: float = 100000, sl: float | None = None,
        export: str | None = None, optimize_mode: bool = False):

    folder_path = Path(folder)
    csv_files = sorted(folder_path.glob("*.csv"))

    if not csv_files:
        print(f"No CSV files found in: {folder_path}"); return

    strategies_to_run = STRATEGIES if strategy_name == "all" else {
        strategy_name: STRATEGIES[strategy_name]
    }

    SEP = "─" * 130
    print(f"\n{c.B}{c.W}{SEP}{c.R}")
    print(f"{c.B}{c.W}"
          f"{'SYMBOL':<15}{'STRATEGY':<20}{'TRADES':>7}{'WIN%':>7}"
          f"{'AVG RET':>9}{'TOTAL RET':>11}{'MAX DD':>9}{'FINAL BAL':>14}  {'SIGNAL'}"
          f"{c.R}")
    print(f"{c.B}{c.W}{SEP}{c.R}")

    all_results = []
    skipped = []

    for fpath in csv_files:
        symbol = fpath.stem.upper()
        df = load_csv(fpath)

        if df is None:
            skipped.append(symbol); continue

        if optimize_mode:
            print(f"{c.DIM}Optimizing {symbol}...{c.R}", end="\r")
            best = optimize(df, capital, sl)
            if best:
                print(
                    f"{c.CY}{symbol[:14].upper():<15}{c.R}"
                    f"{c.Y}{best['strategy']:<20}{c.R}"
                    f"{str(best['total_trades']):>7}"
                    f"{(c.G if best['win_rate']>=50 else c.RED)+str(best['win_rate'])+'%'+c.R:>14}"
                    f"{c.pnl(best['avg_ret']):>16}"
                    f"{c.pnl(best['total_return']):>18}"
                    f"{c.RED+str(best['max_drawdown'])+'%'+c.R:>16}"
                    f"  {c.sig(best['latest_signal'])}"
                    f"  params={best['params']}"
                )
                all_results.append({"symbol": symbol, **best})
            continue

        for strat_name, strat_fn in strategies_to_run.items():
            try:
                bt_df = strat_fn(df)
                result = run_backtest(bt_df, capital=capital, stop_loss_pct=sl)

                wr_str = f"{result['win_rate']}%"
                wr_col = c.G if result["win_rate"] >= 50 else c.RED

                print(
                    f"{c.CY}{symbol[:14].upper():<15}{c.R}"
                    f"{c.Y}{strat_name:<20}{c.R}"
                    f"{str(result['total_trades']):>7}"
                    f"{wr_col+wr_str+c.R:>14}"
                    f"{c.pnl(result['avg_ret']):>16}"
                    f"{c.pnl(result['total_return']):>18}"
                    f"{c.RED+str(result['max_drawdown'])+'%'+c.R:>16}"
                    f"{c.W+str(result['final_balance'])+c.R:>18}"
                    f"  {c.sig(result['latest_signal'])}"
                )

                all_results.append({
                    "symbol":         symbol,
                    "strategy":       strat_name,
                    "total_trades":   result["total_trades"],
                    "win_rate":       result["win_rate"],
                    "avg_ret":        result["avg_ret"],
                    "avg_ret_win":    result["avg_ret_win"],
                    "avg_ret_loss":   result["avg_ret_loss"],
                    "total_return":   result["total_return"],
                    "max_drawdown":   result["max_drawdown"],
                    "final_balance":  result["final_balance"],
                    "latest_signal":  result["latest_signal"],
                })
            except Exception as e:
                print(f"{c.RED}ERROR{c.R} {symbol}/{strat_name}: {e}")

    print(f"{c.B}{c.W}{SEP}{c.R}")

    # ── SUMMARY ──
    if all_results and not optimize_mode:
        rdf = pd.DataFrame(all_results)
        print(f"\n{c.B}{c.W}── STRATEGY SUMMARY ──{c.R}")
        for strat in rdf["strategy"].unique():
            sdf = rdf[rdf["strategy"] == strat]
            buys  = sdf["latest_signal"].str.contains("BUY").sum()
            sells = sdf["latest_signal"].str.contains("SELL").sum()
            print(
                f"  {c.Y}{strat:<22}{c.R}"
                f"Avg WinRate: {c.G if sdf['win_rate'].mean()>=50 else c.RED}"
                f"{sdf['win_rate'].mean():.1f}%{c.R}  "
                f"Avg TotalRet: {c.pnl(round(sdf['total_return'].mean(),2))}  "
                f"Active BUYs: {c.G}{buys}{c.R}  "
                f"Active SELLs: {c.RED}{sells}{c.R}"
            )

    if skipped:
        print(f"\n{c.DIM}Skipped: {', '.join(skipped)}{c.R}")

    if export and all_results:
        out = Path(export)
        pd.DataFrame(all_results).to_csv(out, index=False)
        print(f"\n{c.G}Exported to: {out.resolve()}{c.R}")

    print()


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NSE CSV multi-strategy backtester")
    parser.add_argument("--folder",   required=True,  help="Folder with stock CSV files")
    parser.add_argument("--strategy", default="all",
                        choices=list(STRATEGIES.keys()) + ["all"],
                        help="Strategy to run (default: all)")
    parser.add_argument("--sl",       type=float, default=None,
                        help="Stop loss %% as negative decimal e.g. -3 for 3%% SL")
    parser.add_argument("--capital",  type=float, default=100000,
                        help="Starting capital (default: 100000)")
    parser.add_argument("--export",   default=None,
                        help="Export results to this CSV file")
    parser.add_argument("--optimize", action="store_true",
                        help="Find best strategy+params per stock (slow)")

    args = parser.parse_args()

    run(
        folder=args.folder,
        strategy_name=args.strategy,
        capital=args.capital,
        sl=args.sl,
        export=args.export,
        optimize_mode=args.optimize,
    )