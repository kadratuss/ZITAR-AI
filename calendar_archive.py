import calendar
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "long_history.db"
DAY_MS = 86_400_000


def period_bounds(day, interval):
    if interval == "1w":
        start = day - timedelta(days=day.weekday())
        end = start + timedelta(days=7)
    else:
        start = day.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    return start, end


def ms(day):
    return int(day.timestamp() * 1000)


def aggregate(db, symbol, interval):
    daily = db.execute("""
        SELECT open_time_ms, open_price, high_price,
               low_price, close_price, volume
        FROM historical_candles
        WHERE symbol = ? AND interval = '1d'
        ORDER BY open_time_ms
    """, (symbol,)).fetchall()

    by_day = {int(row[0]): row for row in daily}
    if not daily:
        return 0

    first_day = datetime.fromtimestamp(
        int(daily[0][0]) / 1000, timezone.utc
    )
    last_day = datetime.fromtimestamp(
        int(daily[-1][0]) / 1000, timezone.utc
    )

    period_start, _ = period_bounds(first_day, interval)
    count = 0

    while period_start <= last_day:
        _, period_end = period_bounds(period_start, interval)
        expected_days = (period_end - period_start).days

        # Son gun dahil tum gunler mevcut degilse
        # haftalik/aylik mum olusturulmaz.
        day_times = [
            ms(period_start + timedelta(days=i))
            for i in range(expected_days)
        ]

        if all(t in by_day for t in day_times):
            rows = [by_day[t] for t in day_times]
            opened = ms(period_start)
            closed = ms(period_end) - 1

            values = (
                symbol,
                interval,
                opened,
                closed,
                str(Decimal(str(rows[0][1]))),
                str(max(Decimal(str(r[2])) for r in rows)),
                str(min(Decimal(str(r[3])) for r in rows)),
                str(Decimal(str(rows[-1][4]))),
                str(sum(Decimal(str(r[5])) for r in rows)),
            )

            old = db.execute("""
                SELECT close_time_ms, open_price, high_price,
                       low_price, close_price, volume
                FROM aggregated_candles
                WHERE symbol = ? AND interval = ?
                  AND open_time_ms = ?
            """, (symbol, interval, opened)).fetchone()

            if old is not None:
                same_time = int(old[0]) == closed
                same_values = all(
                    Decimal(str(a)) == Decimal(str(b))
                    for a, b in zip(old[1:], values[4:])
                )
                if not (same_time and same_values):
                    raise ValueError(
                        f"Kayit uyusmazligi: {symbol} "
                        f"{interval} {period_start.date()}"
                    )
            else:
                db.execute("""
                    INSERT INTO aggregated_candles (
                        symbol, interval, open_time_ms,
                        close_time_ms, open_price, high_price,
                        low_price, close_price, volume
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, values)

            count += 1

        period_start = period_end

    return count


def main():
    if not DB_PATH.is_file():
        raise FileNotFoundError(DB_PATH)

    with sqlite3.connect(DB_PATH, timeout=20) as db:
        db.execute("PRAGMA busy_timeout=20000")
        db.execute("""
            CREATE TABLE IF NOT EXISTS aggregated_candles (
                symbol TEXT NOT NULL,
                interval TEXT NOT NULL,
                open_time_ms INTEGER NOT NULL,
                close_time_ms INTEGER NOT NULL,
                open_price TEXT NOT NULL,
                high_price TEXT NOT NULL,
                low_price TEXT NOT NULL,
                close_price TEXT NOT NULL,
                volume TEXT NOT NULL,
                PRIMARY KEY (symbol, interval, open_time_ms)
            )
        """)

        symbols = [
            row[0] for row in db.execute("""
                SELECT DISTINCT symbol
                FROM historical_candles
                WHERE interval = '1d'
                ORDER BY symbol
            """)
        ]

        print("PORTFOLIOAI - HAFTALIK / AYLIK ARSIV")

        errors = 0
        for symbol in symbols:
            try:
                # Her paritenin iki zaman dilimi birlikte kaydedilir.
                with db:
                    weekly = aggregate(db, symbol, "1w")
                    monthly = aggregate(db, symbol, "1M")

                print(
                    f"TAMAM: {symbol} | "
                    f"1w={weekly} | 1M={monthly}",
                    flush=True
                )
            except Exception as exc:
                errors += 1
                print(
                    f"HATA: {symbol} | "
                    f"{type(exc).__name__}: {exc}",
                    flush=True
                )

        print(f"TAKVIM_ARSIVI_BITTI | hata={errors}")
        print("Kayit yeri: long_history.db / aggregated_candles")


if __name__ == "__main__":
    main()
