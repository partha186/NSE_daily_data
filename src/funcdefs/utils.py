import json
import random
import string
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple

import pandas as pd

from funcdefs.csv_read_load.csv_loader import csv_loader


class Color:
    """ANSI color codes for terminal output formatting.

    Provides color constants and a static method to apply color coding to
    numeric values based on configurable thresholds.  Used throughout the
    project to create visual emphasis on important metrics.

    Usage::

        from funcdefs.utils import Color
        print(Color.GREEN + "OK" + Color.ENDC)
        print(Color.num(2.5, config))   # threshold-aware coloring
    """

    HEADER = "\033[95m"
    WHITE = "\033[1;37m"
    YELLOW = "\033[1;32m"
    PURPLE = "\033[1;35m"
    BLUE = "\033[94m"
    CYAN = "\033[0;96m"
    GREEN = "\033[1;92m"
    ORANGE = "\033[1;93m"
    RED = "\033[1;91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[1;4m"

    @staticmethod
    def num(nu: float, config) -> str:
        """Apply threshold-based color to a numeric value.

        Tier mapping (uses config thresholds):
            WHITE  : nu >= DLV_L3  (very above average)
            ORANGE : nu >= DLV_L2  (above average)
            RED    : nu >  DLV_L1  (moderately above average)
            CYAN   : nu <= DLV_L1  (below / at average)
        """
        if nu >= config.DLV_L3:
            return f"{Color.WHITE}{nu}{Color.ENDC}"
        if nu >= config.DLV_L2:
            return f"{Color.ORANGE}{nu}{Color.ENDC}"
        if nu > config.DLV_L1:
            return f"{Color.RED}{nu}{Color.ENDC}"
        return f"{Color.CYAN}{nu}{Color.ENDC}"

    @staticmethod
    def enable_windows() -> None:
        """Enable ANSI color codes on Windows (no-op on other platforms)."""
        import platform
        if platform.system() == "Windows":
            import os
            os.system("color")


class DateEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


def loadJson(fPath: Path):
    return json.loads(fPath.read_bytes())


def writeJson(fPath: Path, data):
    fPath.write_text(json.dumps(data, indent=3, cls=DateEncoder))


def randomChar(length):
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))


def getDataFrame(
    fpath: Path,
    tf: str,
    period: int,
    column: Optional[str] = None,
    toDate: Optional[datetime] = None,
) -> Any:
    candle_count = period * 5 if tf == "weekly" else period

    df = csv_loader(fpath, candle_count, end_date=toDate)

    dct: dict = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }

    if tf == "weekly":
        if column:
            return (
                df[column]
                .resample("W", label="left")
                .apply(dct[column])[-period:]
            )

        return df.resample("W", label="left").apply(dct)[-period:]

    return df[-period:] if column is None else df[column][-period:]


def arg_parse_dict(dct: dict) -> list:
    """
    Convert a dictionary of arguments and values into a list of command-line
    arguments.

    Parameters:
    - dct (dict): Dictionary containing argument names and values.

    Returns:
    - list: List of command-line style arguments.

    Example:
    ```python
    args = {'input_file': 'data.txt', 'output_dir': '/output', 'verbose': True}
    command_line_args = arg_parse_dict(args)
    ```
    """

    result = []

    for arg, val in dct.items():
        if val is False or val is None:
            continue

        arg = arg.replace("_", "-")

        result.append(f"--{arg}")

        if val is not True:
            if isinstance(val, list):
                result.extend(map(str, val))
            else:
                result.append(str(val))

    return result


def getDeliveryLevels(df, config):
    # Average of traded volume
    avgTrdQty = df["QTY_PER_TRADE"].rolling(config.DLV_AVG_LEN).mean().round(2)

    # Average of delivery
    avgDlvQty = df["DLV_QTY"].rolling(config.DLV_AVG_LEN).mean().round(2)

    # above average delivery days
    df["DQ"] = df["DLV_QTY"] / avgDlvQty

    # above average Traded volume days
    df["TQ"] = df["QTY_PER_TRADE"] / avgTrdQty

    # get combination of above average traded volume and delivery days
    df["IM_F"] = (df["TQ"] > 1.2) & (df["DQ"] > 1.2)

    # see https://github.com/matplotlib/mplfinance/blob/master/examples/marketcolor_overrides.ipynb
    df["MCOverrides"] = None
    df["IM"] = float("nan")

    for idx in df.index:
        dq, im = df.loc[idx, ["DQ", "IM_F"]]

        if im:
            df.loc[idx, "IM"] = df.loc[idx, "Low"] * 0.99

        if dq >= config.DLV_L3:
            df.loc[idx, "MCOverrides"] = config.PLOT_DLV_L1_COLOR
        elif dq >= config.DLV_L2:
            df.loc[idx, "MCOverrides"] = config.PLOT_DLV_L2_COLOR
        elif dq > config.DLV_L1:
            df.loc[idx, "MCOverrides"] = config.PLOT_DLV_L3_COLOR
        else:
            df.loc[idx, "MCOverrides"] = config.PLOT_DLV_DEFAULT_COLOR


def isFarFromLevel(
    level: float,
    levels: List[Tuple[pd.DatetimeIndex, float]],
    mean_candle_size: float,
) -> bool:
    """Returns true if difference between the level and any of the price levels
    is greater than the mean_candle_size."""
    # Detection of price support and resistance levels in Python -Gianluca Malato
    # source: https://towardsdatascience.com/detection-of-price-support-and-resistance-levels-in-python-baedc44c34c9
    return sum([abs(level - x[1]) < mean_candle_size for x in levels]) == 0


