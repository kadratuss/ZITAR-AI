"""Deterministic time splits for offline FinRL records; no IO or network."""

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime


def _date(value):
    if not isinstance(value, str):
        raise ValueError("date must be UTC text YYYY-MM-DD HH:MM:SS")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError("date must be UTC text YYYY-MM-DD HH:MM:SS") from exc
    if parsed.strftime("%Y-%m-%d %H:%M:%S") != value:
        raise ValueError("date must use canonical UTC format")
    return parsed


def split_records(records, *, validation_start, test_start,
                  start=None, end=None, label_horizon_steps=0, embargo_steps=0):
    """Split FinRL records by explicit UTC boundaries, never shuffled.

    Raw windows: [start, validation_start), [validation_start, test_start),
    [test_start, end). Remove the last label_horizon_steps timestamps from
    train/validation and the first embargo_steps from validation/test. Steps
    count distinct observed timestamps, NOT elapsed candle intervals.
    Require a nonempty rectangular symbol grid and a nonempty retained result
    in each partition. Extra fields are copied, never fitted or recomputed.
    """
    for value in (label_horizon_steps, embargo_steps):
        if type(value) is not int or value < 0:
            raise ValueError("horizon and embargo must be nonnegative integers")
    v, t = _date(validation_start), _date(test_start)
    s, e = _date(start) if start is not None else None, _date(end) if end is not None else None
    if v >= t or (s is not None and s >= v) or (e is not None and e <= t):
        raise ValueError("boundaries must satisfy start < validation_start < test_start < end")
    by_date = {}
    for record in records:
        if not isinstance(record, Mapping) or "date" not in record or "tic" not in record:
            raise ValueError("each record must contain date and tic")
        stamp = _date(record["date"])
        symbol = record["tic"]
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("tic must be a nonempty string")
        bucket = by_date.setdefault(stamp, {})
        if symbol in bucket:
            raise ValueError(f"duplicate date/tic: {record['date']} {symbol}")
        bucket[symbol] = record
    dates = sorted(d for d in by_date if (s is None or d >= s) and (e is None or d < e))
    if not dates:
        raise ValueError("selected window is empty")
    symbols = sorted(by_date[dates[0]])
    if any(set(by_date[d]) != set(symbols) for d in dates):
        raise ValueError("selected timestamps must share the same symbol grid")
    raw = {"train": [d for d in dates if d < v],
           "validation": [d for d in dates if v <= d < t],
           "test": [d for d in dates if d >= t]}
    selected, excluded, metadata = {}, [], {}
    for name, window in raw.items():
        head = embargo_steps if name != "train" else 0
        tail = label_horizon_steps if name != "test" else 0
        stop = len(window) - tail
        if stop <= head:
            raise ValueError(f"{name} has no retained timestamps after purge/embargo")
        kept = window[head:stop]
        selected[name] = [deepcopy(by_date[d][symbol]) for d in kept for symbol in symbols]
        for index, d in enumerate(window):
            reason = "embargo" if index < head else "label_horizon_purge" if index >= stop else None
            if reason:
                excluded.extend({"date": by_date[d][symbol]["date"], "tic": symbol,
                                 "partition": name, "reason": reason} for symbol in symbols)
        metadata[name] = {"raw_timestamps": len(window), "retained_timestamps": len(kept),
                          "retained_rows": len(selected[name]),
                          "first_date": selected[name][0]["date"],
                          "last_date": selected[name][-1]["date"]}
    selected["excluded"] = excluded
    selected["metadata"] = {"symbols": symbols, "partitions": metadata,
                            "validation_start": validation_start, "test_start": test_start,
                            "start": start, "end": end,
                            "label_horizon_steps": label_horizon_steps,
                            "embargo_steps": embargo_steps}
    return selected
