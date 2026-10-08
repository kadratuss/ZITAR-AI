import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

from market_engine import BASE_URL

ROOT = Path(__file__).resolve().parent
SOURCE_DB = ROOT / "learning_lab.db"
HISTORY_DB = ROOT / "long_history.db"

PLANS = {
    "1h": (90, 3_600_000),
    "1d": (730, 86_400_000),
}


def utc(ms):
    return datetime.fromtimestamp(
        ms / 1000, timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")


def initialize(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS historical_candles (
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            open_time_ms INTEGER NOT NULL,
            close_time_ms INTEGER NOT NULL,
            open_price TEXT NOT NULL,
            high_price TEXT NOT NULL,
            low_price TEXT NOT NULL,
            close_price TEXT NOT NULL,
            volume TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (symbol, interval, open_time_ms)
        )
    """)


def fetch(session, symbol, interval, start, end):
    for attempt in range(1, 4):
        try:
            response = session.get(
                BASE_URL + "/api/v3/klines",
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": start,
                    "endTime": end,
                    "limit": 1000,
                },
                timeout=25,
            )

            if response.status_code in (418, 429):
                raise RuntimeError(
                    f"API_ERISIM_SINIRI HTTP {response.status_code}"
                )

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                raise ValueError("Beklenmeyen API yaniti")

            return data

        except RuntimeError:
            raise
        except (requests.RequestException, ValueError) as exc:
            if attempt == 3:
                raise RuntimeError(str(exc)) from exc
            time.sleep(attempt * 2)


def validate(item, duration, latest_closed):
    if not isinstance(item, list) or len(item) < 7:
        raise ValueError("Eksik mum")

    opened = int(item[0])
    closed = int(item[6])

    if (
        opened % duration != 0
        or closed != opened + duration - 1
        or opened > latest_closed
    ):
        raise ValueError(f"Acik veya gecersiz mum: {opened}")

    op, hi, lo, cl, vol = [
        Decimal(str(item[i])) for i in (1, 2, 3, 4, 5)
    ]

    if (
        not all(x.is_finite() for x in (op, hi, lo, cl, vol))
        or min(op, hi, lo, cl) <= 0
        or vol < 0
        or lo > min(op, cl)
        or hi < max(op, cl)
    ):
        raise ValueError(f"Gecersiz fiyat/hacim: {opened}")

    return (
        opened, closed,
        str(op), str(hi), str(lo), str(cl), str(vol)
    )


def collect_interval(session, db, symbol, interval, days, duration):
    now_ms = int(time.time() * 1000)
    latest_closed = (now_ms // duration - 1) * duration
    requested_start = latest_closed - (
        days * 86_400_000 // duration - 1
    ) * duration

    cursor = requested_start
    rows = {}
    pages = 0

    while cursor <= latest_closed:
        page = fetch(
            session, symbol, interval, cursor, latest_closed
        )

        if not page:
            break

        pages += 1
        previous = None

        for item in page:
            row = validate(item, duration, latest_closed)
            opened = row[0]

            if not requested_start <= opened <= latest_closed:
                continue

            if previous is not None and opened <= previous:
                raise ValueError("API sayfasi sirali degil")

            previous = opened

            if opened in rows and rows[opened] != row:
                raise ValueError("Tekrar eden mum uyusmazligi")

            rows[opened] = row

        if previous is None:
            raise ValueError("API sayfasi ilerlemiyor")

        next_cursor = previous + duration
        if next_cursor <= cursor:
            raise ValueError("Sayfalama ilerlemiyor")

        cursor = next_cursor
        time.sleep(0.25)

    if not rows:
        print(f"VERI_YOK: {symbol} {interval}", flush=True)
        return

    ordered = [rows[t] for t in sorted(rows)]

    for first, second in zip(ordered, ordered[1:]):
        if second[0] - first[0] != duration:
            raise ValueError(
                f"Aralikli veri: {utc(first[0])} -> {utc(second[0])}"
            )

    fetched_at = datetime.now(timezone.utc).isoformat()

    # Tum kontroller tamamlanmadan bu parite/aralik yazilmaz.
    db.execute("BEGIN IMMEDIATE")
    try:
        for row in ordered:
            old = db.execute("""
                SELECT close_time_ms, open_price, high_price,
                       low_price, close_price, volume
                FROM historical_candles
                WHERE symbol=? AND interval=? AND open_time_ms=?
            """, (symbol, interval, row[0])).fetchone()

            if old is not None and tuple(old) != row[1:]:
                raise ValueError(
                    f"Eski mum API ile uyusmuyor: {utc(row[0])}"
                )

        db.executemany("""
            INSERT OR IGNORE INTO historical_candles (
                symbol, interval, open_time_ms, close_time_ms,
                open_price, high_price, low_price, close_price,
                volume, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (symbol, interval, *row, fetched_at)
            for row in ordered
        ])
        db.commit()
    except Exception:
        db.rollback()
        raise

    print(
        f"TAMAM: {symbol} {interval} | mum={len(ordered)} "
        f"| sayfa={pages} | {utc(ordered[0][0])} "
        f"-> {utc(ordered[-1][0])}",
        flush=True
    )


def main():
    with sqlite3.connect(
        SOURCE_DB.resolve().as_uri() + "?mode=ro", uri=True
    ) as source:
        symbols = [
            row[0] for row in source.execute("""
                SELECT DISTINCT symbol FROM candles
                WHERE interval='1m' ORDER BY symbol
            """)
        ]

    print("PORTFOLIOAI - UZUN DONEM GRAFIK HAFIZASI")
    print(f"Parite sayisi: {len(symbols)}")
    print("Hedef: 90 gun 1h + 730 gun 1d")
    print("Kayit: long_history.db", flush=True)

    failures = 0

    with sqlite3.connect(HISTORY_DB, timeout=20) as db:
        db.execute("PRAGMA busy_timeout=20000")
        initialize(db)
        db.commit()

        with requests.Session() as session:
            stop = False

            for symbol in symbols:
                for interval, (days, duration) in PLANS.items():
                    try:
                        collect_interval(
                            session, db, symbol,
                            interval, days, duration
                        )
                    except Exception as exc:
                        failures += 1
                        print(
                            f"HATA: {symbol} {interval} | "
                            f"{type(exc).__name__}: {exc}",
                            flush=True
                        )

                        if "API_ERISIM_SINIRI" in str(exc):
                            stop = True
                            break

                if stop:
                    break

    print(f"UZUN_ARSIV_TURU_BITTI | hata={failures}")
    print("Mevcut ajan ve kisa donem arsivi degistirilmedi.")


if __name__ == "__main__":
    main()