def getLevels(
    df: pd.DataFrame, mean_candle_size: float
) -> List[
    Tuple[Tuple[pd.DatetimeIndex, float], Tuple[pd.DatetimeIndex, float]]
]:
    """
    Identify potential support and resistance levels in a DataFrame.

    Parameters:
    - df (pd.DataFrame): DataFrame containing at least 'High' and 'Low' columns.
    - mean_candle_size (float): The mean size of a candle, used as a threshold for level clustering.

    Returns:
    - list of tuples: Each tuple represents a horizontal line segment, defined by two points.
      Each point is a tuple containing date and price.
      The list represents identified support and resistance levels.

    Algorithm:
    - The function uses local maxima and minima in the 'High' and 'Low' prices to identify potential reversal points.
    - It filters for rejection from the top (local maxima) and from the bottom (local minima).
    - To avoid clustering of support and resistance lines, it utilizes the isFarFromLevel function.
    - Identified levels are returned as horizontal line segments for visualization.

    Example Usage:
    ```python
    # Example DataFrame df with 'High' and 'Low' columns
    levels = getLevels(df, mean_candle_size=2.0)
    ```

    Note:
    - It is recommended to provide a DataFrame with sufficient historical price data for accurate level identification.
    - The function is designed for use in financial technical analysis.
    """

    levels = []

    # filter for rejection from top
    # 2 succesive highs followed by 2 succesive lower highs
    local_max = df["High"][
        (df["High"].shift(1) < df["High"])
        & (df["High"].shift(2) < df["High"].shift(1))
        & (df["High"].shift(-1) < df["High"])
        & (df["High"].shift(-2) < df["High"].shift(-1))
    ].dropna()

    # filter for rejection from bottom
    # 2 succesive highs followed by 2 succesive lower highs
    local_min = df["Low"][
        (df["Low"].shift(1) > df["Low"])
        & (df["Low"].shift(2) > df["Low"].shift(1))
        & (df["Low"].shift(-1) > df["Low"])
        & (df["Low"].shift(-2) > df["Low"].shift(-1))
    ].dropna()

    for idx in local_max.index:
        level = local_max[idx]

        # Prevent clustering of support and resistance lines
        # Only add a level if it at a distance from any other price lines
        if isFarFromLevel(level, levels, mean_candle_size):
            levels.append((idx, level))

    for idx in local_min.index:
        level = local_min[idx]

        if isFarFromLevel(level, levels, mean_candle_size):
            levels.append((idx, level))

    alines = []
    lastDt = df.index[-1]

    for dt, price in levels:
        # a tuple containing start and end point coordinates for a horizontal line
        # Each tuple is composed of date and price.
        seq = ((dt, price), (lastDt, price))
        alines.append(seq)

    return alines


def isFarFromLevel_v2(
    level: float,
    levels: List[Tuple[pd.Timestamp, float]],
    mean_candle_size: float,
):
    """Returns true if difference between the level and any of the price levels
    is greater than the mean_candle_size."""
    # Detection of price support and resistance levels in Python -Gianluca Malato
    # source: https://towardsdatascience.com/detection-of-price-support-and-resistance-levels-in-python-baedc44c34c9
    return sum([abs(level - x[1]) < mean_candle_size for x in levels]) == 0


def getLevels_v2(df: pd.DataFrame, mean_candle_size: float):

    levels = []

    highs_mask = (
        (df.High.shift(1) < df.High)
        & (df.High.shift(2) < df.High)
        & (df.High.shift(3) < df.High)
        & (df.High.shift(-1) < df.High)
        & (df.High.shift(-2) < df.High)
        & (df.High.shift(-3) < df.High)
    )

    lows_mask = (
        (df.Low.shift(1) > df.Low)
        & (df.Low.shift(2) > df.Low)
        & (df.Low.shift(3) > df.Low)
        & (df.Low.shift(-1) > df.Low)
        & (df.Low.shift(-2) > df.Low)
        & (df.Low.shift(-3) > df.Low)
    )

    # filter for rejection from top
    # 2 succesive highs followed by 2 succesive lower highs
    max = df["High"].loc[highs_mask].dropna()
    min = df["Low"].loc[lows_mask].dropna()

    max_min = pd.concat([max, min], axis=0)

    max_min = max_min.loc[~max_min.index.duplicated()]

    for i, lv in max_min.items():

        touch_count = max_min.loc[
            (max_min - lv).abs() < mean_candle_size
        ].count()

        if touch_count > 1 and isFarFromLevel_v2(lv, levels, mean_candle_size):
            levels.append((i, lv))

    return [((i, lv), (df.index[-1], lv)) for i, lv in levels]


# def getScreenSize():
#     root = Tk()
#     root.withdraw()
#     mm = 25.4
#
#     width, height = root.winfo_screenmmwidth(), root.winfo_screenmmheight()
#
#     return (round(width / mm), round(height / mm))


def relativeStrength(close: pd.Series, index_close: pd.Series) -> pd.Series:
    return (close / index_close * 100).round(2)


def mansfieldRelativeStrength(
    close: pd.Series, index_close: pd.Series, period: int
) -> pd.Series:
    """Mansfield Relative Strength: stock performance vs index, normalised to SMA.

    Returns ((RS / SMA(RS, period)) - 1) * 100.
    Positive values indicate outperformance vs the index.
    """
    rs = relativeStrength(close, index_close)
    sma_rs = rs.rolling(period).mean()
    return ((rs / sma_rs - 1) * 100).round(2)


# Backwards-compatible alias (corrected from typo)
manfieldRelativeStrength = mansfieldRelativeStrength
