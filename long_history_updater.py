import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal

import requests

from long_history_collector import (
    HISTORY_DB, SOURCE_DB, PLANS, initialize,
    fetch, validate, collect_interval,
)


def same_candle(stored, downloaded):
    if len(stored) != 7 or len(downloaded) != 7:
        return False
    return (
        int(stored[0]) == int(downloaded[0])
        and int(stored[1]) == int(downloaded[1])
        and all(
            Decimal(str(a)) == Decimal(str(b))
            for a, b in zip(stored[2:], downloaded[2:])
        )
    )


def update_interval(session, db, symbol, interval, days, duration):
    latest = db.execute("""
        SELECT open_time_ms, close_time_ms, open_price,
               high_price, low_price, close_price, volume
        FROM historical_candles
        WHERE symbol = ? AND interval = ?
        ORDER BY open_time_ms DESC
        LIMIT 1
    """, (symbol, interval)).fetchone()

    if latest is None:
        print(
            f"ILK_ARSIV: {symbol} {interval}",
            flush=True,
        )
        collect_interval(
            session, db, symbol, interval, days, duration
        )
        return

    now_ms = int(time.time() * 1000)
    end_ms = (now_ms // duration - 1) * duration
    start_ms = int(latest[0])

    if start_ms > end_ms:
        raise ValueError("Kayitli son mum gelecekte")

    if start_ms == end_ms:
        print(
            f"GUNCEL: {symbol} {interval} | yeni_mum=0",
            flush=True,
        )
        return

    cursor = start_ms
    downloaded = {}
    pages = 0

    while cursor <= end_ms:
        page = fetch(
            session, symbol, interval, cursor, end_ms
        )

        if not page:
            break

        pages += 1
        previous = None

        for item in page:
            row = validate(item, duration, end_ms)
            opened = row[0]

            if not start_ms <= opened <= end_ms:
                continue

            if previous is not None and opened <= previous:
                raise ValueError("API sayfasi sirali degil")

            previous = opened

            if opened in downloaded and downloaded[opened] != row:
                raise ValueError("Tekrar eden mum uyusmazligi")

            downloaded[opened] = row

        if previous is None:
            raise ValueError("API sayfasi ilerlemiyor")

        next_cursor = previous + duration

        if next_cursor <= cursor:
            raise ValueError("Sayfalama ilerlemiyor")

        cursor = next_cursor
        time.sleep(0.25)

    ordered = [downloaded[t] for t in sorted(downloaded)]

    if (
        not ordered
        or ordered[0][0] != start_ms
        or ordered[-1][0] != end_ms
    ):
        raise ValueError(
            "Beklenen ilk veya son kapanmis mum eksik"
        )

    for first, second in zip(ordered, ordered[1:]):
        if second[0] - first[0] != duration:
            raise ValueError("Mumlar arasinda zaman boslugu var")

    if not same_candle(latest, ordered[0]):
        raise ValueError(
            "Kayitli son mum API ile uyusmuyor; yazilmadi"
        )

    new_rows = ordered[1:]
    fetched_at = datetime.now(timezone.utc).isoformat()

    # Baska bir islem araya veri yazdiysa eski
    # varsayimlarla kayit yapma.
    db.execute("BEGIN IMMEDIATE")

    try:
        current = db.execute("""
            SELECT open_time_ms, close_time_ms, open_price,
                   high_price, low_price, close_price, volume
            FROM historical_candles
            WHERE symbol = ? AND interval = ?
            ORDER BY open_time_ms DESC
            LIMIT 1
        """, (symbol, interval)).fetchone()

        if current != latest:
            raise RuntimeError(
                "Indirme sirasinda arsiv degisti; tur atlandi"
            )

        db.executemany("""
            INSERT INTO historical_candles (
                symbol, interval, open_time_ms, close_time_ms,
                open_price, high_price, low_price, close_price,
                volume, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (symbol, interval, *row, fetched_at)
            for row in new_rows
        ])

        db.commit()

    except Exception:
        db.rollback()
        raise

    print(
        f"TAMAM: {symbol} {interval} | "
        f"yeni_mum={len(new_rows)} | sayfa={pages}",
        flush=True,
    )


def main():
    with sqlite3.connect(
        SOURCE_DB.resolve().as_uri() + "?mode=ro",
        uri=True,
    ) as source:
        symbols = [
            row[0] for row in source.execute("""
                SELECT DISTINCT symbol
                FROM candles
                WHERE interval = '1m'
                ORDER BY symbol
            """)
        ]

    print(
        f"UZUN_ARSIV_GUNCELLEME | parite={len(symbols)}",
        flush=True,
    )

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
                        update_interval(
                            session, db, symbol,
                            interval, days, duration,
                        )
                    except Exception as exc:
                        failures += 1
                        print(
                            f"HATA: {symbol} {interval} | "
                            f"{type(exc).__name__}: {exc}",
                            flush=True,
                        )

                        if "API_ERISIM_SINIRI" in str(exc):
                            stop = True
                            break

                if stop:
                    break

    print(
        f"UZUN_ARSIV_GUNCELLEME_BITTI | hata={failures}",
        flush=True,
    )

    if failures:
        raise RuntimeError(
            f"Uzun arsivde {failures} basarisiz islem var"
        )


if __name__ == "__main__":
    main()
