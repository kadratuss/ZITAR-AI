import importlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_DB = ROOT / "learning_lab.db"
HUB_DB = ROOT / "portfolio_hub.db"

# Saniye. Gorevler birbirinden bagimsiz zamanlanir.
JOBS = {
    "market_timeframes": 60,
    "news_collection": 300,
}

# Haftalik/aylik mumlar, yeterli gecmis veri edinilince eklenecek.
TIMEFRAMES = {
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

def now():
    return datetime.now(timezone.utc).isoformat()

def connect():
    db = sqlite3.connect(HUB_DB, timeout=15)
    db.execute("PRAGMA busy_timeout=15000")
    return db

def initialize():
    with connect() as db:
        db.execute("""
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
        db.execute("""
            CREATE TABLE IF NOT EXISTS job_runs (
                job_name TEXT PRIMARY KEY,
                last_started_at TEXT,
                last_finished_at TEXT,
                last_status TEXT NOT NULL,
                last_detail TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        db.execute("""
            INSERT OR REPLACE INTO system_config (key, value)
            VALUES ('architecture_version', 'hub-v1')
        """)

def record_job(name, started, status, detail):
    with connect() as db:
        db.execute("""
            INSERT INTO job_runs (
                job_name, last_started_at, last_finished_at,
                last_status, last_detail
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(job_name) DO UPDATE SET
                last_started_at=excluded.last_started_at,
                last_finished_at=excluded.last_finished_at,
                last_status=excluded.last_status,
                last_detail=excluded.last_detail
        """, (name, started, now(), status, detail))

def market_timeframes():
    if not SOURCE_DB.exists():
        raise FileNotFoundError(f"Kaynak mum veritabani yok: {SOURCE_DB}")

    # Kaynak veritabani yalnizca okunur.
    source_uri = SOURCE_DB.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(source_uri, uri=True, timeout=15) as src:
        rows = src.execute("""
            SELECT open_time_ms, open_price, high_price,
                   low_price, close_price, volume
            FROM candles
            WHERE symbol = 'BTCTRY' AND interval = '1m'
            ORDER BY open_time_ms
        """).fetchall()

    # Ayni dakikanin tekrar kaydi varsa iki kez sayma.
    by_minute = {int(row[0]): row for row in rows}
    rows = [by_minute[t] for t in sorted(by_minute)]

    saved = {}
    with connect() as db:
        for timeframe, minutes in TIMEFRAMES.items():
            duration = minutes * 60_000
            groups = {}

            for row in rows:
                t = int(row[0])
                bucket = (t // duration) * duration
                groups.setdefault(bucket, []).append(row)

            count = 0
            for bucket, group in groups.items():
                # Yalnizca eksiksiz, ardisik ve kapanmis mumlar.
                expected = [
                    bucket + i * 60_000
                    for i in range(minutes)
                ]
                actual = [int(row[0]) for row in group]
                if actual != expected:
                    continue

                # Acik olan zaman dilimini kaydetme.
                if bucket + duration > int(time.time() * 1000):
                    continue

                opening = Decimal(group[0][1])
                highest = max(Decimal(r[2]) for r in group)
                lowest = min(Decimal(r[3]) for r in group)
                closing = Decimal(group[-1][4])
                volume = sum(
                    (Decimal(r[5]) for r in group), Decimal(0)
                )

                db.execute("""
                    INSERT INTO timeframe_candles (
                        symbol, timeframe, open_time_ms,
                        open_price, high_price, low_price,
                        close_price, volume, source_candle_count,
                        calculated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, timeframe, open_time_ms)
                    DO UPDATE SET
                        open_price=excluded.open_price,
                        high_price=excluded.high_price,
                        low_price=excluded.low_price,
                        close_price=excluded.close_price,
                        volume=excluded.volume,
                        source_candle_count=excluded.source_candle_count,
                        calculated_at=excluded.calculated_at
                """, (
                    "BTCTRY", timeframe, bucket,
                    str(opening), str(highest), str(lowest),
                    str(closing), str(volume), len(group), now()
                ))
                count += 1

            saved[timeframe] = count

        db.commit()

    return json.dumps(saved, ensure_ascii=False)

def news_collection():
    core = importlib.import_module("ai_core")
    core.initialize()

    with sqlite3.connect(core.DB, timeout=15) as db:
        before = db.execute(
            "SELECT COUNT(*) FROM knowledge"
        ).fetchone()[0]

    core.collect()

    with sqlite3.connect(core.DB, timeout=15) as db:
        after = db.execute(
            "SELECT COUNT(*) FROM knowledge"
        ).fetchone()[0]

    return f"toplam={after}, yeni={after - before}"

def run_job(name, fn):
    started = now()
    print(f"\n[{started}] BASLADI: {name}", flush=True)
    try:
        detail = fn()
        record_job(name, started, "OK", detail)
        print(f"[{now()}] TAMAM: {name} | {detail}", flush=True)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        record_job(name, started, "ERROR", detail)
        print(f"[{now()}] HATA: {name} | {detail}", flush=True)

def main():
    initialize()
    print("PORTFOLIOAI HUB v1")
    print("Tek baslangic omurgasi aktif.")
    print("Mevcut islem ajani baslatilmaz veya degistirilmez.")
    print("Yerel model disariya acilmaz.")
    print("Cikmak icin Ctrl+C.\n")

    tasks = {
        "market_timeframes": market_timeframes,
        "news_collection": news_collection,
    }
    next_run = {name: 0.0 for name in tasks}

    try:
        while True:
            for name, fn in tasks.items():
                current = time.monotonic()
                if current >= next_run[name]:
                    # Basarisiz gorev de bir sonraki turda yeniden denenir.
                    next_run[name] = current + JOBS[name]
                    run_job(name, fn)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nPORTFOLIOAI HUB durduruldu.")
        print("Ayri calisan islem ajanina dokunulmadi.")

if __name__ == "__main__":
    main()
