"""Offline SQLite candle audit; standard library only, JSON to stdout."""

import argparse
import json
import math
import sqlite3
import sys
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

DURATIONS = {"1h": 3_600_000, "1d": 86_400_000}
REQUIRED = {"symbol", "interval", "open_time_ms", "close_time_ms",
            "open_price", "high_price", "low_price", "close_price", "volume"}


def _integer(value):
    return type(value) is int and value >= 0


def audit_history(db_path, *, as_of_ms=None, sample_limit=20):
    """Audit all stored rows of an offline, checkpointed snapshot.

    Counts are exact, example lists bounded. Coverage counts valid, unique,
    closed candles between each group's first/last valid candle, not an
    externally assumed history window. No data repair or DB writes occur.
    """
    as_of_ms = int(time.time() * 1000) if as_of_ms is None else as_of_ms
    if not _integer(as_of_ms) or not _integer(sample_limit):
        raise ValueError("as_of_ms and sample_limit must be nonnegative integers")
    path = Path(db_path).resolve(strict=True)
    if not path.is_file():
        raise ValueError("database must be a file")
    # Refuse likely live/uncheckpointed databases instead of silently ignoring WAL.
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("use a checkpointed offline snapshot without sidecars")
    groups = {}
    def example(group, kind, value):
        bucket = group["examples"].setdefault(kind, [])
        if len(bucket) < sample_limit:
            bucket.append(value)

    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        columns = {row[1] for row in db.execute("PRAGMA table_info(historical_candles)")}
        if not REQUIRED <= columns:
            raise ValueError("historical_candles missing columns: " +
                             ", ".join(sorted(REQUIRED - columns)))
        rows = db.execute("""SELECT symbol, interval, open_time_ms, close_time_ms,
            open_price, high_price, low_price, close_price, volume
            FROM historical_candles ORDER BY symbol, interval, open_time_ms""")
        for symbol, interval, opened, closed, *values in rows:
            key = (symbol, interval)
            if key not in groups:
                groups[key] = {"symbol": symbol, "interval": interval,
                    "rows": 0, "issues": Counter(), "examples": {},
                    "valid_times": set(), "seen_times": set(), "unclosed_rows": 0}
            group = groups[key]
            group["rows"] += 1
            issues = []
            if not isinstance(symbol, str) or not symbol.strip():
                issues.append("invalid_symbol")
            duration = DURATIONS.get(interval)
            if duration is None:
                issues.append("unsupported_interval")
            times_ok = _integer(opened) and _integer(closed)
            if not times_ok or (duration is not None and
                    (opened % duration or closed != opened + duration - 1)):
                issues.append("invalid_times")
            if _integer(opened):
                if opened in group["seen_times"]:
                    issues.append("duplicate_open_time")
                group["seen_times"].add(opened)
            try:
                op, hi, lo, cl, vol = map(float, values)
                if (not all(math.isfinite(v) for v in (op, hi, lo, cl, vol))
                        or min(op, hi, lo, cl) <= 0 or vol < 0
                        or lo > min(op, cl) or hi < max(op, cl)):
                    issues.append("invalid_ohlcv")
            except (ValueError, TypeError, OverflowError):
                issues.append("invalid_ohlcv")
            if times_ok and closed >= as_of_ms:
                group["unclosed_rows"] += 1
                example(group, "unclosed", opened)
            for issue in issues:
                group["issues"][issue] += 1
                example(group, issue, opened)
            if not issues and closed < as_of_ms:
                group["valid_times"].add(opened)

    output = []
    grids = {}
    for group in groups.values():
        times = sorted(group.pop("valid_times"))
        group.pop("seen_times")
        duration = DURATIONS.get(group["interval"])
        missing = 0
        longest = current = 0
        previous = None
        for opened in times:
            if previous is None or opened == previous + duration:
                current += 1
            else:
                count = (opened - previous) // duration - 1
                missing += count
                example(group, "gaps", {"first_missing_ms": previous + duration,
                                        "last_missing_ms": opened - duration,
                                        "missing_candles": count})
                current = 1
            longest = max(longest, current)
            previous = opened
        expected = (times[-1] - times[0]) // duration + 1 if times else 0
        group.update(valid_unique_closed_candles=len(times),
                     first_open_ms=times[0] if times else None,
                     last_open_ms=times[-1] if times else None,
                     expected_candles_in_observed_span=expected,
                     missing_candles_in_observed_span=missing,
                     coverage_ratio=len(times) / expected if expected else None,
                     longest_contiguous_candles=longest)
        group["issues"] = dict(sorted(group["issues"].items()))
        if duration is not None and isinstance(group["symbol"], str):
            grids.setdefault(group["interval"], []).append((group["symbol"], set(times)))
        output.append(group)
    alignment = []
    for interval, entries in sorted(grids.items()):
        union = set().union(*(grid for _, grid in entries))
        common = set.intersection(*(grid for _, grid in entries))
        alignment.append({"interval": interval, "symbols": [s for s, _ in entries],
                          "union_candles": len(union), "common_candles": len(common),
                          "identical_grids": all(grid == union for _, grid in entries)})
    has_issues = any(g["issues"] or g["missing_candles_in_observed_span"]
                     or not g["valid_unique_closed_candles"] for g in output)
    has_issues = has_issues or not output or any(not a["identical_grids"] for a in alignment)
    return {"report_version": 1, "as_of_ms": as_of_ms, "sample_limit": sample_limit,
            "status": "attention" if has_issues else "ok",
            "total_rows": sum(g["rows"] for g in output),
            "groups": output, "alignment": alignment}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="checkpointed offline SQLite snapshot")
    parser.add_argument("--as-of-ms", type=int)
    parser.add_argument("--sample-limit", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        report = audit_history(args.database, as_of_ms=args.as_of_ms,
                               sample_limit=args.sample_limit)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"Audit failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
