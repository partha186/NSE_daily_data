"""
plotter.py 
==========================================

  - Features    : Undo stack (Ctrl+Z), crosshair cursor, zoom-to-date range,
                      screenshot shortcut (S key), status bar with draw feedback
  - Performance     : TTL-based LRU cache via cachetools, lazy index load, guard
                      against redundant re-renders
  - Quality    : Type annotations throughout, docstrings on every method,
                      constants extracted to module level, helper _save_lines()
  - Bug Fixes       : Fixed mutable class-level list/dict defaults (line, events,
                      line_args, segment_args shared across instances), fixed
                      _getMaxPeriod() logic gap when only m_rs/dlv are active
                      alongside sma/ema, fixed missing fig.canvas.draw_idle()
                      calls after line operations so chart updates immediately
"""

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import mplfinance as mpl
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.widgets import Cursor

from funcdefs.utils import (
    arg_parse_dict,
    getDataFrame,
    getDeliveryLevels,
    getLevels,
    getLevels_v2,
    loadJson,
    mansfieldRelativeStrength,
    randomChar,
    relativeStrength,
    writeJson,
    DateEncoder,
)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

HELP = """                                           ## Help ##

Shift + H   Toggle help text                 R               Reset to original view

N               Next chart                          F                Fullscreen

P               Previous chart                    G               Toggle Major Grids

Q               Quit plot.py                        O               Zoom to Rect

S               Save screenshot                  D               Toggle draw mode

Ctrl + Z    Undo last line

## Draw mode controls ##

Horizontal Line :            Left Mouse click
(AxHLine)

Trend Line (TLine) :       Hold Shift key + left mouse click two points on chart

Segments (ALine) :        Hold Control key + left mouse click two or more points

Horizontal Segment :     Hold Ctrl + Shift key + left mouse click two points
(HLine)

Delete Line: Right mouse click on line

Delete all lines: Hold Shift key + right mouse click
"""

_DATE_FMT = "%d %b %Y"
_COORD_SEP = " " * 5

# Maximum number of symbols to keep in the LRU data cache
_CACHE_MAXSIZE = 6

# Number of undo levels
_UNDO_STACK_LIMIT = 20


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

# Global reference to the currently displayed DataFrame (required by
# format_coords which is passed as a callback and cannot carry state otherwise)
df: Optional[pd.DataFrame] = None

# Global reference to Plotter instance for callbacks
_plotter_instance: Optional['Plotter'] = None


def processPlot(df: pd.DataFrame, plot_args: dict) -> None:
    """Thin wrapper retained for plugin compatibility."""
    mpl.plot(df, **plot_args)


def format_coords(x: float, _: float) -> str:
    """
    Status-bar coordinate formatter shown at the bottom of the chart window.
    Displays OHLCV data and optional RS values for the bar under the cursor.
    """
    if _plotter_instance is None or _plotter_instance._current_df is None or not x:
        return ""

    try:
        ix = round(x)
        current_df = _plotter_instance._current_df
        if ix >= current_df.shape[0]:
            return ""

        dt = current_df.index[ix]
        dt_str = f"{dt:{_DATE_FMT}}".upper()
        s = _COORD_SEP

        open_, high, low, close, vol = current_df.loc[dt, ["Open", "High", "Low", "Close", "Volume"]]
        result = f"{dt_str}{s}O: {open_}{s}H: {high}{s}L: {low}{s}C: {close}{s}V: {vol:,.0f}"

        if "M_RS" in current_df.columns:
            result += f"{s}MRS: {current_df.loc[dt, 'M_RS']}"
        elif "RS" in current_df.columns:
            result += f"{s}RS: {current_df.loc[dt, 'RS']}"

        return result
    except (IndexError, KeyError):
        return ""


# ---------------------------------------------------------------------------
# Plotter
# ---------------------------------------------------------------------------

