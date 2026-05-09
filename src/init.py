"""
EOD2 - End of Day Data Synchronization Script

This module is the main entry point for the EOD2 system, which automates the
download and processing of NSE (National Stock Exchange) financial data.

FUNCTIONALITY:
    - Downloads daily OHLCV (Open, High, Low, Close, Volume) data for stocks
    - Downloads delivery data showing investor participation
    - Downloads and updates indices data
    - Applies historical adjustments for stock splits and bonus issues
    - Maintains data integrity with rollback mechanisms on errors
    - Syncs data up to the current date while respecting NSE holidays
    - Validates NSE connection, version compatibility, and data versions
    
WORKFLOW:
    1. Validate dependencies (NSE library version, data version)
    2. Parse command-line arguments (--version, --config)
    3. Establish connection to NSE server
    4. Check for special trading sessions and update metadata
    5. Update AmiBroker if configured
    6. Process pending delivery reports from previous sync attempts
    7. Main Loop:
        - Determine next date to process
        - Check for NSE holidays
        - Download equity bhavcopy (price data), indices data, and delivery data
        - Update database with downloaded data
        - Apply adjustments for splits and bonuses
        - Execute user-defined hooks if present
        - Update metadata with last sync date
    
COMMAND-LINE USAGE:
    python init.py                    # Run normal data sync
    python init.py --version          # Display version information
    python init.py --config           # Display current configuration
    
CONFIGURATION:
    Settings are loaded from funcdefs.config which includes:
    - AMIBROKER: Enable/disable AmiBroker integration
    - EXPECTED_DATA_VERSION: Required eod2_data version
    - VERSION: EOD2 version number
    
ERROR HANDLING:
    - Network errors: Logs warning and exits gracefully
    - Data sync errors: Rolls back changes to maintain integrity
    - Missing reports: Tracks pending dates for retry in next sync
    - Holiday conflicts: Skips processing, updates metadata
    
DEPENDENCIES:
    - nse: NSE data fetching library (required version >= 1.2.4)
    - httpx: HTTP client for network requests
    - funcdefs: Project utilities and configuration
"""

import logging
import sys
from argparse import ArgumentParser

from httpx import ConnectError
from nse import NSE

from funcdefs import funcdefs
from funcdefs.utils import writeJson


logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)

# ============================================================================
# DEPENDENCY AND VERSION VALIDATION
# ============================================================================
# Ensure the NSE library version meets minimum requirements
if not funcdefs.is_version_compatible(NSE.__version__, major=1, minor=2, patch=4):
    print(NSE.__version__)
    logger.warning("Require NSE version 1.2.4. Run `pip install -U nse`")
    exit()

# Validate eod2_data version compatibility
# Prompts user to update data if version mismatch detected
data_version = funcdefs.meta.get("data-version", None)

if data_version != funcdefs.config.EXPECTED_DATA_VERSION:
    if (funcdefs.DIR.parent / ".git").exists():
        update_url = "https://github.com/BennyThadikaran/eod2/wiki/Installation#updating-the-git-repo\n"

        exit(
            f"Warning: NSE_eod folder needs an update.\n\nFollow instructions at below link to update\n{update_url}"
        )
    else:
        exit("Warning: NSE_eod folder needs an update. Run `setup_data.py` to update")

# ============================================================================
# EXCEPTION HANDLING SETUP
# ============================================================================
# Register custom exception handler to log unhandled exceptions with context
# This ensures all errors are properly logged for debugging
sys.excepthook = funcdefs.log_unhandled_exception

# ============================================================================
# COMMAND-LINE ARGUMENT PARSING
# ============================================================================
# Set up argument parser for --version and --config flags
parser = ArgumentParser(prog="init.py")

group = parser.add_mutually_exclusive_group()

group.add_argument(
    "-v", "--version", action="store_true", help="Print the current version."
)

group.add_argument(
    "-c", "--config", action="store_true", help="Print the current config."
)

args = parser.parse_args()

# Handle --version flag: Display version information and exit
if args.version:
    exit(
        f"EOD2 init.py: v{funcdefs.config.VERSION} | eod2_data: v{funcdefs.meta.get('data-version', None)}"
    )

# Handle --config flag: Display current configuration and exit
if args.config:
    exit(str(funcdefs.config))

# ============================================================================
# NSE SERVER CONNECTION
# ============================================================================
# Establish connection to NSE server for data fetching
# Catches network-related errors and exits gracefully
try:
    nse = NSE(funcdefs.DIR, server=True)
