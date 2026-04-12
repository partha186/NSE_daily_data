"""NSE End-of-Day Stock Data Analysis Tool.

This module provides command-line tools to analyze NSE (National Stock Exchange)
end-of-day stock data, calculate trading metrics, and identify institutional trading
activity patterns. It supports both individual stock lookup with historical trends
and watchlist-based monitoring of multiple stocks.

Main Features:
    - Detailed stock analysis with rolling averages and ratio metrics
    - Watchlist management (add, remove, list)
    - Institutional money detection (IM) based on volume and delivery patterns
    - Color-coded terminal output for visual analysis

Usage:
    python data_get.py --sym SYMBOL [SYMBOL ...]
    python data_get.py --lookup SYMBOL
    python data_get.py --watch WATCHLIST_NAME
    python data_get.py --watch-add NAME FILENAME
    python data_get.py --watch-rm NAME
    python data_get.py --ls
"""

import sys
from argparse import ArgumentParser
from funcdefs.Config import Config
from funcdefs.utils import writeJson, loadJson, Color
from pathlib import Path
from pandas import read_csv


# Alias for brevity throughout this module
c = Color


def lookup(sym):
    """Perform detailed analysis of a single stock symbol with historical trends.
    
    Loads CSV data for a symbol, calculates rolling averages over a specified period,
    computes ratio metrics (DQ, TQ, VOL), detects institutional money patterns, and
    displays color-coded results for the last N trading days.
    
    The analysis includes:
        - Rolling averages: Average trade qty, delivery qty, volume
        - Ratio metrics: Current value / average (e.g., 2.5 = 2.5x average)
        - Institutional Money (IM): True when both DQ and TQ exceed their averages
        - Color coding: WHITE (high) > ORANGE (medium) > RED (moderate) > CYAN (low)
    
    Args:
        sym (str): Stock symbol (e.g., 'RELIANCE', 'TCS')
        
    Raises:
        SystemExit: If data file not found for the symbol
    """
    # Construct file path to daily CSV data
    fpath = DIR / "NSE_eod_data" / "daily" / f"{sym}.csv"
    print(f"Analyzing {sym.upper()}...\n")
    

    # Validate symbol name (alphanumeric + hyphen only, max 20 chars)
    sym = sym.strip().upper()
    if not sym or not all(ch.isalnum() or ch == "-" for ch in sym):
        print(f"Error: Invalid symbol name '{sym}'.")
        return

    # Fail-fast: Exit if symbol data file doesn't exist
    if not fpath.exists():
        sys.exit(f"Error: No data file found for symbol '{sym}'. "
                 "Check that the symbol is listed on NSE and data has been synced.")

    # Load CSV file with Date as index and automatic date parsing
    df = read_csv(fpath, index_col="Date", parse_dates=True)

    # Calculate N-day rolling averages (baseline for comparison)
    # These allow us to identify above/below average activity
    df["AVG_TRD_QTY"] = (
        df["QTY_PER_TRADE"].rolling(config.DGET_AVG_DAYS).mean().round(2)
    )

    df["AVG_DLV_QTY"] = (
        df["DLV_QTY"].rolling(config.DGET_AVG_DAYS).mean().round(2)
    )

    df["AVG_VOL"] = df["Volume"].rolling(config.DGET_AVG_DAYS).mean().round(2)

    # Calculate ratio metrics: current value / average value
    # Values > 1.0 = above average, < 1.0 = below average
    # Example: DQ = 2.5 means delivery qty is 2.5x the average
    df["DQ"] = (df["DLV_QTY"] / df["AVG_DLV_QTY"]).round(2)
    df["TQ"] = (df["QTY_PER_TRADE"] / df["AVG_TRD_QTY"]).round(2)
    df["VOL"] = (df["Volume"] / df["AVG_VOL"]).round(2)

    # Institutional Money (IM) detection: True only when BOTH DQ and TQ exceed
    # DLV_L1 threshold (consistent with snapshot mode — both use config.DLV_L1)
    im_threshold = config.DLV_L1
    df["IM"] = True
    df["IM"] = df["IM"].where(
        (df["DQ"] > im_threshold)   # Delivery qty above threshold
        & (df["TQ"] > im_threshold),  # Trade qty above threshold
        "",  # Empty string if condition not met
    )

    # Apply color formatting to all metric columns
    df["DQ"] = df["DQ"].apply(lambda v: c.num(v, config))
    df["TQ"] = df["TQ"].apply(lambda v: c.num(v, config))
    # IM column: Orange $$ if institutional signal detected, dash otherwise
    df["IM"] = df["IM"].apply(lambda v: f'{c.ORANGE}{"$$" if v else "-"}{c.ENDC}')
    df["VOL"] = df["VOL"].apply(lambda v: c.num(v, config))

    # Keep only the last N days and select display columns in order
    df = df[-config.DGET_DAYS:][["DQ", "TQ", "IM", "VOL"]]

    print(
        f"{c.WHITE}Units = average multiples (1x 2x …). "
        f"<1: below avg. DQ: Delivery qty  TQ: Qty/trade  "
        f"IM: Institutional Money (DQ & TQ > {im_threshold}x avg){c.ENDC}\n"
    )
    print(f'{c.WHITE}DATE{" " * 10}DQ{" " * 5}TQ{" " * 5}VOL{" " * 4}IM{c.ENDC}')
    # Display results in reverse chronological order (most recent first)
    for Index, DQ, TQ, IM, VOL in df[::-1].itertuples():
        print(
            f'{c.CYAN}{Index.strftime("%d %b %Y").ljust(13)}{c.ENDC}',
            DQ.ljust(17),
            TQ.ljust(17),
            VOL.ljust(17),
            IM,
        )


