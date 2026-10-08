"""Offline historical_candles reader. No exchange or application imports."""

import math
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

COLUMNS = ("date", "tic", "open", "high", "low", "close", "volume", "day")
DURATIONS = {"1h": 3_600_000, "1d": 86_400_000}


def _milliseconds(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer in milliseconds")
    return value


def read_finrl_records(db_path, symbols, interval="1h", *, start_ms=0,
                       end_ms=None, as_of_ms=None):
    """Return date/tic ordered OHLCV records from [start_ms, end_ms).

    date is the UTC candle OPEN timestamp (ISO text with time preserved).
    Only candles closed strictly before as_of_ms are included. All requested
    symbols must have the same contiguous time grid; no filling or resampling.
    Supports the collector's fixed 1h/1d intervals. Empty windows return [].
    """
    if interval not in DURATIONS:
        raise ValueError("interval must be 1h or 1d")
    if isinstance(symbols, (str, bytes)):
        raise ValueError("symbols must be a nonempty sequence of strings")
    symbols = tuple(symbols)
    if not symbols or any(not isinstance(s, str) or not s.strip() for s in symbols):
        raise ValueError("symbols must be a nonempty sequence of strings")
    if len(set(symbols)) != len(symbols):
        raise ValueError("duplicate symbols")
    start_ms = _milliseconds(start_ms, "start_ms")
    as_of_ms = _milliseconds(int(time.time() * 1000) if as_of_ms is None
                             else as_of_ms, "as_of_ms")
    if end_ms is not None:
        _milliseconds(end_ms, "end_ms")
        if end_ms <= start_ms:
            raise ValueError("end_ms must exceed start_ms")
    path = Path(db_path).resolve(strict=True)
    duration = DURATIONS[interval]
    records = []
    grids = {}
    # immutable=1 also prevents SQLite from creating WAL/SHM sidecars.
    # This requires an offline, checkpointed snapshot, not a live WAL database.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1",
                                 uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        for symbol in sorted(symbols):
            raw = db.execute("""
                SELECT open_time_ms, close_time_ms, open_price, high_price,
                       low_price, close_price, volume
                FROM historical_candles
                WHERE symbol=? AND interval=? AND open_time_ms>=?
                  AND (? IS NULL OR open_time_ms<?)
                ORDER BY open_time_ms
            """, (symbol, interval, start_ms, end_ms, end_ms))
            grid = []
            for opened, closed, *values in raw:
                try:
                    _milliseconds(opened, "open_time_ms")
                    _milliseconds(closed, "close_time_ms")
                    if opened % duration or closed != opened + duration - 1:
                        raise ValueError("invalid candle times")
                    if closed >= as_of_ms:
                        continue
                    op, hi, lo, cl, vol = map(float, values)
                    if (not all(math.isfinite(v) for v in (op, hi, lo, cl, vol))
                            or min(op, hi, lo, cl) <= 0 or vol < 0
                            or lo > min(op, cl) or hi < max(op, cl)):
                        raise ValueError("invalid OHLCV")
                    if grid and opened != grid[-1] + duration:
                        raise ValueError("duplicate or missing candle")
                    stamp = datetime.fromtimestamp(opened / 1000, timezone.utc)
                    records.append(dict(zip(COLUMNS, (
                        stamp.strftime("%Y-%m-%d %H:%M:%S"), symbol,
                        op, hi, lo, cl, vol, stamp.weekday()))))
                    grid.append(opened)
                except (ValueError, TypeError, OverflowError) as exc:
                    raise ValueError(f"{symbol} candle {opened}: {exc}") from exc
            grids[symbol] = grid
    if any(grid != next(iter(grids.values())) for grid in grids.values()):
        raise ValueError("requested symbols have different time grids")
    return sorted(records, key=lambda row: (row["date"], row["tic"]))


def load_finrl_dataframe(db_path, symbols, interval="1h", **kwargs):
    """Return a pandas frame with FinRL's shared date index; pandas is optional.

    No FinRL installation, credentials, downloads, or feature engineering needed.
    """
    import pandas as pd

    frame = pd.DataFrame(read_finrl_records(db_path, symbols, interval, **kwargs),
                         columns=COLUMNS)
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = frame[column].astype(float)
    frame["day"] = frame["day"].astype("int64")
    frame.index = pd.Index(pd.factorize(frame["date"])[0])
    return frame
