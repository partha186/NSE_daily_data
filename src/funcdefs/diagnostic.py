"""Data integrity diagnostic tool for EOD2 stock market data.

This module performs comprehensive validation of OHLCV (Open, High, Low, Close, Volume)
and delivery data stored in CSV files within the eod2_data/daily directory.

Checks performed:
- Duplicate date entries in the index
- Datatype consistency (numeric columns should be float64 or int64)
- Datetime index format (should be datetime64[ns])
- Column count consistency (9 columns for stocks, 10 for indices)
- Missing values (NaN) in critical OHLCV columns
- File parsing errors (corrupted or malformed CSV)

Run directly::

    python -m funcdefs.diagnostic
    python -m funcdefs.diagnostic --threshold 20
    python -m funcdefs.diagnostic --dir /path/to/daily

Configuration:
    --threshold : Maximum errors per category before stopping (default 5).
    --dir       : Override the daily CSV directory.
"""

import argparse
import pandas as pd
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

DIR = Path(__file__).parents[1]

# ---------------------------------------------------------------------------
# Error message templates
# ---------------------------------------------------------------------------
_DTYPE_TMPL  = "{}: Column type mismatch in '{}'. Expected float64/int64, got {}"
_COL_TMPL    = "{}: Column count mismatch. Expected {} got {}"
_INDEX_TMPL  = "{}: Index type mismatch. Expected datetime64[ns], got {}"
_NAN_TMPL    = "{}: Column '{}' has NaN values"


@dataclass
class DiagnosticResult:
    """Holds all errors found during a diagnostic run."""
    duplicates:     List[str] = field(default_factory=list)
    type_mismatches: List[str] = field(default_factory=list)
    index_mismatches: List[str] = field(default_factory=list)
    exceptions:     List[str] = field(default_factory=list)
    col_mismatches: List[str] = field(default_factory=list)
    has_nans:       List[str] = field(default_factory=list)
    total_scanned:  int = 0

    def max_error_count(self) -> int:
        return max(
            len(self.duplicates),
            len(self.type_mismatches),
            len(self.index_mismatches),
            len(self.exceptions),
            len(self.col_mismatches),
            len(self.has_nans),
        )

    def total_errors(self) -> int:
        return (
            len(self.duplicates)
            + len(self.type_mismatches)
            + len(self.index_mismatches)
            + len(self.exceptions)
            + len(self.col_mismatches)
            + len(self.has_nans)
        )

    def print_report(self) -> None:
        """Print a formatted diagnostic report to stdout."""
        print(f"\nScanned {self.total_scanned} file(s).")

        if self.total_errors() == 0:
            print("No errors found.\n")
            return

        print(f"Total issues: {self.total_errors()}\n")

        sections = [
            ("Duplicate entries",        self.duplicates),
            ("Datatype mismatches",       self.type_mismatches),
            ("Index type mismatches",     self.index_mismatches),
            ("File / parse exceptions",   self.exceptions),
            ("Column count mismatches",   self.col_mismatches),
            ("Columns with NaN values",   self.has_nans),
        ]
        for title, items in sections:
            if items:
                print(f"--- {title} ({len(items)}) ---")
                print("\n".join(items))
                print()


def run(daily_dir: Path, threshold: int = 5) -> DiagnosticResult:
    """Scan all CSV files in *daily_dir* and return a DiagnosticResult.

    Args:
        daily_dir: Path to directory containing daily OHLCV CSV files.
        threshold: Stop after any single error category reaches this count.

    Returns:
        DiagnosticResult populated with any errors found.
    """
    result = DiagnosticResult()

    for file in daily_dir.iterdir():
        if not file.suffix.lower() == ".csv":
            continue

        # Index files have a space in their name (e.g. "nifty 50.csv")
        is_index_file = " " in file.name

        try:
            df = pd.read_csv(file, index_col="Date", parse_dates=True)
        except Exception as exc:
            result.exceptions.append(f"{file.name.upper()}: {exc!r}")
            result.total_scanned += 1
            if result.max_error_count() >= threshold:
                break
            continue

        result.total_scanned += 1

        if df.shape[0] < 1:
            print(f"WARN: daily/{file.name} is empty — skipped.")
            continue

        fname = file.name.upper().ljust(15)

        # --- Index type ---
        if df.index.dtype != "datetime64[ns]":
            result.index_mismatches.append(
                _INDEX_TMPL.format(fname, df.index.dtype)
            )

        # --- Column count ---
        expected_cols = 10 if is_index_file else 9
        if len(df.columns) != expected_cols:
            result.col_mismatches.append(
                _COL_TMPL.format(fname, expected_cols, len(df.columns))
            )

        # --- Dtypes ---
        for col in df.columns:
            if col == "Series":
                continue
            if df[col].dtype not in ("float64", "int64"):
                result.type_mismatches.append(
                    _DTYPE_TMPL.format(fname, col, df[col].dtype)
                )

        # --- NaN check ---
        ohlcv_cols = ("Open", "High", "Low", "Close", "Volume")
        for col in ohlcv_cols:
            if col not in df.columns:
                continue
            # For index files only Close is expected to be fully populated
            if is_index_file and col != "Close":
                continue
            if df[col].hasnans:
                result.has_nans.append(_NAN_TMPL.format(fname, col))

        # --- Duplicates ---
        if df.index.has_duplicates:
            result.duplicates.append(file.name.upper())

        if result.max_error_count() >= threshold:
            print(f"WARN: Threshold of {threshold} reached — stopping early.")
            break

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose data integrity of EOD2 daily CSV files."
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=5,
        metavar="N",
        help="Stop after any error category reaches N errors (default: 5).",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DIR / "NSE_eod_data" / "daily",
        metavar="PATH",
        help="Path to daily CSV directory (default: src/NSE_eod_data/daily).",
    )
    args = parser.parse_args()

    if not args.dir.exists():
        parser.error(f"Directory not found: {args.dir}")

    result = run(args.dir, threshold=args.threshold)
    result.print_report()


if __name__ == "__main__":
    main()