# Command-line argument parser
parser = ArgumentParser(prog="data_get.py")

# Mutually exclusive group: only one operation can be specified at a time
group = parser.add_mutually_exclusive_group(required=True)

group.add_argument(
    "--sym",
    nargs="+",
    metavar="SYM",
    help="Space separated list of stock symbols",
)

group.add_argument(
    "--watch", metavar="NAME", help="load a watchlist file by NAME."
)

group.add_argument(
    "--watch-add",
    nargs=2,
    metavar=("NAME", "FILENAME"),
    help="Add a watchlist by NAME and FILENAME",
)

group.add_argument(
    "--watch-rm", metavar="NAME", help="Remove a watchlist by NAME"
)

group.add_argument(
    "--ls", action="store_true", help="List available watchlists."
)

group.add_argument("-l", "--lookup", metavar="SYM", help="Symbol to lookup")

# Parse command-line arguments
args = parser.parse_args()

# Load configuration with thresholds and parameters
config = Config()

# Set up file paths
DIR = Path(__file__).parent
configPath = DIR / "funcdefs" / "user.json"  # User watchlist configuration
DAILY = DIR / "NSE_eod_data" / "daily"          # Directory containing daily CSV files

# Enable ANSI color support on Windows systems
Color.enable_windows()

# Handle --watch-add: Create or update a watchlist
if args.watch_add:
    name, fName = args.watch_add

    # Load existing config or start fresh
    data = loadJson(configPath) if configPath.is_file() else {}

    # Ensure WATCH key exists
    if "WATCH" not in data:
        data["WATCH"] = {}

    # Add watchlist entry (uppercase name for case-insensitive matching)
    data["WATCH"][name.upper()] = fName
    writeJson(configPath, data)
    print(f"Added watchlist '{name}' with value '{fName}'")
    sys.exit(0)

# Handle --watch-rm: Remove a watchlist
if args.watch_rm:
    # Validate watchlist exists
    if args.watch_rm.upper() not in getattr(config, "WATCH"):
        sys.exit(f"Error: No watchlist named: '{args.watch_rm}'")

    if not configPath.is_file():
        sys.exit("Error: No config file found.")

    # Load, modify, and save config
    data = loadJson(configPath)

    del data["WATCH"][args.watch_rm.upper()]
    writeJson(configPath, data)
    print(f"Watchlist '{args.watch_rm}' removed.")
    sys.exit(0)

