"""
Configuration Management Module 

This module defines all configurable settings for the system including:
- AmiBroker integration settings
- Delivery data analysis parameters
- data_get.py analysis tool settings
- Plot.py charting and visualization settings
- Data file locations and themes

CONFIGURATION OVERRIDE SYSTEM:
    The Config class uses a hierarchical configuration system:
    1. Default values defined in Config class attributes
    2. Optional user overrides from user.json (in src/funcdefs/ directory)
    
    To override defaults, create src/funcdefs/user.json with settings:
    {
        "AMIBROKER": true,
        "PLOT_DAYS": 200,
        "PLOT_CHART_STYLE": "dark"
    }
    
    All attribute names in user.json MUST be UPPERCASE.
    Settings are merged with defaults via __init__() method.

USAGE:
    from funcdefs import config
    
    # Access configuration values
    days_to_plot = config.PLOT_DAYS
    is_amibroker_enabled = config.AMIBROKER
    
    # Display all settings
    print(config)  # Uses __str__() method

CONFIGURATION CATEGORIES:
    - AmiBroker: Integration with AmiBroker charting software
    - Delivery: Delivery data thresholds and averaging parameters
    - DGET: data_get.py delivery analysis tool parameters
    - Plot: All charting and visualization settings
    - Watch: Stock watchlists and sector data
    - Hooks: User-defined callback functions
    - Version: System versioning information
"""

import json
from pathlib import Path

DIR = Path(__file__).parents[1]


