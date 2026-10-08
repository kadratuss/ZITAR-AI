"""Opt-in Binance global USDT public candle snapshots; no database or orders."""

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE_URL = "https://data-api.binance.vision"
DURATIONS = {"1h": 3_600_000, "1d": 86_400_000}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get_json(path, params=None):
    if path not in ("/api/v3/time", "/api/v3/klines"):
        raise ValueError("unsupported public data endpoint")
    url = BASE_URL + path + ("?" + urlencode(params) if params else "")
    request = Request(url, headers={"User-Agent": "ZITAR-public-data/1.0"}, method="GET")
    opener = build_opener(_NoRedirect())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=15) as response:
                payload = response.read(2_000_001)
            if len(payload) > 2_000_000:
                raise ValueError("oversized market response")
            return json.loads(payload)
        except HTTPError as exc:
            status = exc.code
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            exc.close()
            if status in (418, 429):
                raise RuntimeError(f"rate limited HTTP {status}; Retry-After={retry_after}; stop polling") from exc
            if status < 500 or attempt == 2:
                raise RuntimeError(f"market data HTTP {status}") from exc
        except (URLError, TimeoutError) as exc:
            if attempt == 2:
                raise RuntimeError("market data connection failed") from exc
        time.sleep(2 ** attempt)


def fetch_latest_records(symbols, interval="1h", count=100):
    """Fetch one bounded, aligned snapshot of the last N closed USDT candles.

    Server time fixes a common cutoff before any symbol requests. All requested
    candles must exist; incomplete, stale, gapped or malformed responses fail.
    No implicit polling, persistence, API credentials or application imports.
    """
    if isinstance(symbols, (str, bytes)):
        raise ValueError("symbols must be a sequence")
    symbols = tuple(symbols)
    if not symbols or len(symbols) > 20 or len(set(symbols)) != len(symbols):
        raise ValueError("provide 1..20 unique USDT symbols")
    if any(not isinstance(s, str) or not re.fullmatch(r"[A-Z0-9]{1,20}USDT", s) for s in symbols):
        raise ValueError("use uppercase Binance global USDT symbols")
    if interval not in DURATIONS or type(count) is not int or not 1 <= count <= 1000:
        raise ValueError("interval must be 1h/1d and count 1..1000")
    clock = _get_json("/api/v3/time")
    now = clock.get("serverTime") if isinstance(clock, dict) else None
    if type(now) is not int or now <= 0:
        raise ValueError("invalid server time")
    duration = DURATIONS[interval]
    cutoff = now // duration * duration
    start = cutoff - count * duration
    if start < 0:
        raise ValueError("requested history predates epoch")
    result = []
    for index, symbol in enumerate(sorted(symbols)):
        if index:
            time.sleep(0.25)
        page = _get_json("/api/v3/klines", {"symbol": symbol, "interval": interval,
                         "startTime": start, "endTime": cutoff - 1, "limit": count})
        if not isinstance(page, list) or len(page) != count:
            raise ValueError(f"{symbol}: incomplete or invalid market response")
        for i, candle in enumerate(page):
            if not isinstance(candle, list) or len(candle) < 7:
                raise ValueError(f"{symbol}: malformed candle")
            opened, closed = candle[0], candle[6]
            if (type(opened) is not int or type(closed) is not int
                    or opened != start + i * duration or closed != opened + duration - 1):
                raise ValueError(f"{symbol}: stale, unclosed, duplicate or gapped candle")
            try:
                op, hi, lo, cl, vol = map(float, candle[1:6])
                valid = (all(math.isfinite(x) for x in (op, hi, lo, cl, vol))
                         and min(op, hi, lo, cl) > 0 and vol >= 0
                         and lo <= min(op, cl) and hi >= max(op, cl))
            except (ValueError, TypeError, OverflowError):
                valid = False
            if not valid:
                raise ValueError(f"{symbol}: invalid OHLCV")
            stamp = datetime.fromtimestamp(opened / 1000, timezone.utc)
            result.append({"date": stamp.strftime("%Y-%m-%d %H:%M:%S"), "tic": symbol,
                           "open": op, "high": hi, "low": lo, "close": cl,
                           "volume": vol, "day": stamp.weekday()})
    return {"source": "Binance global", "quote_currency": "USDT", "interval": interval,
            "server_time_ms": now, "closed_before_ms": cutoff,
            "records": sorted(result, key=lambda r: (r["date"], r["tic"]))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--interval", choices=tuple(DURATIONS), default="1h")
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args(argv)
    try:
        snapshot = fetch_latest_records(args.symbols, args.interval, args.count)
    except (ValueError, RuntimeError) as exc:
        print(f"Online fetch failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(snapshot, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
