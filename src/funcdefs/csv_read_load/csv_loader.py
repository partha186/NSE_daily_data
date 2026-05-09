import io
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List

import pandas as pd


def csv_loader(
    file_path: Path,
    period: int = 160,
    end_date: Optional[datetime] = None,
    date_format: Optional[str] = None,
    use_columns: Optional[List[str]] = None,
    chunk_size: int = 1024 * 6,
) -> pd.DataFrame:
    """
    Load a CSV file with timeseries data in chunks from the end.

    Could return an empty DataFrame, if no data was found.
    Use ``df.empty`` to check if the DataFrame is empty before further processing.

    :param file_path: The path to the CSV file to be loaded.
    :type file_path: pathlib.Path

    :param period: Number of lines/candles to return. The default is 160.
    :type period: int

    :param end_date: Load N lines up to this date.
        If None, will load the last N lines from the file.
        If the date is provided, load the last N lines from this date.
    :type end_date: Optional[datetime]

    :param date_format: Custom date format in case pandas is unable to parse the date column.
    :type date_format: Optional[str]

    :param use_columns: Default None. List of column names to load from the CSV file. If None, all columns are loaded.
    :type use_columns: Optional[List[str]]

    :param chunk_size: The size of data chunks loaded into memory.
        The default is 6144 bytes (6 KB).
    :type chunk_size: int

    :return: A DataFrame containing the loaded timeseries data.
    :rtype: pd.DataFrame

    :raise IndexError: if ``end_date`` is provided but not within the boundary of the data.
    """

    def get_date(start: int, chunk: bytes) -> datetime:
        # Given the start point date column ends with ','
        end = chunk.find(b",", start)
        date_str = chunk[start:end].decode()
        # empty string returns NaT
        dt = pd.to_datetime(date_str, format=date_format)
        if pd.isna(dt):
            raise ValueError("Not a Date")
        return dt

    def binary_search_pos(f, target_date, first_row_pos, size) -> int:
        """Binary search for the file position where dates cross target_date.

        Returns the largest file position whose row date is <= target_date,
        reducing the backward scan from O(n) to O(log n) seeks.
        """
        lo, hi = first_row_pos, size
        while hi - lo > chunk_size:
            mid = (lo + hi) // 2
            f.seek(mid)
            f.readline()  # align to the next full line boundary
            line = f.readline()
            if not line:
                hi = mid
                continue
            try:
                dt = get_date(0, line)
                if dt <= target_date:
                    lo = mid
                else:
                    hi = mid
            except (ValueError, IndexError):
                hi = mid
        return lo

    size = os.path.getsize(file_path)

    if size <= max(1024 * 19, chunk_size):
        df = pd.read_csv(
            file_path,
            index_col=[0],
            parse_dates=[0],
            date_format=date_format,
            usecols=use_columns,  # plain list, pd.Index wrapper is unnecessary
        )

        if end_date:
            dt = df.index[0]

            if isinstance(dt, pd.Timestamp) and dt.tzinfo:
                end_date = end_date.replace(tzinfo=dt.tzinfo)

            if not df.empty and end_date < dt:
                raise IndexError("Date out of bounds of current DataFrame")

            return df.loc[:end_date].iloc[-period:]

        return df.iloc[-period:]

    chunks_read = []
    prev_chunk_start_line = None

    with file_path.open(mode="rb") as f:
        columns = f.readline()
        first_row_pos = f.tell()

        if end_date:
            dt = get_date(0, f.readline())

            if dt.tzinfo:
                end_date = end_date.replace(tzinfo=dt.tzinfo)

            # Jump to the vicinity of end_date instead of scanning from EOF
            curr_pos = min(
                binary_search_pos(f, end_date, first_row_pos, size) + chunk_size,
                size,
            )
        else:
            curr_pos = size

        lines_read = 0

        while curr_pos >= first_row_pos:
            read_size = min(chunk_size, curr_pos - first_row_pos)

            if read_size == 0:
                break

            f.seek(curr_pos - read_size)
            chunk = f.read(read_size)

            if end_date:
                # First line in a chunk may not be complete; skip it and parse the next
                start = chunk.find(b"\n")

                try:
                    current_dt = get_date(start + 1, chunk)
                except ValueError:
                    chunks_read.append(chunk)
                    curr_pos -= read_size
                    continue

                if current_dt <= end_date:
                    # Sentinel of 1 for the first matching chunk: end_date may sit near
                    # the chunk's start, so most lines in it are after end_date.
                    # Counting all would exhaust the period budget too early.
                    # Subsequent chunks are fully before end_date, so count exactly.
                    lines_read += 1 if lines_read == 0 else chunk.count(b"\n")

                    if prev_chunk_start_line:
                        chunks_read.append(prev_chunk_start_line)
                        prev_chunk_start_line = None

                    if lines_read >= period:
                        chunks_read.append(chunk[start + 1:])
                        break

                    chunks_read.append(chunk)
                else:
                    prev_chunk_start_line = chunk[:start]

            else:
                # Exact newline count per chunk — no estimation needed
                lines_read += chunk.count(b"\n")

                if lines_read >= period:
                    start = chunk.find(b"\n") + 1
                    chunks_read.append(chunk[start:])
                    break

                chunks_read.append(chunk)

            curr_pos -= read_size

        if end_date and not chunks_read:
            raise IndexError("Date out of bounds of current DataFrame")

        chunks_read.append(columns)
        buffer = io.BytesIO(b"".join(chunks_read[::-1]))

    df = pd.read_csv(
        buffer,
        parse_dates=[0],
        index_col=[0],
        date_format=date_format,
        usecols=use_columns,  # plain list, pd.Index wrapper is unnecessary
    )

    if end_date:
        return df.loc[df.index <= end_date].iloc[-period:]
    else:
        return df.iloc[-period:]
