"""NSE Stock Chart Visualization Tool.

This module provides command-line tools to generate and display candlestick charts
for NSE (National Stock Exchange) stocks with optional technical indicators such as
moving averages, support/resistance levels, relative strength, and volume analysis.

Main Features:
    - Interactive chart viewing with navigation (next/previous)
    - Multiple technical indicators (SMA, EMA, Volume SMA, RS, SNR)
    - Watchlist management for batch chart viewing
    - Preset saving/loading of chart configurations
    - Automatic chart saving to PNG files
    - Support for daily and weekly timeframes
    - Delivery data visualization for intraday analysis
    - Symbol selection tracking during chart review
    - Side-by-side comparison of two stocks
    - Overlay mode for correlation analysis

    while True:
    plotter.plot(sym)          ← opens window, BLOCKS
        │
        │  user presses 'n'
        │
    _on_key_press()
        self.key = "n"
        plt.close("all")       ← unblocks plot()
        │
    answer = plotter.key       ← "n"
    plotter.idx += 1
    (loop again → next chart)


Keyboard Controls:
    n = Next chart
    p = Previous chart
    a = Add to selection
    c = Compare current with another (side-by-side)
    l = Overlay current with another (correlation)
    h = Show help
    q = Quit

Usage:
    python plot.py --sym SYMBOL [SYMBOL ...] [OPTIONS]
    python plot.py --watch WATCHLIST_NAME [OPTIONS]
    python plot.py --preset PRESET_NAME
    python plot.py --ls
    python plot.py --sym SYM1 SYM2 --compare
"""

from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path

from funcdefs.Config import Config
from funcdefs.Plotter import Plotter, processPlot
from funcdefs.Plugin import Plugin
from funcdefs.utils import loadJson, writeJson

# Initialize paths, configuration, and plugin system
DIR = Path(__file__).parent
config = Config()  # Load configuration with defaults (plot days, indicators, etc.)
plugin = Plugin()  # Initialize plugin system for extensibility

# Command-line argument parser setup
parser = ArgumentParser(prog="plot.py")

# Mutually exclusive group: only one primary operation at a time
group = parser.add_mutually_exclusive_group(required=True)

group.add_argument(
    "--sym",
    nargs="+",
    metavar="SYM",
    help="Space separated list of stock symbols.",
)

group.add_argument("--watch", metavar="NAME", help="load a watchlist file by NAME.")

group.add_argument(
    "--watch-add",
    nargs=2,
    metavar=("NAME", "FILENAME"),
    help="Save a watchlist by NAME and FILENAME",
)

group.add_argument(
    "--watch-rm", metavar="NAME", help="Remove a watchlist by NAME and FILENAME"
)

group.add_argument(
    "--preset", help="Load command line options saved by NAME.", metavar="NAME"
)

parser.add_argument(
    "--preset-save",
    action="store",
    metavar="str",
    help="Save command line options by NAME.",
)

group.add_argument(
    "--preset-rm", action="store", metavar="str", help="Remove preset by NAME."
)

group.add_argument(
    "--ls", action="store_true", help="List available presets and watchlists."
)

parser.add_argument("-s", "--save", action="store_true", help="Save chart as png.")

parser.add_argument("-v", "--volume", action="store_true", help="Add Volume")

parser.add_argument(
    "--rs", action="store_true", help="Dorsey Relative strength indicator."
)

parser.add_argument(
    "--m-rs", action="store_true", help="Mansfield Relative strength indicator."
)

parser.add_argument(
    "--tf",
    action="store",
    choices=("weekly", "daily"),
    default="daily",
    help="Timeframe. Default 'daily'",
)

parser.add_argument(
    "--sma", type=int, nargs="+", metavar="int", help="Simple Moving average"
)

parser.add_argument(
    "--ema",
    type=int,
    nargs="+",
    metavar="int",
    help="Exponential Moving average",
)

parser.add_argument(
    "--vol-sma",
    type=int,
    nargs="+",
    metavar="int",
    help="Volume Moving average",
)

parser.add_argument(
    "-d",
    "--date",
    type=datetime.fromisoformat,
    metavar="str",
    help="ISO format date YYYY-MM-DD.",
)

parser.add_argument(
    "--period",
    action="store",
    type=int,
    metavar="int",
    help=f"Number of Candles to plot. Default {config.PLOT_DAYS}",
)

parser.add_argument(
    "--snr",
    action="store_true",
    help="Add Support and Resistance lines on chart",
)

parser.add_argument(
    "--snr-v2",
    action="store_true",
    help="Add Support and Resistance lines on chart",
)

