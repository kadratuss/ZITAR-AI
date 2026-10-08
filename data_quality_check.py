from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from collections import Counter
import sqlite3

ROOT = Path(__file__).resolve().parent
NOW_MS = int(datetime.now(timezone.utc).timestamp() * 1000)
DAY_MS = 86_400_000
INTERVAL_MS = {"1m": 60_000, "1h": 3_600_000, "1d": DAY_MS}

def open_ro(filename):
    path = ROOT / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)

def inspect(db, table, interval):
    issues = Counter()
    examples = []
    symbols = {}
    previous = {}

    rows = db.execute(
        f"""SELECT symbol, open_time_ms, close_time_ms,
                   open_price, high_price, low_price,
                   close_price, volume
            FROM {table}
            WHERE interval=?
            ORDER BY symbol, open_time_ms""",
        (interval,)
    )

    for symbol, opened, closed, op, hi, lo, cl, vol in rows:
        symbols[symbol] = symbols.get(symbol, 0) + 1
        labels = []

        try:
            opened, closed = int(opened), int(closed)
            op, hi, lo, cl, vol = (
                Decimal(str(x)) for x in (op, hi, lo, cl, vol)
            )
            if not all(x.is_finite() for x in (op, hi, lo, cl, vol)):
                raise ValueError("non-finite")
        except (ValueError, TypeError, InvalidOperation):
            labels.append("GECERSIZ_SAYI")
            opened = None

        if opened is not None:
            span = INTERVAL_MS[interval]

            if opened % span or closed != opened + span - 1:
                labels.append("MUM_ZAMANI")
            if closed >= NOW_MS:
                labels.append("KAPANMAMIS_VEYA_GELECEK")
            if min(op, hi, lo, cl) <= 0 or vol < 0:
                labels.append("GECERSIZ_FIYAT_HACIM")
            if hi < max(op, cl) or lo > min(op, cl) or hi < lo:
                labels.append("OHLC_TUTARSIZ")

            if symbol in previous:
                prev_open, prev_close = previous[symbol]
                delta = opened - prev_open
                if delta == 0:
                    labels.append("TEKRAR_MUM")
                elif delta < 0:
                    labels.append("ZAMAN_SIRASI")
                elif delta > span:
                    labels.append("EKSIK_MUM_ARALIGI")

                if interval == "1d" and prev_close > 0 and cl > 0:
                    change = (cl / prev_close - 1) * 100
                    if abs(change) >= 30:
                        labels.append("BUYUK_GUNLUK_HAREKET")
                        if len(examples) < 15:
                            examples.append(
                                f"  {symbol} {datetime.fromtimestamp(opened/1000, timezone.utc).date()}"
                                f" | onceki={prev_close} simdiki={cl}"
                                f" | degisim={change:+.2f}%"
                            )

            previous[symbol] = (opened, cl)

        for label in set(labels):
            issues[label] += 1
            if label != "BUYUK_GUNLUK_HAREKET" and len(examples) < 15:
                examples.append(f"  {symbol} {opened}: {label}")

    print(f"\n{table} / {interval}")
    print(f"Parite: {len(symbols)} | Toplam mum: {sum(symbols.values())}")
    if issues:
        for label, count in sorted(issues.items()):
            print(f"  {label}: {count}")
    else:
        print("  Kontrol edilen alanlarda sorun saptanmadi.")
    if examples:
        print("Ornekler (en fazla 15):")
        print("\n".join(examples))
    return issues

def main():
    print("PORTFOLIOAI | SALT-OKUNUR VERI KALITE KONTROLU")
    print("BUYUK_GUNLUK_HAREKET tek basina veri hatasi demek degildir.")
    totals = Counter()

    with open_ro("learning_lab.db") as short, \
         open_ro("long_history.db") as long_db:
        for db, table, interval in (
            (short, "candles", "1m"),
            (long_db, "historical_candles", "1h"),
            (long_db, "historical_candles", "1d"),
        ):
            totals.update(inspect(db, table, interval))

    print("\n===== GENEL OZET =====")
    for label, count in sorted(totals.items()):
        print(f"{label}: {count}")
    if not totals:
        print("Kontrol edilen alanlarda sorun saptanmadi.")
    print("Veritabanlarina yazilmadi. Islem emri verilmedi.")

if __name__ == "__main__":
    main()
