import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "learning_lab.db"
TARGET = ROOT / "portfolio_hub.db"
MINUTE_MS = 60_000

TIMEFRAMES = {
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

def bucket_for(timestamp, timeframe):
    if timeframe in TIMEFRAMES:
        duration = TIMEFRAMES[timeframe] * MINUTE_MS
        start = timestamp // duration * duration
        return start, start + duration

    dt = datetime.fromtimestamp(timestamp / 1000, timezone.utc)

    if timeframe == "1w":
        day_start = datetime(
            dt.year, dt.month, dt.day, tzinfo=timezone.utc
        )
        start = (
            int(day_start.timestamp() * 1000)
            - dt.weekday() * 1440 * MINUTE_MS
        )
        return start, start + 7 * 1440 * MINUTE_MS

    if timeframe == "1M":
        start = int(datetime(
            dt.year, dt.month, 1, tzinfo=timezone.utc
        ).timestamp() * 1000)

        next_year = dt.year + (dt.month == 12)
        next_month = 1 if dt.month == 12 else dt.month + 1
        end = int(datetime(
            next_year, next_month, 1, tzinfo=timezone.utc
        ).timestamp() * 1000)
        return start, end

    raise ValueError(f"Bilinmeyen zaman dilimi: {timeframe}")

def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Kaynak bulunamadi: {SOURCE}")

    source_uri = SOURCE.resolve().as_uri() + "?mode=ro"

    with sqlite3.connect(source_uri, uri=True) as src:
        symbols = [
            row[0] for row in src.execute("""
                SELECT DISTINCT symbol
                FROM candles
                WHERE interval = '1m'
                ORDER BY symbol
            """)
        ]

        with sqlite3.connect(TARGET, timeout=20) as out:
            out.execute("PRAGMA busy_timeout=20000")
            out.execute("""
                CREATE TABLE IF NOT EXISTS timeframe_candles (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    open_time_ms INTEGER NOT NULL,
                    open_price TEXT NOT NULL,
                    high_price TEXT NOT NULL,
                    low_price TEXT NOT NULL,
                    close_price TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    source_candle_count INTEGER NOT NULL,
                    calculated_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, timeframe, open_time_ms)
                )
            """)
            out.execute("""
                CREATE TABLE IF NOT EXISTS market_coverage (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    complete_candles INTEGER NOT NULL,
                    first_open_ms INTEGER,
                    last_open_ms INTEGER,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, timeframe)
                )
            """)

            now_ms = int(time.time() * 1000)
            updated_at = datetime.now(timezone.utc).isoformat()

            print(f"KAYNAKTAKI_PARITE_SAYISI: {len(symbols)}")

            for symbol in symbols:
                rows = src.execute("""
                    SELECT open_time_ms, open_price, high_price,
                           low_price, close_price, volume
                    FROM candles
                    WHERE symbol = ? AND interval = '1m'
                    ORDER BY open_time_ms
                """, (symbol,)).fetchall()

                unique = {int(row[0]): row for row in rows}
                ordered = [unique[t] for t in sorted(unique)]
                counts = {}

                for timeframe in (*TIMEFRAMES, "1w", "1M"):
                    groups = defaultdict(list)
                    ends = {}

                    for row in ordered:
                        start, end = bucket_for(
                            int(row[0]), timeframe
                        )
                        groups[start].append(row)
                        ends[start] = end

                    saved = 0
                    first_saved = None
                    last_saved = None

                    for start, group in sorted(groups.items()):
                        end = ends[start]
                        expected_count = (end - start) // MINUTE_MS

                        if end > now_ms or len(group) != expected_count:
                            continue

                        if (
                            int(group[0][0]) != start
                            or int(group[-1][0]) != end - MINUTE_MS
                            or any(
                                int(group[i][0]) - int(group[i - 1][0])
                                != MINUTE_MS
                                for i in range(1, len(group))
                            )
                        ):
                            continue

                        high = max(Decimal(r[2]) for r in group)
                        low = min(Decimal(r[3]) for r in group)
                        volume = sum(
                            (Decimal(r[5]) for r in group),
                            Decimal(0)
                        )

                        out.execute("""
                            INSERT INTO timeframe_candles (
                                symbol, timeframe, open_time_ms,
                                open_price, high_price, low_price,
                                close_price, volume,
                                source_candle_count, calculated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(
                                symbol, timeframe, open_time_ms
                            ) DO UPDATE SET
                                open_price=excluded.open_price,
                                high_price=excluded.high_price,
                                low_price=excluded.low_price,
                                close_price=excluded.close_price,
                                volume=excluded.volume,
                                source_candle_count=excluded.source_candle_count,
                                calculated_at=excluded.calculated_at
                        """, (
                            symbol, timeframe, start,
                            str(Decimal(group[0][1])),
                            str(high), str(low),
                            str(Decimal(group[-1][4])),
                            str(volume), len(group), updated_at
                        ))

                        saved += 1
                        if first_saved is None:
                            first_saved = start
                        last_saved = start

                    out.execute("""
                        INSERT INTO market_coverage (
                            symbol, timeframe, complete_candles,
                            first_open_ms, last_open_ms, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(symbol, timeframe) DO UPDATE SET
                            complete_candles=excluded.complete_candles,
                            first_open_ms=excluded.first_open_ms,
                            last_open_ms=excluded.last_open_ms,
                            updated_at=excluded.updated_at
                    """, (
                        symbol, timeframe, saved,
                        first_saved, last_saved, updated_at
                    ))
                    counts[timeframe] = saved

                out.commit()
                print(
                    f"{symbol}: " + " | ".join(
                        f"{tf}={count}"
                        for tf, count in counts.items()
                    ),
                    flush=True
                )

    print("ARSIV_ISLEMI_TAMAMLANDI")
    print("Eksik veya kapanmamis haftalik/aylik mum kaydedilmedi.")
    print("Mevcut islem ajanina dokunulmadi.")

if __name__ == "__main__":
    main()