# Handle --ls: List all available watchlists
if args.ls:
    if not len(config.WATCH):
        print("No watchlists configured.")
        sys.exit(0)

    # Convert to lowercase for display
    lst = [i.lower() for i in config.WATCH.keys()]
    print(f'Watchlists: {",".join(lst)}')
    sys.exit(0)

# Determine symbol list: from watchlist file or command-line arguments
if args.watch:
    # Validate watchlist exists
    if args.watch.upper() not in config.WATCH:
        sys.exit(f"Error: No watchlist named '{args.watch}'")

    # Load symbols from watchlist file
    file = DIR / "data" / config.WATCH[args.watch.upper()]

    if not file.is_file():
        sys.exit(f"Error: File not found {file}")

    # Parse symbols from file (one per line)
    symList = file.read_text().strip("\n").split("\n")
else:
    # Use symbols provided via command-line
    symList = args.sym


# Route to appropriate analysis mode
if args.lookup:
    # Single symbol detailed lookup with rolling averages and history
    lookup(args.lookup)
else:
    # Watchlist snapshot mode: latest metrics for multiple symbols
    watch_name = args.watch.upper() if args.watch else "DEFAULT"

    # Build color legend showing threshold boundaries
    heading = f"{c.WHITE}>= {config.DLV_L3}{c.ENDC}  {c.ORANGE}>= {config.DLV_L2}{c.ENDC}  {c.RED}>= {config.DLV_L1}{c.ENDC}\n\n"

    heading += f"{c.WHITE}{watch_name}{c.ENDC}\n"

    # Heading text
    heading += (
        f'{c.WHITE}SCRIP{" " * 8}DQ{" " * 9}TQ{" " * 9}VOL{" " * 5}IM{c.ENDC}\n'
    )

    # Build output table with metrics for each symbol
    txt = ""

    for sym in symList:
        # Construct file path for symbol
        fpath = DAILY / f"{sym.lower()}.csv"

        # Skip symbols with missing data files
        if not fpath.exists():
            print(f"Error: File not found: {fpath.name}")
            continue

        # Load last N days of data (e.g., 30 days for averaging)
        df = read_csv(fpath, index_col="Date", parse_dates=True)[
            -config.DLV_AVG_LEN :
        ]

        # Skip if no delivery data available
        if df["DLV_QTY"].dropna().empty:
            print(f"No delivery data: {sym.upper()}")
            continue

        try:
            # Calculate simple average over the period
            # (Different from rolling average used in lookup() function)
            avgQty, avgDlvQty, avgVol = (
                df[["QTY_PER_TRADE", "DLV_QTY", "Volume"]]
                .mean(numeric_only=True)
                .round(2)
            )
        except ValueError:
            # New stocks may not have enough historical data
            continue

        # Extract most recent values for the symbol
        tradeQty, dlvQty, volume = df.loc[
            df.index[-1], ["QTY_PER_TRADE", "DLV_QTY", "Volume"]
        ]

        # Calculate ratio metrics: current / average
        tq = round(tradeQty / avgQty, 2)
        dq = round(dlvQty / avgDlvQty, 2)
        vol = round(volume / avgVol, 2)
        # Institutional Money: consistent threshold (config.DLV_L1) across both modes
        im_threshold = config.DLV_L1
        im = f'{c.ORANGE}{"$$" if dq > im_threshold and tq > im_threshold else "-"}{c.ENDC}'

        # Format row with symbol and metrics, applying color codes
        txt += "{} {} {} {} {}\n".format(
            c.CYAN + sym[:15].upper().ljust(12),
            c.num(dq, config).ljust(21),
            c.num(tq, config).ljust(21),
            c.num(vol, config).ljust(18),
            im,
        )

    # Display complete table with header and all symbol rows
    if txt:
        print(heading + txt)