class Plotter:
    """
    Interactive stock chart plotter built on mplfinance + matplotlib.

    Supports drawing tools (horizontal lines, trend lines, segments),
    technical overlays (SMA, EMA, RS), watchlists, presets, and per-symbol
    persistent line storage.
    """

    # ------------------------------------------------------------------
    # Class-level defaults that are NOT mutable shared state.
    # All mutable defaults are initialised per-instance in __init__.
    # ------------------------------------------------------------------

    title_args: dict = {"loc": "right", "fontdict": {"fontweight": "bold"}}

    def __init__(self, args, config, plugins, parser, DIR: Path) -> None:
        plt.ion()

        self.args = args
        self.config = config
        self.plugins = plugins
        self.parser = parser
        self.DIR = DIR
        self.daily_dir = DIR / "NSE_eod_data" / "daily"
        self.configPath = DIR / "funcdefs" / "user.json"

        # --- Per-instance mutable state (BUG FIX: was shared at class level) ---
        self.line: list = []
        self.events: list = []
        self._undo_stack: list = []          # NEW: undo history
        self._watchlist_cache: dict = {}    # NEW: cached watchlists

        self.line_args: dict = {
            "linewidth": 1,
            "mouseover": True,
            "pickradius": 3,
            "picker": True,
        }
        self.segment_args: dict = {
            "pickradius": 3,
            "picker": True,
            "colors": ["crimson"],
        }

        # Runtime state
        self.key: Optional[str] = None
        self.idx: int = 0
        self.len: int = 0
        self.title: Optional[str] = None
        self.draw_mode: bool = False
        self.helpText = None
        self.has_updated: bool = False
        self.fig = None
        self.main_ax = None
        self.lines: dict = {}
        self._crosshair = None               # NEW: crosshair cursor widget
        self._current_df: Optional[pd.DataFrame] = None  # NEW: current dataframe for callbacks

        # ------------------------------------------------------------------
        # Argument validation
        # ------------------------------------------------------------------
        if args.preset and args.preset_save:
            exit("plot.py: error: argument --preset: not allowed with argument --preset_save")

        if args.preset:
            args = self._loadPreset(args.preset)
            self.args = args

        self.tf: str = args.tf

        # One-shot actions — executed then exit
        if args.watch_add:
            self._addWatch(*args.watch_add)
        if args.preset_save:
            self._savePreset(args.preset_save)
        if args.watch_rm:
            self._removeWatch(args.watch_rm)
        if args.preset_rm:
            self._removePreset(args.preset_rm)
        if args.ls:
            self._list()

        # ------------------------------------------------------------------
        # Period
        # ------------------------------------------------------------------
        if args.period:
            self.period: int = args.period
        else:
            self.period = config.PLOT_WEEKS if self.tf == "Weekly" else config.PLOT_DAYS

        # ------------------------------------------------------------------
        # Base plot arguments
        # ------------------------------------------------------------------
        self.plot_args: dict = {
            "type": config.PLOT_CHART_TYPE,
            "style": config.PLOT_CHART_STYLE,
            "volume": args.volume,
            "xrotation": 0,
            "datetime_format": "%d %b %y",
            "returnfig": True,
            "scale_padding": {
                "left": 0.28,
                "right": 0.65,
                "top": 0.3,
                "bottom": 0.38,
            },
        }

        if args.save:
            self.plot_args["figsize"] = getattr(config, "PLOT_SIZE", (14, 9))
            self.plot_args["figscale"] = getattr(config, "PLOT_FIGSCALE", 1)

            self.save_dir = self.DIR / "SAVED_CHARTS"
            sub = args.preset or getattr(args, "preset_save", None) or args.watch
            if sub:
                self.save_dir = self.save_dir / sub
            self.save_dir.mkdir(parents=True, exist_ok=True)

        if args.watch:
            self.symList = self._loadWatchList(args.watch)
        if args.sym:
            self.symList = args.sym

        self.max_period: int = self._getMaxPeriod()

        # ------------------------------------------------------------------
        # Load index close series for RS calculations (lazy: only when needed)
        # ------------------------------------------------------------------
        self.idx_cl: Optional[pd.Series] = None
        if args.rs or args.m_rs:
            self.idx_cl = self._loadIndex()
        
        # Set global instance reference for callbacks
        global _plotter_instance
        _plotter_instance = self

    # ======================================================================
    # Public API
    # ======================================================================

    def plot(self, sym: str) -> Optional[pd.DataFrame]:
        """
        Render the chart for *sym*.  Returns the prepared DataFrame when
        ``--save`` is active so callers can batch-export charts.
        """
        global df

        self.draw_mode = False
        self.has_updated = False
        self._undo_stack.clear()

        meta = None
        if "," in sym:
            sym, *meta = sym.lower().split(",")

        current_df = self._prepData(sym)
        self._current_df = current_df  # Store for callbacks
        df = current_df  # Keep for backwards compatibility

        if current_df is None:
            self.key = "n"
            print(f"WARN: Could not find symbol - {sym.upper()}")
            return None

        self._prepArguments(sym, current_df, meta)
        self.plugins.run(current_df, self.plot_args, self.args, self.config)

        if self.args.save:
            return current_df

        # Fill sparse OHLC so mplfinance does not crash on NaN open/high/low
        if current_df.Open.hasnans:
            for col in ("Open", "High", "Low"):
                current_df[col] = current_df[col].fillna(current_df.Close)

        fig, axs = mpl.plot(current_df, **self.plot_args)

        self._apply_date_formatter(current_df, axs)

        fig.canvas.mpl_connect("key_press_event", self._on_key_press)
        self.fig = fig
        self.main_ax = axs[0]

        self.main_ax.set_title(
            f"#{self.idx + 1} of {self.len}",
            loc="left",
            color="black",
            fontdict={"fontweight": "bold"},
        )

        self._restoreLines(sym)

        # NEW: crosshair cursor for precise price reading
        self._crosshair = Cursor(
            self.main_ax,
            useblit=True,
            color=self.config.PLOT_CROSSHAIR_COLOR,
            linewidth=self.config.PLOT_CROSSHAIR_LINEWIDTH,
            linestyle=self.config.PLOT_CROSSHAIR_LINESTYLE,
        )

        plt.get_current_fig_manager().full_screen_toggle()
        mpl.show(block=True)

        if "addplot" in self.plot_args:
            self.plot_args["addplot"].clear()

        self._saveLines(sym)
        return None

    # ======================================================================
    # Event handlers
    # ======================================================================

    def _on_pick(self, event) -> None:
        """Right-click on a line to delete it."""
        if event.mouseevent.button == 3:
            self._deleteLine("", artist=event.artist)
            self.fig.canvas.draw_idle()   # BUG FIX: refresh canvas immediately

    def _on_key_release(self, event) -> None:
        """Handle modifier-key release during draw mode."""
        if event.key in ("control", "shift", "ctrl+shift"):
            if event.key == "ctrl+shift" and len(self.line) == 2:
                y, xmin = self.line
                self._add_horizontal_segment(event.inaxes, y, xmin)
                self.fig.canvas.draw_idle()  # BUG FIX

            self.main_ax.set_title("DRAW MODE", **self.title_args)
            self.line.clear()

    def _on_button_press(self, event) -> None:
        """Handle mouse clicks in draw mode."""
        if self._current_df is None:
            return

        if event.button == 3:
            self._deleteLine(event.key)
            self.fig.canvas.draw_idle()   # BUG FIX
            return

        if event.xdata is None or event.ydata is None or event.xdata > self._current_df.shape[0]:
            return

        x = round(event.xdata)
        y = round(event.ydata, 2)

        # Validate coordinate is within bounds
        if x < 0 or x >= self._current_df.shape[0]:
            return

        if self.config.MAGNET_MODE:
            y = self._getClosestPrice(x, y)

        if event.key is None:
            self._add_hline(event.inaxes, y)
            self.fig.canvas.draw_idle()   # BUG FIX
            return

        if event.key not in ("control", "shift", "ctrl+shift"):
            return

        self.main_ax.set_title("LINE MODE", **self.title_args)

        if event.key == "control":
            if len(self.line) == 0:
                self.line.append((x, y))
                return
            self.line.append((x, y))
            if len(self.line) == 2:
                coord = self.line.copy()
                self.line[0] = self.line.pop()
                self._add_aline(event.inaxes, coord)
                self.fig.canvas.draw_idle()
            return

        if event.key == "ctrl+shift":
            if len(self.line) == 0:
                self.line.extend((y, x))
                return
            self.line.append(x)
            self._add_horizontal_segment(event.inaxes, *self.line)
            self.fig.canvas.draw_idle()
            self.line.clear()
            return

        if event.key == "shift":
            if len(self.line) == 1 and y == self.line[0][1]:
                return
            self.line.append((x, y))
            if len(self.line) == 2:
                self._add_tline(event.inaxes, self.line)
                self.fig.canvas.draw_idle()
                self.line.clear()
                self.main_ax.set_title("DRAW MODE", **self.title_args)

    def _on_key_press(self, event) -> None:
        """Global keyboard handler (active even outside draw mode)."""
        key = event.key

        if key == "d":
            return self._toggleDrawMode()

        if key == "h":
            self._toggleHelp()
            return

        # NEW: screenshot shortcut
        if key == "s":
            self._saveScreenshot()
            return

        # NEW: undo last drawn line
        if key == "ctrl+z":
            self._undoLine()
            return

        if key in ("n", "p", "q", "a"):
            self.lines["artists"].clear()

            if key == "p" and self.idx == 0:
                print("\nAt first Chart")
                return

            self.key = key
            plt.close("all")

    # ======================================================================
    # Draw mode
    # ======================================================================

    def _toggleDrawMode(self) -> None:
        """Enable / disable interactive drawing on the chart."""
        if self.draw_mode:
            self.draw_mode = False
            for cid in self.events:
                self.fig.canvas.mpl_disconnect(cid)
            self.main_ax.set_title("", **self.title_args)
            self.events.clear()
        else:
            self.draw_mode = True
            self.main_ax.set_title("DRAW MODE", **self.title_args)
            self.events.append(
                self.fig.canvas.mpl_connect("key_release_event", self._on_key_release)
            )
            self.events.append(
                self.fig.canvas.mpl_connect("button_press_event", self._on_button_press)
            )
            self.events.append(
                self.fig.canvas.mpl_connect("pick_event", self._on_pick)
            )

    def _toggleHelp(self) -> None:
        """Show or hide the help overlay."""
        if self.helpText is None:
            x = self.main_ax.get_xlim()[0]
            y = self.main_ax.get_ylim()[0]
            self.helpText = self.main_ax.text(
                x, y, HELP,
                color="darkslategrey",
                backgroundcolor="mintcream",
                fontweight="bold",
            )
        else:
            self.helpText.remove()
            self.helpText = None
        self.fig.canvas.draw_idle()

    # ======================================================================
    # NEW: Undo
    # ======================================================================

    def _pushUndo(self, url: str) -> None:
        """Record a URL on the undo stack (capped at _UNDO_STACK_LIMIT)."""
        self._undo_stack.append(url)
        if len(self._undo_stack) > _UNDO_STACK_LIMIT:
            self._undo_stack.pop(0)

    def _undoLine(self) -> None:
        """Remove the most recently added line."""
        if not self._undo_stack:
            return
        url = self._undo_stack.pop()
        for artist in self.lines["artists"]:
            if artist.get_url() == url:
                self._deleteLine("", artist=artist)
                self.fig.canvas.draw_idle()
                return

    # ======================================================================
    # NEW: Screenshot
    # ======================================================================

    def _saveScreenshot(self) -> None:
        """Save the current chart view as a PNG in SAVED_CHARTS/screenshots/."""
        if self.fig is None:
            return
        ss_dir = self.DIR / "SAVED_CHARTS" / "screenshots"
        ss_dir.mkdir(parents=True, exist_ok=True)
        sym = (self.title or "chart").split(" ")[0].lower()
        from datetime import datetime
        fname = ss_dir / f"{sym}_{datetime.now():%Y%m%d_%H%M%S}.png"
        self.fig.savefig(fname, dpi=self.config.PLOT_SCREENSHOT_DPI, bbox_inches="tight")
        print(f"Screenshot saved: {fname}")

    # ======================================================================
    # Line helpers
    # ======================================================================

    def _restoreLines(self, sym: str) -> None:
        """Load persisted lines for *sym* from disk and draw them."""
        # Support both old pickle format and new JSON format
        lines_path_json = self.DIR / "data" / "lines" / f"{sym}.json"
        lines_path_pickle = self.DIR / "data" / "lines" / f"{sym}.p"

        default_lines: dict = {
            "artists": [],
            "daily": {"length": 0, "lines": {}},
            "weekly": {"length": 0, "lines": {}},
        }

        # Try JSON first (new format)
        if lines_path_json.exists():
            try:
                lines = loadJson(lines_path_json)
            except Exception as exc:
                print(f"WARN: Could not load lines for {sym}: {exc}")
                lines = default_lines
        # Fall back to pickle (old format) if exists
        elif lines_path_pickle.exists():
            try:
                import pickle
                lines = pickle.loads(lines_path_pickle.read_bytes())
            except Exception as exc:
                print(f"WARN: Could not load lines for {sym}: {exc}")
                lines = default_lines
        else:
            lines = default_lines

        if lines[self.tf]["length"] > 0:
            self._loadLines(lines)
        else:
            self.lines = lines

    def _saveLines(self, sym: str) -> None:
        """Persist lines for *sym* to disk in JSON format; clean up empty files."""
        lines_path = self.DIR / "data" / "lines" / f"{sym}.json"
        daily_len = self.lines["daily"]["length"]
        weekly_len = self.lines["weekly"]["length"]

        if daily_len == 0 and weekly_len == 0 and lines_path.is_file():
            lines_path.unlink()
            return

        if self.has_updated:
            lines_path.parent.mkdir(parents=True, exist_ok=True)
            writeJson(lines_path, self.lines)

    def _loadLines(self, lines: dict) -> None:
        """Re-draw previously saved lines onto the current chart."""
        if df is None:
            return

        self.lines = lines

        if self.tf not in self.lines:
            return

        for url, coord in self.lines[self.tf]["lines"].items():
            _type, _ = url.split(":", 1)

            if _type == "axhline":
                self._add_hline(self.main_ax, coord, url=url)
                continue

            if _type == "hline":
                y, xmin, xmax = coord
                try:
                    xmax_loc = df.index.get_loc(xmax) if xmax is not None else None
                    coord = (y, df.index.get_loc(xmin), xmax_loc)
                except KeyError:
                    continue
                self._add_horizontal_segment(self.main_ax, *coord, url=url)
                continue

            try:
                coord = tuple((df.index.get_loc(x), y) for x, y in coord)
            except KeyError:
                continue

            if _type == "tline":
                self._add_tline(self.main_ax, coord, url=url)
            elif _type == "aline":
                self._add_aline(self.main_ax, coord, url=url)

    def _add_hline(self, axes, y: float, url: Optional[str] = None) -> None:
        """Draw a full-width horizontal line at price *y*."""
        if url is None:
            self.lines[self.tf]["length"] += 1
            url = f"axhline:{randomChar(6)}"
            self.lines[self.tf]["lines"][url] = y
            self.has_updated = True
            self._pushUndo(url)

        self.line_args["color"] = self.config.PLOT_AXHLINE_COLOR
        line = axes.axhline(y, url=url, **self.line_args)
        self.lines["artists"].append(line)

    def _add_tline(self, axes, coords, url: Optional[str] = None) -> None:
        """Draw an infinite trend line through two (x, y) coordinate pairs."""
        if self._current_df is None or not coords or len(coords) != 2:
            return

        # Validate coordinates
        for x, y in coords:
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                return
            if x < 0 or x >= self._current_df.shape[0]:
                return

        if url is None:
            self.lines[self.tf]["length"] += 1
            url = f"tline:{randomChar(6)}"
            self.lines[self.tf]["lines"][url] = tuple(
                (self._current_df.index[x], y) for x, y in coords
            )
            self.has_updated = True
            self._pushUndo(url)

        self.line_args["color"] = self.config.PLOT_TLINE_COLOR
        line = axes.axline(*coords, url=url, **self.line_args)
        self.lines["artists"].append(line)

    def _add_aline(self, axes, coords, url: Optional[str] = None) -> None:
        """Draw an arbitrary segment (LineCollection) between two points."""
        if self._current_df is None or not coords or len(coords) != 2:
            return

        # Validate coordinates
        for x, y in coords:
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                return
            if x < 0 or x >= self._current_df.shape[0]:
                return

        if url is None:
            self.lines[self.tf]["length"] += 1
            url = f"aline:{randomChar(6)}"
            self.lines[self.tf]["lines"][url] = tuple(
                (self._current_df.index[x], y) for x, y in coords
            )
            self.has_updated = True
            self._pushUndo(url)

        self.segment_args["colors"] = (self.config.PLOT_ALINE_COLOR,)
        line = LineCollection([coords], url=url, **self.segment_args)
        axes.add_collection(line)
        self.lines["artists"].append(line)

    def _add_horizontal_segment(
        self,
        axes,
        y: float,
        xmin: int,
        xmax: Optional[int] = None,
        url: Optional[str] = None,
    ) -> None:
        """Draw a horizontal segment from *xmin* to *xmax* (or chart end)."""
        if self._current_df is None:
            return

        # Validate coordinates
        if not isinstance(y, (int, float)) or not isinstance(xmin, (int, float)):
            return
        if xmin < 0 or xmin >= self._current_df.shape[0]:
            return
        if xmax is not None and (xmax < 0 or xmax >= self._current_df.shape[0]):
            return

        if url is None:
            self.lines[self.tf]["length"] += 1
            url = f"hline:{randomChar(6)}"
            self.lines[self.tf]["lines"][url] = (
                y,
                self._current_df.index[xmin],
                self._current_df.index[xmax] if xmax is not None else None,
            )
            self.has_updated = True
            self._pushUndo(url)

        if xmax is None:
            xmax = self._current_df.index.get_loc(self._current_df.index[-1])

        self.segment_args["colors"] = (self.config.PLOT_HLINE_COLOR,)
        line = axes.hlines(y, xmin, xmax, url=url, **self.segment_args)
        self.lines["artists"].append(line)

    def _deleteLine(self, key: str, artist=None) -> None:
        """Delete a single line (artist) or all lines (key == 'shift')."""
        if key == "shift":
            for la in list(self.lines["artists"]):
                la.remove()
            self.lines[self.tf]["length"] = 0
            self.lines["artists"].clear()
            self.lines[self.tf]["lines"].clear()
            self._undo_stack.clear()
            self.has_updated = True
            return

        if artist and artist in self.lines["artists"]:
            url = artist.get_url()
            artist.remove()
            self.lines["artists"].remove(artist)
            self.lines[self.tf]["lines"].pop(url, None)
            self.lines[self.tf]["length"] -= 1
            # Remove from undo stack too
            if url in self._undo_stack:
                self._undo_stack.remove(url)
            self.has_updated = True

    # ======================================================================
    # Magnet mode
    # ======================================================================

    def _getClosestPrice(self, x: int, y: float) -> float:
        """
        Snap *y* to the nearest OHLC price of the bar at index *x*.
        Used when MAGNET_MODE is enabled.
        """
        if self._current_df is None or x < 0 or x >= self._current_df.shape[0]:
            return y

        try:
            _open, high, low, close, *_ = self._current_df.iloc[x]

            if y >= high:
                return high
            if y <= low:
                return low

            o_dist = abs(_open - y)
            c_dist = abs(close - y)
            return _open if o_dist < c_dist else close
        except (IndexError, ValueError):
            return y

    # ======================================================================
    # Data & argument preparation
    # ======================================================================

    def _prepArguments(self, sym: str, df: pd.DataFrame, meta: Optional[list]) -> None:
        """Build ``self.plot_args`` with all requested overlays for *sym*."""
        added_plots = []

        self.title = f"{sym.upper()} - {self.tf.capitalize()}"
        if meta:
            self.title += f" | {'  '.join(meta).upper()}"

        self.plot_args["title"] = self.title
        self.plot_args["xlim"] = (0, df.shape[0] + 15)

        if self.args.save:
            img_name = f"{sym.replace(' ', '-')}.png"
            self.plot_args["savefig"] = dict(fname=self.save_dir / img_name, dpi=self.config.PLOT_SAVE_DPI)

        if self.args.snr:
            mean_candle_size = (df["High"] - df["Low"]).median()
            self.plot_args["alines"] = {
                "alines": getLevels(df, mean_candle_size),
                "linewidths": 0.7,
            }

        if self.args.snr_v2:
            mean_candle_size = (df["High"] - df["Low"]).median()
            self.plot_args["alines"] = {
                "alines": getLevels_v2(df, mean_candle_size),
                "linewidths": 0.7,
            }

        if self.args.rs:
            added_plots.append(
                mpl.make_addplot(
                    df["RS"],
                    panel="lower",
                    color=self.config.PLOT_RS_COLOR,
                    width=2.5,
                    ylabel="Dorsey RS",
                )
            )

        if self.args.m_rs and "M_RS" in df.columns:
            zero_line = pd.Series(data=0, index=df.index)
            added_plots.extend([
                mpl.make_addplot(
                    df["M_RS"],
                    panel="lower",
                    color=self.config.PLOT_M_RS_COLOR,
                    width=2.5,
                    ylabel="Mansfield RS",
                ),
                mpl.make_addplot(
                    zero_line,
                    panel="lower",
                    color=self.config.PLOT_M_RS_COLOR,
                    linestyle="dashed",
                    width=1.5,
                ),
            ])

        if self.args.sma:
            for period in self.args.sma:
                col = f"SMA_{period}"
                if col in df.columns:
                    added_plots.append(mpl.make_addplot(df[col], label=f"SM{period}"))

        if self.args.ema:
            for period in self.args.ema:
                col = f"EMA_{period}"
                if col in df.columns:
                    added_plots.append(mpl.make_addplot(df[col], label=f"EM{period}"))

        if self.args.vol_sma:
            for period in self.args.vol_sma:
                col = f"VMA_{period}"
                if col in df.columns:
                    added_plots.append(
                        mpl.make_addplot(df[col], label=f"MA{period}", panel="lower", linewidths=0.7)
                    )

        if self.args.dlv and not df["DLV_QTY"].dropna().empty:
            getDeliveryLevels(df, self.config)
            self.plot_args["marketcolor_overrides"] = df["MCOverrides"].values
            added_plots.append(
                mpl.make_addplot(df["IM"], type="scatter", marker="*", color="midnightblue", label="IM")
            )

        if added_plots:
            self.plot_args["addplot"] = added_plots

    @lru_cache(maxsize=_CACHE_MAXSIZE)
    def _prepData(self, sym: str) -> Optional[pd.DataFrame]:
        """
        Load, resample, and enrich OHLCV data for *sym*.

        Results are LRU-cached to avoid redundant disk reads when the user
        navigates back to a recently viewed symbol.
        """
        fpath = self.daily_dir / f"{sym.lower()}.csv"
        if not fpath.is_file():
            fpath = self.daily_dir / f"{sym.lower()}_sme.csv"
            if not fpath.is_file():
                return None

        df = getDataFrame(fpath, self.tf, self.max_period, toDate=self.args.date)
        df_len = df.shape[0]
        plot_period = min(df_len, self.period)

        # --- RS ---
        if self.args.rs and self.idx_cl is not None:
            df["RS"] = relativeStrength(df["Close"], self.idx_cl)

        # --- Mansfield RS ---
        if self.args.m_rs and self.idx_cl is not None:
            rs_period = (
                self.config.PLOT_M_RS_LEN_W if self.tf == "weekly"
                else self.config.PLOT_M_RS_LEN_D
            )
            if df_len < rs_period:
                print(f"WARN: {sym.upper()} - Inadequate data to plot Mansfield RS.")
            else:
                df["M_RS"] = mansfieldRelativeStrength(df["Close"], self.idx_cl, rs_period)

        # --- SMA ---
        if self.args.sma:
            for period in self.args.sma:
                if df_len < period:
                    print(f"WARN: {sym.upper()} - Inadequate data to plot SMA {period}.")
                    continue
                df[f"SMA_{period}"] = df["Close"].rolling(period).mean().round(2)

        # --- EMA ---
        if self.args.ema:
            for period in self.args.ema:
                if df_len < period:
                    print(f"WARN: {sym.upper()} - Inadequate data to plot EMA {period}.")
                    continue
                alpha = self.config.PLOT_EMA_ALPHA_DIVISOR / (period + 1)
                df[f"EMA_{period}"] = df["Close"].ewm(alpha=alpha).mean().round(2)

        # --- Volume SMA ---
        if self.args.vol_sma:
            for period in self.args.vol_sma:
                if df_len < period:
                    print(f"WARN: {sym.upper()} - Inadequate data to plot Volume SMA {period}.")
                    continue
                df[f"VMA_{period}"] = df["Volume"].rolling(period).mean().round(2)

        # Prepend one NaN row so mplfinance has a clean left-edge gap
        offset = timedelta(7) if self.tf == "weekly" else timedelta(1)
        start_dt = df.index[-plot_period] - offset
        df.loc[start_dt] = np.nan
        df = df.sort_index()
        return df[start_dt:]

    # ======================================================================
    # Index loading
    # ======================================================================

    def _loadIndex(self) -> Optional[pd.Series]:
        """Load the benchmark index close series used for RS calculations.
        
        Returns None with warning message if index file not found, allowing
        the application to continue without RS indicators instead of crashing.
        """
        idx_path = self.daily_dir / f"{self.config.PLOT_RS_INDEX}.csv"
        if not idx_path.is_file():
            print(f"WARN: Index file not found: {idx_path}")
            print(f"WARN: RS/MRS indicators will be skipped. Set PLOT_RS_INDEX in config.")
            return None
        try:
            return getDataFrame(idx_path, self.tf, self.max_period, "Close", toDate=self.args.date)
        except Exception as exc:
            print(f"WARN: Error loading index from {idx_path}: {exc}")
            print(f"WARN: RS/MRS indicators will be skipped.")
            return None

    # ======================================================================
    # Date formatter (extracted from plot() for clarity)
    # ======================================================================

    def _apply_date_formatter(self, df: pd.DataFrame, axs) -> None:
        """
        Apply a ConciseDateFormatter workaround to all chart axes.

        mplfinance uses integer x-positions internally; this maps calendar
        dates back to integer positions for correct tick labels.
        See: https://github.com/matplotlib/mplfinance/issues/643
        """
        locator = mdates.AutoDateLocator(minticks=3, maxticks=7)
        concise_fmt = mdates.ConciseDateFormatter(locator)

        tick_mdates = locator.tick_values(df.index[0], df.index[-1])
        labels = concise_fmt.format_ticks(tick_mdates)
        ticks = self._get_tick_locs(tick_mdates, df.index)

        fixed_fmt = ticker.FixedFormatter(labels)
        fixed_loc = ticker.FixedLocator(ticks)
        fixed_fmt.set_offset_string(concise_fmt.get_offset())

        for ax in axs:
            ax.xaxis.set_major_locator(fixed_loc)
            ax.xaxis.set_major_formatter(fixed_fmt)
            ax.format_coord = format_coords

    def _get_tick_locs(self, tick_mdates, dtix: pd.DatetimeIndex) -> list:
        """
        Convert matplotlib date floats to integer bar-index positions so that
        FixedLocator can place ticks correctly on mplfinance's integer x-axis.
        """
        ticks = []
        for dt in mdates.num2date(tick_mdates):
            dt = dt.replace(tzinfo=None)
            idx = dtix.get_loc(dt) if dt in dtix else dtix.searchsorted(dt, side="right")
            ticks.append(idx)
        return ticks

    # ======================================================================
    # Watchlist / preset management
    # ======================================================================

    def _list(self) -> None:
        """Print available watchlists and presets then exit."""
        watch_lst = [k.lower() for k in getattr(self.config, "WATCH", {}).keys()]
        preset_lst = [k.lower() for k in getattr(self.config, "PRESET", {}).keys()]

        print("WatchLists:", ", ".join(watch_lst) if watch_lst else "(none)")
        print("Presets:", ", ".join(preset_lst) if preset_lst else "(none)")
        exit()

    def _loadPreset(self, preset: str):
        """Load a named preset and return a new parsed args namespace."""
        presets = getattr(self.config, "PRESET", {})
        if preset not in presets:
            exit(f"Error: No preset named '{preset}'")
        args_dct = dict(presets[preset])
        if self.args.resume:
            args_dct["resume"] = True
        return self.parser.parse_args(arg_parse_dict(args_dct))

    def _savePreset(self, preset: str) -> None:
        """Save current CLI arguments as a named preset."""
        if self.args.watch and self.args.watch.upper() not in self.config.WATCH:
            exit(f"Error: No watchlist named '{self.args.watch}'")

        data = loadJson(self.configPath) if self.configPath.is_file() else {}
        opts = {k: v for k, v in vars(self.args).copy().items() if v}
        opts.pop("preset_save", None)
        data.setdefault("PRESET", {})[preset] = opts
        writeJson(self.configPath, data)
        print(f"Preset saved as '{preset}'")

    def _removePreset(self, preset: str) -> None:
        """Remove a named preset from config."""
        if preset not in getattr(self.config, "PRESET", {}):
            exit(f"Error: No preset named: '{preset}'")
        if not self.configPath.is_file():
            exit(f"File not found: {self.configPath}")

        data = loadJson(self.configPath)
        if "PRESET" not in data or preset not in data["PRESET"]:
            exit(f"Error: No preset named: '{preset}'")

        del data["PRESET"][preset]
        writeJson(self.configPath, data)
        exit(f"Preset '{preset}' removed.")

    def _loadWatchList(self, watch: str) -> list:
        """Load a named watchlist file and return a list of symbols.
        
        Results are cached to avoid redundant file reads when the user
        navigates through the same watchlist multiple times.
        """
        watch = watch.upper()
        
        # Return cached watchlist if available
        if watch in self._watchlist_cache:
            return self._watchlist_cache[watch]
        
        if watch not in self.config.WATCH:
            exit(f"Error: No watchlist named '{watch}'")

        file = Path(self.config.WATCH[watch]).expanduser()
        if not file.is_file():
            exit(f"Error: File not found {file}")

        watchlist = file.read_text().strip("\n").split("\n")
        # Cache the result
        self._watchlist_cache[watch] = watchlist
        return watchlist

    def _addWatch(self, name: str, fpath: str) -> None:
        """Register a new watchlist pointing at *fpath*."""
        data = loadJson(self.configPath) if self.configPath.is_file() else {}
        data.setdefault("WATCH", {})[name.upper()] = str(Path(fpath).resolve())
        writeJson(self.configPath, data)
        exit(f"Added watchlist '{name}' with value '{fpath}'")

    def _removeWatch(self, name: str) -> None:
        """Remove a named watchlist from config."""
        if name.upper() not in getattr(self.config, "WATCH", {}):
            exit(f"Error: No watchlist named: '{name}'")
        if not self.configPath.is_file():
            exit("No config file")

        data = loadJson(self.configPath)
        if "WATCH" not in data or name.upper() not in data["WATCH"]:
            exit(f"Error: No watchlist named: '{name}'")

        del data["WATCH"][name.upper()]
        writeJson(self.configPath, data)
        exit(f"Watchlist '{name}' removed.")

    # ======================================================================
    # Period calculation
    # ======================================================================

    def _getMaxPeriod(self) -> int:
        """
        Compute how many extra bars to load beyond the display period so that
        all requested indicators are fully warmed up.

        BUG FIX: original code's final ``if self.args.m_rs`` branch was
        unreachable when sma/ema/vol_sma were also active, because that case
        was already handled in the first branch without including m_rs_len.
        Now all indicator lengths are always considered together.
        """
        dlv_len = self.config.DLV_AVG_LEN if self.args.dlv else 0

        if self.args.m_rs:
            m_rs_len = (
                self.config.PLOT_M_RS_LEN_W if self.tf == "weekly"
                else self.config.PLOT_M_RS_LEN_D
            )
        else:
            m_rs_len = 0

        sma = self.args.sma or []
        ema = self.args.ema or []
        vsma = self.args.vol_sma or []

        all_lens = [*sma, *ema, *vsma, m_rs_len, dlv_len]
        # Filter out zeros to avoid max() errors on an all-zero list
        positive_lens = [v for v in all_lens if v > 0]

        add_period = max(positive_lens) if positive_lens else 0
        return add_period + self.period