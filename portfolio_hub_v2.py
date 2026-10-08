import importlib
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import portfolio_hub as hub

ROOT = Path(__file__).resolve().parent
HUB_DB = ROOT / "portfolio_hub.db"

INTERVALS = {
    "market_timeframes": 60,
    "news_collection": 300,
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    db = sqlite3.connect(HUB_DB, timeout=15)
    db.execute("PRAGMA busy_timeout=15000")
    return db


def initialize():
    hub.initialize()

    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS news_intake (
                source_id INTEGER PRIMARY KEY,
                collected_at TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                published_at TEXT,
                title TEXT NOT NULL,
                intake_status TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS intake_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        core = importlib.import_module("ai_core")
        core.initialize()

        with sqlite3.connect(core.DB, timeout=15) as source:
            latest_id = source.execute("""
                SELECT COALESCE(MAX(id), 0)
                FROM knowledge
                WHERE project = 'investment'
            """).fetchone()[0]

        # Ilk baslangictaki mevcut haberler gecmis kayittir.
        # Yeniden baslatmada kayitli sinir korunur.
        db.execute("""
            INSERT OR IGNORE INTO intake_state (key, value)
            VALUES ('last_seen_news_id', ?)
        """, (str(latest_id),))

        db.execute("""
            INSERT OR REPLACE INTO system_config (key, value)
            VALUES ('architecture_version', 'hub-v2')
        """)


def collect_and_register_news():
    core = importlib.import_module("ai_core")
    core.initialize()

    with connect() as db:
        last_seen = int(db.execute("""
            SELECT value FROM intake_state
            WHERE key = 'last_seen_news_id'
        """).fetchone()[0])

    # Var olan RSS toplama mekanizmasini yeniden kullaniyoruz.
    core.collect()

    with sqlite3.connect(core.DB, timeout=15) as source:
        rows = source.execute("""
            SELECT id, collected_at, published_at, title
            FROM knowledge
            WHERE project = 'investment' AND id > ?
            ORDER BY id
        """, (last_seen,)).fetchall()

    with connect() as db:
        for source_id, collected_at, published_at, title in rows:
            db.execute("""
                INSERT OR IGNORE INTO news_intake (
                    source_id, collected_at, detected_at,
                    published_at, title, intake_status
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                source_id, collected_at, utc_now(),
                published_at, title, "NEW_UNANALYZED"
            ))

        if rows:
            db.execute("""
                UPDATE intake_state
                SET value = ?
                WHERE key = 'last_seen_news_id'
            """, (str(rows[-1][0]),))

        db.commit()

    for source_id, _, _, title in rows:
        print(
            f"YENI_HABER_GIRISI: {source_id} | {title}",
            flush=True
        )

    return f"yeni_giris={len(rows)}"


def execute_job(name, function):
    started = utc_now()
    print(f"[{started}] BASLADI: {name}", flush=True)

    try:
        detail = function()
        hub.record_job(name, started, "OK", detail)
        print(
            f"[{utc_now()}] TAMAM: {name} | {detail}",
            flush=True
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        hub.record_job(name, started, "ERROR", detail)
        print(
            f"[{utc_now()}] HATA: {name} | {detail}",
            flush=True
        )


def main():
    initialize()

    jobs = {
        "market_timeframes": hub.market_timeframes,
        "news_collection": collect_and_register_news,
    }

    next_run = {name: 0.0 for name in jobs}
    running = {}

    print("PORTFOLIOAI HUB v2")
    print("Grafik ve haber gorevleri ayri is parcaciklarinda.")
    print("Eski haberler yeni giris olarak isaretlenmez.")
    print("Islem ajani baslatilmaz veya degistirilmez.")
    print("Cikmak icin Ctrl+C.", flush=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        try:
            while True:
                current = time.monotonic()

                for name, function in jobs.items():
                    future = running.get(name)

                    # Ayni gorev ikinci kez ust uste baslamaz.
                    if future is not None and not future.done():
                        continue

                    if current >= next_run[name]:
                        running[name] = pool.submit(
                            execute_job, name, function
                        )
                        next_run[name] = current + INTERVALS[name]

                time.sleep(1)

        except KeyboardInterrupt:
            print(
                "\nHub durduruluyor; baslamis gorevler bekleniyor.",
                flush=True
            )


if __name__ == "__main__":
    main()
