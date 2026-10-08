"""Causal OHLCV features for closed Binance candles; no IO or network."""

import math
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone

DURATIONS = {"1h": 3_600_000, "1d": 86_400_000}
FEATURES = ("sma", "ema", "rsi", "macd", "macd_signal", "macd_hist", "atr", "features_ready")


def _ema(values, period):
    result = [None] * len(values)
    if len(values) >= period:
        previous = sum(v / period for v in values[:period])
        result[period-1] = previous
        alpha = 2 / (period + 1)
        for i in range(period, len(values)):
            previous = alpha * values[i] + (1-alpha) * previous
            result[i] = previous
    return result


def add_indicators(records, *, as_of_ms, interval="1h", sma_period=20,
                   ema_period=20, rsi_period=14, atr_period=14,
                   macd_fast=12, macd_slow=26, macd_signal=9):
    """Return copied date/tic sorted rows, with None during feature warmup.

    Require closed, contiguous candles and identical symbol grids. A row's
    features use that row and earlier rows of the same symbol only. Input
    features with reserved output names are rejected to prevent overwriting.
    as_of_ms is explicit UTC epoch milliseconds (use snapshot server_time_ms).
    """
    periods = (sma_period, ema_period, rsi_period, atr_period, macd_fast, macd_slow, macd_signal)
    if any(type(p) is not int or not 1 <= p <= 10000 for p in periods):
        raise ValueError("periods must be integers in 1..10000")
    if macd_fast >= macd_slow:
        raise ValueError("macd_fast must be less than macd_slow")
    if interval not in DURATIONS or type(as_of_ms) is not int or as_of_ms < 0:
        raise ValueError("interval must be 1h/1d and as_of_ms a nonnegative integer")
    duration = DURATIONS[interval]
    grouped = {}
    for row in records:
        if not isinstance(row, Mapping) or not {"date", "tic", "open", "high", "low", "close", "volume"} <= row.keys():
            raise ValueError("record must contain date/tic/OHLCV")
        if set(FEATURES) & row.keys():
            raise ValueError("record already contains reserved feature fields")
        symbol = row["tic"]
        if not isinstance(symbol, str) or not symbol.strip() or not isinstance(row["date"], str):
            raise ValueError("invalid symbol/date")
        try:
            stamp = datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if stamp.strftime("%Y-%m-%d %H:%M:%S") != row["date"]:
                raise ValueError("noncanonical date")
            opened = int(stamp.timestamp()) * 1000
            op, hi, lo, cl, vol = (float(row[k]) for k in ("open", "high", "low", "close", "volume"))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("invalid date/OHLCV") from exc
        if opened < 0 or opened % duration or opened + duration > as_of_ms:
            raise ValueError("unaligned or unclosed candle")
        if (not all(math.isfinite(v) for v in (op, hi, lo, cl, vol))
                or min(op, hi, lo, cl) <= 0 or vol < 0
                or lo > min(op, cl) or hi < max(op, cl)):
            raise ValueError("invalid OHLCV")
        grouped.setdefault(symbol, []).append((opened, deepcopy(dict(row)), hi, lo, cl))
    grids = []
    output = []
    for symbol in sorted(grouped):
        rows = sorted(grouped[symbol], key=lambda r: r[0])
        times = [r[0] for r in rows]
        if any(b != a + duration for a, b in zip(times, times[1:])):
            raise ValueError("duplicate or missing candle")
        grids.append(times)
        closes = [r[4] for r in rows]
        ema = _ema(closes, ema_period)
        fast, slow = _ema(closes, macd_fast), _ema(closes, macd_slow)
        macd = [f-s if s is not None else None for f, s in zip(fast, slow)]
        signal = [None] * (macd_slow-1) + _ema(macd[macd_slow-1:], macd_signal)
        gains, losses, tr = [], [], []
        avg_gain = avg_loss = atr = None
        for i, (_, row, high, low, close) in enumerate(rows):
            sma = sum(v / sma_period for v in closes[i-sma_period+1:i+1]) if i+1 >= sma_period else None
            tr.append(max(high-low, abs(high-closes[i-1]), abs(low-closes[i-1])) if i else high-low)
            if i+1 == atr_period:
                atr = sum(v / atr_period for v in tr)
            elif i+1 > atr_period:
                atr = atr * ((atr_period-1)/atr_period) + tr[-1]/atr_period
            rsi = None
            if i:
                delta = close - closes[i-1]
                gains.append(max(delta, 0.))
                losses.append(max(-delta, 0.))
                if i == rsi_period:
                    avg_gain = sum(v/rsi_period for v in gains)
                    avg_loss = sum(v/rsi_period for v in losses)
                elif i > rsi_period:
                    avg_gain = avg_gain*((rsi_period-1)/rsi_period) + gains[-1]/rsi_period
                    avg_loss = avg_loss*((rsi_period-1)/rsi_period) + losses[-1]/rsi_period
                if avg_gain is not None:
                    rsi = (50. if avg_gain == avg_loss == 0 else 100. if avg_loss == 0
                           else 100 * (avg_gain / max(avg_gain, avg_loss)) /
                           (avg_gain / max(avg_gain, avg_loss) + avg_loss / max(avg_gain, avg_loss)))
            sig = signal[i] if i < len(signal) else None
            values = (sma, ema[i], rsi, macd[i], sig,
                      macd[i]-sig if sig is not None else None, atr)
            if any(v is not None and not math.isfinite(v) for v in values):
                raise ValueError("indicator numeric overflow")
            row.update(zip(FEATURES[:-1], values))
            row["features_ready"] = all(v is not None for v in values)
            output.append(row)
    if grids and any(grid != grids[0] for grid in grids[1:]):
        raise ValueError("symbols must share identical time grids")
    return sorted(output, key=lambda r: (r["date"], r["tic"]))