except (TimeoutError, ConnectionError, ConnectError) as e:
    logger.warning(f"Network error connecting to NSE - Please try again later. - {e!r}")
    exit()

# ============================================================================
# INITIALIZATION CHECKS AND UPDATES
# ============================================================================
# Check for special trading sessions (e.g., post-market trading)
# and update metadata if changes detected
if funcdefs.check_special_sessions(nse):
    writeJson(funcdefs.META_FILE, funcdefs.meta)

# Update AmiBroker database if configured and data is outdated
if funcdefs.config.AMIBROKER and not funcdefs.isAmiBrokerFolderUpdated():
    funcdefs.updateAmiBrokerRecords(nse)

# ============================================================================
# PENDING DELIVERY REPORTS PROCESSING
# ============================================================================
# Initialize pending delivery dates list if not present
# These are dates where delivery data was unavailable in previous syncs
if "DLV_PENDING_DATES" not in funcdefs.meta:
    funcdefs.meta["DLV_PENDING_DATES"] = []

# Retry processing delivery reports from previous failed attempts
if len(funcdefs.meta["DLV_PENDING_DATES"]):
    pendingList = funcdefs.meta["DLV_PENDING_DATES"].copy()

    logger.info("Updating pending delivery reports.")

    for dateStr in pendingList:
        if funcdefs.updatePendingDeliveryData(nse, dateStr):
            writeJson(funcdefs.META_FILE, funcdefs.meta)