class Config:
    """Configuration container for EOD2 system settings.
    
    OVERVIEW:
        This class stores all configuration parameters for EOD2 including
        data processing, analysis, visualization, and integration settings.
    
    DEFAULT VALUES:
        All attributes have sensible defaults appropriate for most users.
        These can be overridden by creating a user.json configuration file.
        
    USER CUSTOMIZATION:
        Create src/funcdefs/user.json to override any attribute:
        
        Example user.json:
        {
            "AMIBROKER": true,
            "AMI_UPDATE_DAYS": 500,
            "PLOT_DAYS": 200,
            "PLOT_CHART_STYLE": "charles",
            "PLOT_C_COLOR": "red"
        }
        
        Rules:
        - All keys must be UPPERCASE
        - Only include keys you want to override
        - WATCH and PRESET settings are merged, not replaced
        - Changes take effect immediately on Config instantiation
    
    PERSISTENCE:
        - Default values: Hard-coded in class attributes
        - User values: Loaded from user.json file
        - Version info: Set at class definition time (DO NOT EDIT)
    
    ACCESSING CONFIGURATION:
        from funcdefs import config
        
        # Get a single setting
        plot_days = config.PLOT_DAYS  # Returns: 160
        
        # Get all settings as formatted string
        all_settings = str(config)  # Prints: VERSION, all attributes
        
        # Get list from data file
        symbols = config.toList("symbols.csv")  # Returns: list of lines
    """

    # ========================================================================
    # HOOKS - User-defined callbacks
    # ========================================================================
    INIT_HOOK = None  # Custom initialization function called on startup
    
    # ========================================================================
    # AMIBROKER INTEGRATION - Convert data to AmiBroker format
    # ========================================================================
    AMIBROKER = False  # Enable/disable AmiBroker export on sync
    AMI_UPDATE_DAYS = 365  # Historical days to convert on first AmiBroker run
    # Purpose: AmiBroker is a charting/analysis tool; when enabled, EOD2
    #          automatically exports data in AmiBroker format
    
    # ========================================================================
    # DELIVERY DATA ANALYSIS - Thresholds and averages
    # ========================================================================
    # Delivery levels - Used to categorize high delivery activity
    DLV_L1 = 1  # Level 1 threshold: 1.0x average delivery (normal)
    DLV_L2 = 1.5  # Level 2 threshold: 1.5x average delivery (high)
    DLV_L3 = 2  # Level 3 threshold: 2.0x average delivery (very high)
    # Usage: plot.py uses these to color-code candles based on delivery levels
    
    # Averaging parameters - Used for delivery and volume calculations
    DLV_AVG_LEN = 30  # Rolling average period for delivery percentage (days)
    VOL_AVG_LEN = 30  # Rolling average period for trading volume (days)
    # Purpose: Smooth short-term volatility, identify trending delivery levels
    
    # ========================================================================
    # DATA_GET.PY ANALYSIS TOOL - Delivery data analysis parameters
    # ========================================================================
    # data_get.py is a standalone tool for analyzing delivery data patterns
    DGET_AVG_DAYS = 30  # Days used to calculate average volume & delivery (data_get.py)
    DGET_DAYS = 30  # Number of days to return in delivery analysis results
    # Purpose: data_get.py uses these to analyze delivery patterns and trends
    
    # ========================================================================
    # PLOT.PY CHARTING - Visualization and analysis settings
    # ========================================================================
    
    # INTERACTION MODE - How chart lines snap to data
    MAGNET_MODE = True  # True: Snap to nearest High/Low/Close/Open
    # False: Use exact mouse coordinates when drawing
    # Use True for accurate technical line drawing
    
    # PLUGIN CONFIGURATION - Load custom analysis plugins
    PLOT_PLUGINS = {}  # Dict of plugins: {plugin_name: {config_dict}}
    # Format: {"plugin_name": {"param": "value"}}
    # Plugins extend plot.py functionality with custom analysis
    
    # CHART TIME PERIODS - How much data to display
    PLOT_DAYS = 160  # Days to plot on daily charts (default zoom)
    PLOT_WEEKS = 140  # Weeks to plot on weekly charts (default zoom)
    
    # ADVANCED TECHNICAL INDICATORS - Relative Strength analysis
    # MRS = Mansfield Relative Strength (stock vs sector)
    # RS = Dorsey Relative Strength (stock vs market index)
    PLOT_M_RS_LEN_D = 22  # MRS lookback period for daily charts (days)
    PLOT_M_RS_LEN_W = 52  # MRS lookback period for weekly charts (weeks)
    PLOT_RS_INDEX = "nifty 50"  # Market index for RS/MRS calculation
    # Purpose: Compare stock performance relative to broader market
    
    # CHART THEME - Visual appearance and style
    # Available: binance, binancedark, blueskies, brasil, charles, checkers,
    #            classic, default, ibd, kenan, mike, nightclouds, sas,
    #            starsandstripes, tradingview, yahoo
    PLOT_CHART_STYLE = "tradingview"  # Predefined color schemes and themes
    # Popular choices: "tradingview" (modern), "charles" (classic), "dark"
    
    # CHART TYPE - How candles are drawn
    PLOT_CHART_TYPE = "candle"  # Options: "candle" (OHLC), "ohlc" (bars), "line"
    # Candles: Visual + Psychological (most common)
    # OHLC: Traditional bar chart format
    # Line: Close prices only (simplest view)
    
    # ========================================================================
    # CHART COLORS - Technical indicator line colors
    # ========================================================================
    # Reference: https://matplotlib.org/gallery/color/named_colors.html
    
    # Relative Strength indicator colors
    PLOT_RS_COLOR = "darkorange"  # Dorsey RS line color (stock vs index)
    PLOT_M_RS_COLOR = "darkred"  # Mansfield RS line color (stock vs sector)
    
    # DELIVERY MODE CANDLE COLORS - Color candles by delivery strength
    # Used in plot.py delivery visualization mode
    PLOT_DLV_DEFAULT_COLOR = "darkgrey"  # Normal delivery level
    PLOT_DLV_L1_COLOR = "red"  # Level 1: Above 1x average
    PLOT_DLV_L2_COLOR = "darkorange"  # Level 2: Above 1.5x average
    PLOT_DLV_L3_COLOR = "royalblue"  # Level 3: Above 2x average (highest)
    # Purpose: Visual identification of high institutional/investor activity
    
    # TRENDLINE AND REFERENCE LINE COLORS
    # Used when drawing technical lines on charts
    PLOT_AXHLINE_COLOR = "crimson"  # Horizontal line (full width)
    PLOT_HLINE_COLOR = "royalblue"  # Horizontal line (from point onwards)
    PLOT_TLINE_COLOR = "darkturquoise"  # Trend line (connecting two points)
    PLOT_ALINE_COLOR = "mediumseagreen"  # Arbitrary line (custom segment)
    
    # CROSSHAIR CURSOR APPEARANCE
    PLOT_CROSSHAIR_COLOR = "gray"  # Color of the crosshair cursor
    PLOT_CROSSHAIR_LINEWIDTH = 0.5  # Line thickness of crosshair
    PLOT_CROSSHAIR_LINESTYLE = "--"  # Line style: "-", "--", "-.", ":"
    
    # SCREENSHOT AND SAVE SETTINGS
    PLOT_SCREENSHOT_DPI = 150  # DPI for screenshot captures (S key)
    PLOT_SAVE_DPI = 300  # DPI for saved chart exports (--save flag)
    PLOT_SIZE = (14, 9)  # Figure size for saved charts (width, height)
    PLOT_FIGSCALE = 1  # Figure scale multiplier for saved charts
    
    # TECHNICAL INDICATOR CALCULATION PARAMETERS
    PLOT_EMA_ALPHA_DIVISOR = 2  # EMA alpha = 2 / (period + PLOT_EMA_ALPHA_DIVISOR)
    
    # ========================================================================
    # DATA FILES AND WATCHLISTS
    # ========================================================================
    # WATCH contains predefined watchlists accessible in plot.py
    WATCH = {"SECTORS": (DIR / "data/sectors.csv").resolve()}
    # Format: {watchlist_name: path_to_csv_file}
    # CSV should contain one symbol per line
    # Add custom watchlists like:
    #   "MY_STOCKS": (DIR / "data/my_stocks.csv").resolve()
    
    # PRESET contains predefined plot configurations
    # Allows quick loading of custom analysis setups
    PRESET = {}  # Format: {preset_name: settings_dict}
    # Example: {"bearish": {"PLOT_DAYS": 300, "PLOT_RS_COLOR": "red"}}

    def __init__(self) -> None:
        """Initialize configuration with optional user overrides.
        
        PROCESS:
            1. Check if user.json exists in src/funcdefs/ directory
            2. If exists, parse JSON and extract all uppercase keys
            3. Merge user settings with class defaults
            4. Special handling for WATCH dict (merge, don't replace)
        
        USER CONFIGURATION FILE:
            Location: src/funcdefs/user.json
            Format: Standard JSON with uppercase attribute names
            
            Example content:
            {
                "AMIBROKER": true,
                "AMI_UPDATE_DAYS": 500,
                "PLOT_DAYS": 250,
                "PLOT_CHART_STYLE": "charles",
                "WATCH": {
                    "NIFTY_50": "some/path/nifty50.csv"
                }
            }
        
        MERGE BEHAVIOR:
            - Regular attributes: User value replaces default
            - WATCH dict: User values merge with defaults (not replaced)
            - Unknown attributes: Added to config (no validation)
        
        ERRORS:
            - Invalid JSON: Uncaught exception, check user.json syntax
            - Missing keys: Defaults used if key not in user.json
            - Type mismatches: Allowed, use with caution
        """
        user_config = DIR / "funcdefs" / "user.json"

        if user_config.exists():
            dct = json.loads(user_config.read_bytes())

            # Special handling for WATCH dictionary
            # Merge user watchlists with defaults instead of replacing
            if "WATCH" in dct:
                dct["WATCH"].update(self.WATCH)

            # Update all class attributes with user configuration
            self.__dict__.update(dct)

    # ========================================================================
    # VERSION INFORMATION - System versioning (DO NOT EDIT)
    # ========================================================================
    # These values are set at class definition and should NOT be modified
    # unless releasing a new version of EOD2
    VERSION = "9.1.2"  # Current EOD2 version number
    # Semantic versioning: MAJOR.MINOR.PATCH
    # Major: Breaking changes to data format or architecture
    # Minor: New features, backwards compatible
    # Patch: Bug fixes, no feature changes
    
    EXPECTED_DATA_VERSION = 3.2  # Required eod2_data version for compatibility
    # If installed eod2_data version doesn't match, init.py will prompt for update
    # Prevents data corruption from schema mismatches

    def toList(self, filename: str):
        """Load a CSV data file from data directory as list of lines.
        
        PURPOSE:
            Convenient method to load simple text/CSV files from the
            standard data directory (src/data/).
        
        PARAMETERS:
            filename (str): Name of file in src/data/ directory
                           Example: "symbols.csv", "sectors.txt"
        
        RETURNS:
            list[str]: Each line as separate string element
                      Empty lines included
                      Trailing/leading whitespace may be present
        
        USAGE:
            # Load sector data
            sectors = config.toList("sectors.csv")
            # Returns: ["INFOTECH", "FINANCE", "AUTO", ...]
            
            # Load symbol list
            symbols = config.toList("symbols.csv")
            # Returns: ["SBIN", "RELIANCE", "TCS", ...]
        
        NOTE:
            - Splits on newline character only (\\n)
            - Removes leading/trailing whitespace from entire file
            - Individual line whitespace NOT stripped
            - Use list comprehension if line cleaning needed:
              clean = [line.strip() for line in config.toList("file.csv")]
        """
        return (DIR / "data" / filename).read_text().strip().split("\n")

    def __str__(self):
        """Generate formatted string of all configuration settings.
        
        PURPOSE:
            Provides human-readable output of all configuration values,
            useful for debugging and verification.
        
        RETURNS:
            str: Formatted string with footer and all attributes
        
        FORMAT:
            First line: "EOD2 | Version: X.X.X"
            Following lines: "KEY: VALUE" for each attribute
        
        USAGE:
            # Display all settings
            print(config)
            
            # Save settings to file for documentation
            with open("config_dump.txt", "w") as f:
                f.write(str(config))
            
            # Check if a setting is applied
            if "AMIBROKER: True" in str(config):
                print("AmiBroker is enabled")
        
        EXAMPLE OUTPUT:
            EOD2 | Version: 9.1.2
            INIT_HOOK: None
            AMIBROKER: False
            AMI_UPDATE_DAYS: 365
            DLV_L1: 1
            DLV_L2: 1.5
            ... (all other attributes)
            EXPECTED_DATA_VERSION: 3.2
        
        NOTE:
            - Includes dynamically loaded attributes from user.json
            - Order of attributes may vary (dict iteration order)
            - Useful in logging to verify configuration at runtime
        """
        txt = f"EOD2 | Version: {self.VERSION}\n"

        for p in self.__dict__:
            txt += f"{p}: {getattr(self, p)}\n"

        return txt
