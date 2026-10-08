from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from collections import defaultdict
import sqlite3

ROOT = Path(__file__).resolve().parent
MINUTE = 60_000
HOUR = 60 * MINUTE
DAY = 24 * HOUR
NOW = int(datetime.now(timezone.utc).timestamp() * 1000)

def ro(name):
    path = ROOT / name
    if not path.is_file():
        raise FileNotFoundError(name)
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)

def fetch(db, table, symbol, interval, limit):
    rows = db.execute(
        f"""SELECT open_time_ms, close_time_ms,
                   open_price, high_price, low_price, close_price
            FROM {table}
            WHERE symbol=? AND interval=?
            ORDER BY open_time_ms DESC LIMIT ?""",
        (symbol, interval, limit)
    ).fetchall()

    result = []
    for row in reversed(rows):
        try:
            opened, closed = int(row[0]), int(row[1])
            op, hi, lo, cl = (Decimal(str(x)) for x in row[2:])
            if (
                all(x.is_finite() and x > 0 for x in (op, hi, lo, cl))
                and hi >= max(op, cl)
                and lo <= min(op, cl)
                and opened <= closed < NOW
            ):
                result.append((opened, closed, op, hi, lo, cl))
        except (ValueError, TypeError, InvalidOperation):
            continue
    return result

def combine(rows, source_ms, target_ms):
    groups = defaultdict(list)
    for row in rows:
        opened, closed = row[:2]
        if opened % source_ms or closed != opened + source_ms - 1:
            continue
        groups[opened // target_ms * target_ms].append(row)

    output = []
    required = target_ms // source_ms
    for start, group in sorted(groups.items()):
        group.sort(key=lambda row: row[0])
        if (
            start + target_ms <= NOW
            and len(group) == required
            and all(
                row[0] == start + i * source_ms
                for i, row in enumerate(group)
            )
        ):
            output.append((
                start,
                start + target_ms - 1,
                group[0][2],
                max(row[3] for row in group),
                min(row[4] for row in group),
                group[-1][5],
            ))
    return output

def latest_contiguous(rows, span):
    if not rows:
        return []
    clean = []
    for row in reversed(rows):
        opened, closed = row[:2]
        if opened % span or closed != opened + span - 1:
            break
        if clean and opened + span != clean[-1][0]:
            break
        clean.append(row)
    return clean[::-1]

def indicators(rows):
    if len(rows) < 51:
        return None

    close = [float(row[5]) for row in rows]
    high = [float(row[3]) for row in rows]
    low = [float(row[4]) for row in rows]

    sma20 = sum(close[-20:]) / 20
    sma50 = sum(close[-50:]) / 50

    gains = []
    losses = []
    for i in range(len(close) - 14, len(close)):
        change = close[i] - close[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    if avg_gain == 0 and avg_loss == 0:
        rsi = 50.0
    elif avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - 100 / (1 + rs)

    true_ranges = [
        max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
        for i in range(len(close) - 14, len(close))
    ]
    atr = sum(true_ranges) / 14
    atr_pct = atr / close[-1] * 100

    if close[-1] > sma20 > sma50:
        structure = "FIYAT>SMA20>SMA50"
    elif close[-1] < sma20 < sma50:
        structure = "FIYAT<SMA20<SMA50"
    else:
        structure = "KARISIK"

    return structure, rsi, atr_pct

def report(symbol, interval, rows, span, max_delay):
    chain = latest_contiguous(rows, span)

    if not chain:
        return f"{interval:<3} | VERI YOK / SON MUM EKSIK", False, None

    last_close = chain[-1][1]
    delay = max(0, (NOW - last_close - 1) / MINUTE)
    stamp = datetime.fromtimestamp(
        last_close / 1000, timezone.utc
    ).strftime("%m-%d %H:%M")

    if delay > max_delay:
        return (
            f"{interval:<3} | BAYAT VERI | "
            f"gecikme={delay:.0f}dk | son UTC={stamp}"
        ), False, None

    values = indicators(chain)
    if values is None:
        return (
            f"{interval:<3} | YETERSIZ KESINTISIZ VERI "
            f"({len(chain)}/51) | son UTC={stamp}"
        ), False, None

    structure, rsi, atr_pct = values
    return (
        f"{interval:<3} | {structure:<19} | "
        f"RSI14={rsi:5.1f} | ATR14={atr_pct:5.2f}% | "
        f"mum={len(chain):>3} | son UTC={stamp}"
    ), True, structure

def main():
    print("PORTFOLIOAI | STRATEJI ARASTIRMA MOTORU V1")
    print("Salt-okunur. Emir vermez. Ajan ve portfoy degismez.")
    print("RSI14: son 14 degisimin basit ortalamasi.")
    print("ATR14: son 14 gercek araligin basit ortalamasi.\n")

    with ro("learning_lab.db") as short, ro("long_history.db") as long_db:
        symbols = [
            row[0] for row in short.execute(
                "SELECT DISTINCT symbol FROM candles "
                "WHERE interval='1m' ORDER BY symbol"
            )
        ]

        print(f"Arsivde bulunan parite: {len(symbols)}\n")
        complete = 0
        incomplete = 0

        for symbol in symbols:
            print(f"===== {symbol} =====")
            minute = fetch(short, "candles", symbol, "1m", 1800)
            hourly = fetch(
                long_db, "historical_candles", symbol, "1h", 600
            )
            daily = fetch(
                long_db, "historical_candles", symbol, "1d", 120
            )

            series = (
                ("1m", minute, MINUTE, 10),
                ("5m", combine(minute, MINUTE, 5 * MINUTE),
                 5 * MINUTE, 15),
                ("15m", combine(minute, MINUTE, 15 * MINUTE),
                 15 * MINUTE, 30),
                ("1h", hourly, HOUR, 180),
                ("4h", combine(hourly, HOUR, 4 * HOUR),
                 4 * HOUR, 480),
                ("1d", daily, DAY, 2880),
            )

            results = {}
            for interval, rows, span, delay_limit in series:
                line, valid, structure = report(
                    symbol, interval, rows, span, delay_limit
                )
                print(line)
                results[interval] = (valid, structure)

            required = ("15m", "1h", "4h", "1d")
            if all(results[name][0] for name in required):
                complete += 1
                structures = [results[name][1] for name in required]
                if len(set(structures)) == 1:
                    print("GORUNUM: Dort zaman diliminde ayni SMA yapisi.")
                else:
                    print("GORUNUM: Zaman dilimleri arasinda farklilik var.")
                print("DURUM: ARASTIRMA VERISI YETERLI")
            else:
                incomplete += 1
                print("DURUM: ARASTIRMA VERISI EKSIK / BAYAT")
            print()

        print("===== OZET =====")
        print(f"Arsiv paritesi: {len(symbols)}")
        print(f"Temel arastirma verisi yeterli: {complete}")
        print(f"Eksik veya bayat: {incomplete}")
        print("Bu ozet paper islem izni veya alim-satim sinyali degildir.")

if __name__ == "__main__":
    main()
