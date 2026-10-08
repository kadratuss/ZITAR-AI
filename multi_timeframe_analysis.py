from pathlib import Path
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from collections import defaultdict
import sqlite3

ROOT = Path(__file__).resolve().parent
MINUTE = 60_000
HOUR = 60 * MINUTE
DAY = 24 * HOUR
NOW_MS = int(datetime.now(timezone.utc).timestamp() * 1000)

def db_readonly(filename):
    path = ROOT / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)

def load(db, table, symbol, interval, limit):
    rows = db.execute(
        f"""SELECT open_time_ms, close_time_ms, close_price
            FROM {table}
            WHERE symbol=? AND interval=?
            ORDER BY open_time_ms DESC LIMIT ?""",
        (symbol, interval, limit)
    ).fetchall()
    result = []
    for opened, closed, price in reversed(rows):
        try:
            value = Decimal(str(price))
            opened, closed = int(opened), int(closed)
            if value > 0 and opened <= closed < NOW_MS:
                result.append((opened, closed, value))
        except (InvalidOperation, ValueError, TypeError):
            continue
    return result

def aggregate_fixed(rows, source_ms, target_ms):
    """Eksik veya henüz kapanmamış grupları atla."""
    groups = defaultdict(list)
    for row in rows:
        opened, closed, _ = row
        if opened % source_ms != 0 or closed != opened + source_ms - 1:
            continue
        bucket = opened // target_ms * target_ms
        groups[bucket].append(row)

    result = []
    expected = target_ms // source_ms
    for bucket, group in sorted(groups.items()):
        group.sort(key=lambda item: item[0])
        if (
            len(group) == expected
            and group[0][0] == bucket
            and group[-1][1] == bucket + target_ms - 1
            and all(
                group[i][0] == bucket + i * source_ms
                for i in range(expected)
            )
            and bucket + target_ms <= NOW_MS
        ):
            result.append((bucket, bucket + target_ms - 1, group[-1][2]))
    return result

def calendar(rows, interval):
    """Günlük mumlardan tam UTC haftaları/ayları oluştur."""
    groups = defaultdict(list)
    for row in rows:
        opened, closed, _ = row
        if opened % DAY != 0 or closed != opened + DAY - 1:
            continue
        date = datetime.fromtimestamp(opened / 1000, timezone.utc)
        if interval == "1w":
            start = (date - timedelta(days=date.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = start + timedelta(days=7)
        else:
            start = date.replace(day=1, hour=0, minute=0,
                                 second=0, microsecond=0)
            end = start.replace(year=start.year + 1, month=1) if (
                start.month == 12
            ) else start.replace(month=start.month + 1)
        groups[(int(start.timestamp() * 1000),
                int(end.timestamp() * 1000))].append(row)

    result = []
    for (start, end), group in sorted(groups.items()):
        group.sort(key=lambda item: item[0])
        expected = (end - start) // DAY
        if (
            end <= NOW_MS
            and len(group) == expected
            and all(
                row[0] == start + i * DAY
                for i, row in enumerate(group)
            )
        ):
            result.append((start, end - 1, group[-1][2]))
    return result

def analyze(rows, interval):
    rows = rows[-60:]
    if not rows:
        return f"{interval:<4} VERI YOK"

    last = datetime.fromtimestamp(
        rows[-1][1] / 1000, timezone.utc
    ).strftime("%Y-%m-%d %H:%M")

    if len(rows) < 20:
        return f"{interval:<4} AZ VERI ({len(rows)}) | Son kapanis UTC: {last}"

    prices = [row[2] for row in rows]
    sma5 = sum(prices[-5:]) / 5
    sma20 = sum(prices[-20:]) / 20
    trend = "YUKARI" if sma5 > sma20 else (
        "ASAGI" if sma5 < sma20 else "YATAY"
    )
    momentum = (prices[-1] / prices[-6] - 1) * 100
    return (
        f"{interval:<4} {trend:<6} | "
        f"5 mum degisim: {momentum:+8.2f}% | "
        f"Mum: {len(rows):>2} | Son kapanis UTC: {last}"
    )

def main():
    with db_readonly("learning_lab.db") as minute_db, \
         db_readonly("long_history.db") as long_db:

        symbols = [
            row[0] for row in minute_db.execute(
                "SELECT DISTINCT symbol FROM candles "
                "WHERE interval='1m' ORDER BY symbol"
            )
        ]

        print("PORTFOLIOAI | COKLU ZAMAN DILIMI")
        print(f"Arsivdeki parite: {len(symbols)}")
        print("Yalnizca kapanmis ve eksiksiz birlestirilmis mumlar.")
        print("Egilim ve degisim betimseldir; islem sinyali degildir.\n")

        for symbol in symbols:
            print(f"===== {symbol} =====")
            try:
                minute = load(
                    minute_db, "candles", symbol, "1m", 1600
                )
                hourly = load(
                    long_db, "historical_candles", symbol, "1h", 500
                )
                daily = load(
                    long_db, "historical_candles", symbol, "1d", 800
                )

                series = {
                    "1m": minute,
                    "5m": aggregate_fixed(minute, MINUTE, 5 * MINUTE),
                    "15m": aggregate_fixed(minute, MINUTE, 15 * MINUTE),
                    "1h": hourly,
                    "4h": aggregate_fixed(hourly, HOUR, 4 * HOUR),
                    "1d": daily,
                    "1w": calendar(daily, "1w"),
                    "1M": calendar(daily, "1M"),
                }
                for interval, rows in series.items():
                    print(analyze(rows, interval))
            except sqlite3.Error as exc:
                print(f"VERI OKUMA HATASI: {exc}")
            print()

if __name__ == "__main__":
    main()