# ============================================================================
# MAIN DATA SYNCHRONIZATION LOOP
# ============================================================================
# Infinite loop to process data for each trading date
# Continues until end of data range is reached
while True:
    # Get next trading date to process; exit if no more dates available
    if not funcdefs.dates.nextDate():
        nse.exit()
        # Run trading strategies on the freshly synced data
        try:
            from strategy_runner_V2 import run as run_strategies
            run_strategies(
                folder=str(funcdefs.DIR / "daily"),
                export=str(funcdefs.DIR.parent / "results.csv"),
            )
        except Exception as e:
            logger.warning(f"Strategy runner failed: {e}")
        exit()

    # Skip processing if current date is a market holiday
    # Update metadata and continue to next iteration
    if funcdefs.checkForHolidays(nse):
        funcdefs.meta["lastUpdate"] = funcdefs.dates.lastUpdate = funcdefs.dates.dt
        writeJson(funcdefs.META_FILE, funcdefs.meta)
        continue

    # Confirm NSE corporate actions file (splits, bonuses, etc.) is current
    funcdefs.validateNseActionsFile(nse)

    # ========================================================================
    # REPORT STATUS CHECK FOR CURRENT DATE
    # ========================================================================
    # If processing today's data, check if NSE reports are ready
    # Some reports may be delayed and we need to handle this appropriately
    logger.info("Downloading Files")

    report_status = None

    if funcdefs.dates.dt.date() == funcdefs.dates.today.date():
        report_status = funcdefs.check_reports_update_status(nse)

        # Define required reports and corresponding messages if unavailable
        required_reports = {
            "CM-UDIFF-BHAVCOPY-CSV": "Equity Bhavcopy not yet updated.",
            "INDEX-SNAPSHOT": "Indices report not yet updated.",
            "CM-BHAVDATA-FULL": "Delivery Report Unavailable. Will retry in subsequent sync",
        }

        for key, msg in required_reports.items():
            if not report_status.get(key):
                logger.warning(msg)

                # Exit for critical reports (equity and indices)
                # Delivery data is non-critical and can be retried
                if key != "CM-BHAVDATA-FULL":
                    nse.exit()
                    exit()

    # ========================================================================
    # DOWNLOAD EQUITY AND INDICES DATA
    # ========================================================================
    # Download equity bhavcopy (daily price data) and indices data
    # These are essential files required for data sync
    try:
        # NSE bhav copy - Contains daily trading data for all stocks
        BHAV_FILE = nse.equityBhavcopy(funcdefs.dates.dt)

        # Index file - Contains daily data for all stock indices
        INDEX_FILE = nse.indicesBhavcopy(funcdefs.dates.dt)
    except (RuntimeError, Exception) as e:
        # Handle download errors with special logic for Saturdays
        # Markets are closed on Saturdays, so errors are expected for past dates
        if funcdefs.dates.dt.weekday() == 5:
            if funcdefs.dates.dt != funcdefs.dates.today:
                logger.info(f"{funcdefs.dates.dt:%a, %d %b %Y}: Market Closed\n{'-' * 52}")

                # Skip Saturdays when syncing past dates - data won't be available
                continue

            # If NSE is closed and report unavailable, inform user
            logger.info(
                "Market is closed on Saturdays. If open, check availability on NSE"
            )

        # Exit on download errors for regular trading days
        nse.exit()
        logger.warning(e)
        exit()

    # ========================================================================
    # DOWNLOAD DELIVERY DATA
    # ========================================================================
    # Attempt to download delivery data (shows investor participation)
    # If unavailable, mark date for retry in next sync instead of failing
    if report_status is None or report_status["CM-BHAVDATA-FULL"]:
        try:
            # NSE delivery - Contains delivery/holding data for stocks
            DELIVERY_FILE = nse.deliveryBhavcopy(funcdefs.dates.dt)
        except (RuntimeError, Exception):
            # Delivery data is optional; track for retry instead of failing
            funcdefs.meta["DLV_PENDING_DATES"].append(funcdefs.dates.dt.isoformat())
            DELIVERY_FILE = None
            logger.warning("Delivery Report Unavailable. Will retry in subsequent sync")

    else:
        # Delivery report not available; mark for retry
        DELIVERY_FILE = None
        funcdefs.meta["DLV_PENDING_DATES"].append(funcdefs.dates.dt.isoformat())

    # ========================================================================
    # DATABASE UPDATE - PRICE AND INDICES DATA
    # ========================================================================
    # Update database with downloaded data; rollback on error to maintain integrity
    try:
        # Update equity EOD data: Parse and insert price data into database
        funcdefs.updateNseEOD(BHAV_FILE, DELIVERY_FILE)

        # Update index EOD data: Process and insert indices data
        funcdefs.updateIndexEOD(INDEX_FILE)
    except Exception as e:
        # On error: rollback changes, log exception, clean up temp files, and exit
        logger.exception("Error during data sync.", exc_info=e)
        funcdefs.rollback(funcdefs.DAILY_FOLDER)
        funcdefs.cleanup((BHAV_FILE, DELIVERY_FILE, INDEX_FILE))

        funcdefs.meta["lastUpdate"] = funcdefs.dates.lastUpdate
        writeJson(funcdefs.META_FILE, funcdefs.meta)
        nse.exit()
        exit()

    # ========================================================================
    # CORPORATE ACTIONS ADJUSTMENT
    # ========================================================================
    # Apply historical adjustments for stock splits and bonus issues
    # This ensures historical data remains accurate after corporate actions
    try:
        funcdefs.adjustNseStocks()
    except Exception as e:
        # On error: rollback all adjustments, log exception, and exit
        # Adjustments are critical for data integrity
        logger.exception(
            "Error while making adjustments.\nAll adjustments have been discarded.",
            exc_info=e,
        )

        funcdefs.rollback(funcdefs.DAILY_FOLDER)
        funcdefs.cleanup((BHAV_FILE, DELIVERY_FILE, INDEX_FILE))

        funcdefs.meta["lastUpdate"] = funcdefs.dates.lastUpdate
        writeJson(funcdefs.META_FILE, funcdefs.meta)
        nse.exit()
        exit()

    # ========================================================================
    # POST-PROCESSING HOOKS
    # ========================================================================
    # Execute user-defined hooks after successful data sync
    # Allows custom operations like notifications, additional processing, etc.
    if funcdefs.hook and hasattr(funcdefs.hook, "on_complete"):
        funcdefs.hook.on_complete()

    # ========================================================================
    # CLEANUP AND FINALIZATION
    # ========================================================================
    # Remove temporary downloaded files from filesystem
    funcdefs.cleanup((BHAV_FILE, DELIVERY_FILE, INDEX_FILE))

    # Clean outdated files when syncing to current date
    if funcdefs.dates.today == funcdefs.dates.dt:
        funcdefs.cleanOutDated()

    # Update metadata with successful sync timestamp
    funcdefs.meta["lastUpdate"] = funcdefs.dates.lastUpdate = funcdefs.dates.dt
    writeJson(funcdefs.META_FILE, funcdefs.meta)

    # Log completion message with separator for readability
    logger.info(f"{funcdefs.dates.dt:%d %b %Y}: Done\n{'-' * 52}")