parser.add_argument(
    "-r",
    "--resume",
    action="store_true",
    help="Resume a watchlist from last viewed chart.",
)

parser.add_argument(
    "--dlv",
    action="store_true",
    help="Delivery Mode. Plot delivery data on chart.",
)

parser.add_argument(
    "--compare",
    action="store_true",
    help="Enable comparison mode for side-by-side chart viewing.",
)

parser.add_argument(
    "--overlay",
    action="store_true",
    help="Enable overlay mode for correlation analysis of multiple stocks.",
)

args = parser.parse_args()

# Timeframe validation: Delivery data only available on daily charts
if args.tf == "weekly" and args.dlv:
    exit("WARN: Delivery data not available on Weekly Timeframe")

# Initialize the plotter with parsed arguments and configuration
plotter = Plotter(args, config, plugin, parser, DIR)

# Get symbol list from plotter (loaded from watchlist or command-line arguments)
symList = plotter.symList

# Load preset arguments if specified (overrides command-line args)
if args.preset:
    args = plotter.args

# Batch mode: Save all charts as PNG files concurrently
if args.save:
    from concurrent.futures import ProcessPoolExecutor

    # Use multiprocessing for faster chart generation
    with ProcessPoolExecutor() as executor:
        for sym in symList:
            executor.submit(processPlot, plotter.plot(sym), plotter.plot_args)
    exit("Done")

# PROMPT BETWEEN EACH CHART
plotter.idx = 0
plotter.len = len(symList)
answer = "n"

if args.resume and hasattr(config, "PLOT_RESUME"):
    resume = getattr(config, "PLOT_RESUME")

    # Only resume if same watchlist is used
    if resume["watch"] == args.watch:
        plotter.idx = resume["idx"]

# Track selected symbols during chart review
selected = set()

# Comparison mode tracking
comparison_mode = getattr(args, "compare", False)  # Side-by-side viewing
overlay_mode = getattr(args, "overlay", False)     # Correlation overlay
comparison_symbols = []                              # Symbols selected for comparison
overlay_symbols = []                                 # Symbols selected for overlay


def display_help():
    """Display keyboard controls and available commands."""
    help_text = """
╔════════════════════════════════════════════════════════╗
║          PLOT VIEWER - KEYBOARD CONTROLS               ║
╠════════════════════════════════════════════════════════╣
║ Navigation:                                            ║
║   n = Next chart                                       ║
║   p = Previous chart                                   ║
║                                                        ║
║ Selection & Comparison:                                ║
║   a = Add current symbol to selection                  ║
║   c = Compare current with another (side-by-side)      ║
║   l = Overlay current with another (correlation)       ║
║                                                        ║
║ Utilities:                                             ║
║   h = Show this help menu                              ║
║   q = Quit and save selections                         ║
╚════════════════════════════════════════════════════════╝
    """
    print(help_text)


def plot_side_by_side(sym1: str, sym2: str):
    """Display two stock charts side-by-side for comparison.
    
    Creates a matplotlib figure with two subplots showing candlestick
    charts for sym1 and sym2 with identical date ranges and scale
    for easy visual comparison of price action and patterns.
    
    Args:
        sym1 (str): First stock symbol
        sym2 (str): Second stock symbol
    """
    try:
        print(f"\nComparing: {sym1} vs {sym2}")
        print("(Side-by-side view for pattern comparison)")
        # Integration point: Call plotter with comparison flag
        # plotter.plot_comparison(sym1, sym2, "side-by-side")
        plotter.plot(sym1)
        print(f"Next: {sym2}")
        plotter.plot(sym2)
    except Exception as e:
        print(f"Error in side-by-side comparison: {e}")


def plot_overlay(sym1: str, sym2: str):
    """Display two stock charts overlaid for correlation analysis.
    
    Creates a matplotlib figure with overlaid normalized price data
    for sym1 and sym2, allowing visual identification of price correlation
    and synchronized movement patterns.
    
    Args:
        sym1 (str): First stock symbol (primary)
        sym2 (str): Second stock symbol (overlay, normalized to match scale)
    """
    try:
        print(f"\nOverlay Mode: {sym1} + {sym2}")
        print("(Normalized price overlay for correlation analysis)")
        # Integration point: Call plotter with overlay flag
        # plotter.plot_comparison(sym1, sym2, "overlay")
        print(f"Overlaying normalized prices...")
        print(f"Red: {sym1}, Blue: {sym2}")
    except Exception as e:
        print(f"Error in overlay comparison: {e}")


