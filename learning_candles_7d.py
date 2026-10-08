import json
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "learning_lab.db"
BASE_URL = "https://api.binance.me/api/v3/klines"
SYMBOL = "BTCTRY"
INTERVAL = "1m"
MINUTE_MS = 60_000


def fetch_candles(start_ms, end_ms):
    params = urllib.parse.urlencode({
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": 1000,
    })
    request = urllib.request.Request(
        BASE_URL + "?" + params,
        headers={"User-Agent": "PortfolioAI-Learning/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def main():
    now = datetime.now(timezone.utc)
    last_closed_open = (
        now.replace(second=0, microsecond=0) - timedelta(minutes=1)
    )
    first_open = last_closed_open - timedelta(days=7) + timedelta(minutes=1)

    start_ms = int(first_open.timestamp() * 1000)
    end_ms = int(last_closed_open.timestamp() * 1000)
    next_ms = start_ms
    inserted = 0
    fetched = 0

    print("BASLANGIC_UTC:", first_open.isoformat(), flush=True)
    print("BITIS_UTC:", last_closed_open.isoformat(), flush=True)

    with sqlite3.connect(DB_PATH, timeout=10) as db:
        while next_ms <= end_ms:
            candles = None
            for attempt in range(3):
                try:
                    candles = fetch_candles(next_ms, end_ms)
                    break
                except Exception as exc:
                    print(
                        f"AG_HATASI deneme={attempt + 1}: {exc}",
                        flush=True,
                    )
                    if attempt < 2:
                        time.sleep(2 * (attempt + 1))

            if candles is None:
                raise RuntimeError(
                    "Veri indirilemedi. Kaydedilen mumlar korunuyor."
                )
            if not candles:
                raise RuntimeError(
                    f"Beklenmeyen bos yanit: {next_ms}"
                )

            valid = [
                c for c in candles
                if start_ms <= int(c[0]) <= end_ms
                and int(c[6]) < int(now.timestamp() * 1000)
            ]
            if not valid:
                raise RuntimeError(
                    f"Gecerli kapanmis mum bulunamadi: {next_ms}"
                )

            before = db.total_changes
            for c in valid:
                db.execute("""
                    INSERT OR IGNORE INTO candles
                    (symbol, interval, open_time_ms, close_time_ms,
                     open_price, high_price, low_price, close_price, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    SYMBOL, INTERVAL, int(c[0]), int(c[6]),
                    c[1], c[2], c[3], c[4], c[5],
                ))
            inserted += db.total_changes - before
            fetched += len(valid)
            db.commit()

            next_ms = max(int(c[0]) for c in valid) + MINUTE_MS
            print(
                f"ILERI: {fetched} mum alindi, "
                f"{inserted} yeni mum kaydedildi",
                flush=True,
            )
            time.sleep(0.3)

        count = db.execute("""
            SELECT COUNT(*) FROM candles
            WHERE symbol = ? AND interval = ?
              AND open_time_ms BETWEEN ? AND ?
        """, (SYMBOL, INTERVAL, start_ms, end_ms)).fetchone()[0]

    expected = (end_ms - start_ms) // MINUTE_MS + 1
    print("BEKLENEN_7_GUNLUK_MUM:", expected)
    print("KAYITLI_7_GUNLUK_MUM:", count)
    print("EKSIK_MUM:", expected - count)
    print("YENI_EKLENEN:", inserted)


if __name__ == "__main__":
    main()