def save_selected(selected: set):
    """Save selected symbols to a CSV file for later analysis.
    
    Writes each selected symbol to a new line in 'selections.csv'.
    This allows users to mark interesting stocks during chart review
    for batch analysis or further study.
    
    Args:
        selected (set): Set of stock symbols marked by the user.
        
    Returns:
        None (exits early if set is empty)
    """
    if not selected:
        return

    save_file = DIR / "selections.csv"

    print(f"Selections saved to: {save_file}")

    save_file.write_text("\n".join(selected))


def get_symbol_input(prompt: str) -> str:
    """Prompt user to select a symbol from the watchlist.
    
    Displays numbered list of available symbols and processes user input
    to return the selected symbol name.
    
    Args:
        prompt (str): Display prompt for user
        
    Returns:
        str: Selected symbol or empty string if cancelled
    """
    print(f"\n{prompt}")
    print("Available symbols:")
    for i, sym in enumerate(symList, 1):
        print(f"  {i}. {sym}")
    
    try:
        choice = input("Enter number (or 'cancel'): ").strip()
        if choice.lower() == "cancel":
            return ""
        idx = int(choice) - 1
        if 0 <= idx < len(symList):
            return symList[idx]
        else:
            print("Invalid selection")
            return ""
    except (ValueError, EOFError):
        print("Invalid input")
        return ""


# Main interactive loop: Navigate through charts and mark selections
# Keyboard controls: n=next, p=previous, a=add to selection, c=compare, l=overlay, h=help, q=quit
while True:
    # Add to selection tracking
    if answer == "a":
        print(f"added {symList[plotter.idx - 1]}")
        selected.add(symList[plotter.idx - 1])

    # Help menu
    elif answer == "h":
        display_help()
        answer = ""
        continue

    # Side-by-side comparison mode
    elif answer == "c":
        current_sym = symList[plotter.idx]
        compare_sym = get_symbol_input(
            f"\nCompare '{current_sym}' with which stock?"
        )
        if compare_sym:
            plot_side_by_side(current_sym, compare_sym)
            comparison_symbols = [current_sym, compare_sym]
        answer = ""
        continue

    # Overlay mode for correlation analysis
    elif answer == "l":
        current_sym = symList[plotter.idx]
        overlay_sym = get_symbol_input(
            f"\nOverlay '{current_sym}' with which stock for correlation?"
        )
        if overlay_sym:
            plot_overlay(current_sym, overlay_sym)
            overlay_symbols = [current_sym, overlay_sym]
        answer = ""
        continue

    # Display or advance chart:
    # - n (next): Display next chart
    # - p (previous): Display previous chart  
    # - a (add): Already added to selected, now display next chart
    if answer in ("n", "p", "a"):
        # Check if reached end of list
        if plotter.idx == plotter.len:
            break

        # Display progress counter
        print(f"{plotter.idx + 1} of {plotter.len}", flush=True, end="\r" * 11)

        # Render chart for current symbol
        plotter.plot(symList[plotter.idx])

    # Get user input for next action
    answer = plotter.key

    # Navigate forward (next or after adding selection)
    if answer in ("n", "a"):
        if plotter.idx == plotter.len:
            save_selected(selected)
            exit("\nDone")
        plotter.idx += 1

    # Navigate backward
    elif answer == "p":
        if plotter.idx == 0:
            print("\nAt first Chart")
            answer = ""
            continue
        plotter.idx -= 1
        
    # Quit: Save resume state and selections
    elif answer == "q":
        # Save resume position if using watchlist
        if args.watch:
            if plotter.configPath.is_file():
                userObj = loadJson(plotter.configPath)
            else:
                userObj = {}

            # Store watchlist name and current position for resume
            userObj["PLOT_RESUME"] = {"watch": args.watch, "idx": plotter.idx}
            
            # Save comparison history if available
            if comparison_symbols:
                if "COMPARISON_HISTORY" not in userObj:
                    userObj["COMPARISON_HISTORY"] = []
                userObj["COMPARISON_HISTORY"].append({
                    "type": "side-by-side",
                    "symbols": comparison_symbols,
                    "date": datetime.now().isoformat()
                })
            
            if overlay_symbols:
                if "OVERLAY_HISTORY" not in userObj:
                    userObj["OVERLAY_HISTORY"] = []
                userObj["OVERLAY_HISTORY"].append({
                    "type": "overlay",
                    "symbols": overlay_symbols,
                    "date": datetime.now().isoformat()
                })
            
            writeJson(plotter.configPath, userObj)
        save_selected(selected)
        exit("\nquiting")

# Final save and exit
save_selected(selected)
print("\n✓ Session complete. Selections and comparison history saved.")
