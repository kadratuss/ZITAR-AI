import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

from market_engine import BASE_URL, get_market_data
from multi_market_collector import download_symbol

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "learning_lab.db"

MINUTE_MS = 60_000
NEW_SYMBOLS_PER_RUN = 2
HISTORY_DAYS = 7
STALE_RETRY_SECONDS = 24 * 60 * 60


def utc_text(ms):
    return datetime.fromtimestamp(
        ms / 1000, timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")


def initialize(db):
    db.execute("PRAGMA busy_timeout=20000")
    db.execute("""
        CREATE TABLE IF NOT EXISTS stale_symbol_checks (
            symbol TEXT PRIMARY KEY,
            last_candle_ms INTEGER NOT NULL,
            checked_at_ms INTEGER NOT NULL,
            retry_after_ms INTEGER NOT NULL
        )
    """)


def existing_symbols(db):
    return {
        row[0] for row in db.execute("""
            SELECT DISTINCT symbol
            FROM candles
            WHERE interval = '1m'
        """)
    }


def latest_candle(db, symbol):
    return db.execute("""
        SELECT open_time_ms, close_time_ms, open_price,
               high_price, low_price, close_price, volume
        FROM candles
        WHERE symbol = ? AND interval = '1m'
        ORDER BY open_time_ms DESC
        LIMIT 1
    """, (symbol,)).fetchone()


def matches_existing(stored, downloaded):
    if int(stored[0]) != int(downloaded["open_ms"]):
        return False

    if int(stored[1]) != int(downloaded["close_ms"]):
        return False

    fields = ("open", "high", "low", "close", "volume")

    return all(
        Decimal(str(stored[index + 2]))
        == Decimal(downloaded[field])
        for index, field in enumerate(fields)
    )


def latest_api_minute(session, symbol):
    """Tanilama: zaman araligi vermeden son 1m mumunu sor."""
    params = {
        "symbol": symbol,
        "interval": "1m",
        "limit": 1,
    }

    for attempt in range(1, 4):
        try:
            response = session.get(
                BASE_URL + "/api/v3/klines",
                params=params,
                timeout=25,
            )

            if response.status_code in (418, 429):
                raise RuntimeError(
                    "API hiz/erisim siniri: "
                    f"HTTP {response.status_code}"
                )

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                raise ValueError(
                    "Son mum sorgusunda beklenmeyen API yaniti"
                )

            if not data:
                raise ValueError(
                    "Son mum sorgusu bos dondu"
                )

            return int(data[-1][0])

        except RuntimeError:
            raise
        except (requests.RequestException, ValueError) as exc:
            if attempt == 3:
                raise RuntimeError(
                    f"{symbol}: son mum sorgusu basarisiz: {exc}"
                ) from exc

            time.sleep(attempt * 2)


def mark_stale(symbol, last_ms):
    now_ms = int(time.time() * 1000)
    retry_ms = now_ms + STALE_RETRY_SECONDS * 1000

    with sqlite3.connect(DB_PATH, timeout=20) as db:
        initialize(db)
        db.execute("""
            INSERT INTO stale_symbol_checks (
                symbol, last_candle_ms,
                checked_at_ms, retry_after_ms
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                last_candle_ms = excluded.last_candle_ms,
                checked_at_ms = excluded.checked_at_ms,
                retry_after_ms = excluded.retry_after_ms
        """, (symbol, last_ms, now_ms, retry_ms))
        db.commit()


def update_symbol(session, symbol, end_ms):
    with sqlite3.connect(DB_PATH, timeout=20) as db:
        initialize(db)
        previous = latest_candle(db, symbol)

    if previous is None:
        start_ms = end_ms - (
            HISTORY_DAYS * 24 * 60 - 1
        ) * MINUTE_MS

        print(
            f"{symbol}: yeni parite, 7 gun indirilecek",
            flush=True,
        )
    else:
        start_ms = int(previous[0])

        if start_ms > end_ms:
            raise ValueError(
                f"{symbol}: kayitli son mum gelecekte gorunuyor"
            )

        if start_ms == end_ms:
            print(f"{symbol}: zaten guncel", flush=True)
            return "current"

        print(
            f"{symbol}: {utc_text(start_ms)} "
            f"-> {utc_text(end_ms)} guncelleniyor",
            flush=True,
        )

    try:
        candles, pages = download_symbol(
            session, symbol, start_ms, end_ms
        )
    except ValueError as exc:
        # Yalnizca YENI paritenin tamamen bos araligini
        # taniyoruz. Mevcut paritedeki bosluk hata kalir.
        empty_new_symbol = (
            previous is None
            and "istenen aralikta mum bulunamadi" in str(exc)
        )

        if not empty_new_symbol:
            raise

        last_ms = latest_api_minute(session, symbol)

        if last_ms < start_ms:
            mark_stale(symbol, last_ms)

            print(
                f"GUNCEL_VERI_YOK: {symbol} | "
                f"son_mum={utc_text(last_ms)} | "
                "24 saat sonra tekrar denenecek",
                flush=True,
            )
            return "stale"

        # API son mumun yeni oldugunu soyluyorsa
        # bos tarih araligini sessizce gecmeyiz.
        raise ValueError(
            f"{symbol}: son mum {utc_text(last_ms)} "
            "ama istenen aralik bos; kontrol gerekli"
        ) from exc

    if int(candles[0]["open_ms"]) != start_ms:
        raise ValueError(
            f"{symbol}: ilk beklenen mum eksik"
        )

    if previous is not None:
        if not matches_existing(previous, candles[0]):
            raise ValueError(
                f"{symbol}: eski son mum API ile uyusmuyor; "
                "veritabani degistirilmedi"
            )

        new_candles = candles[1:]
    else:
        new_candles = candles

    # Tum mumlar dogrulanmadan bu pariteye yazilmaz.
    with sqlite3.connect(DB_PATH, timeout=20) as db:
        initialize(db)
        db.execute("BEGIN IMMEDIATE")

        current = latest_candle(db, symbol)

        if current != previous:
            db.rollback()
            raise RuntimeError(
                f"{symbol}: indirme sirasinda arsiv degisti; "
                "bu tur atlandi"
            )

        db.executemany("""
            INSERT INTO candles (
                symbol, interval, open_time_ms,
                close_time_ms, open_price, high_price,
                low_price, close_price, volume
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                symbol, "1m",
                int(c["open_ms"]),
                int(c["close_ms"]),
                c["open"], c["high"], c["low"],
                c["close"], c["volume"]
            )
            for c in new_candles
        ])

        # Daha once eski diye isaretlenen parite
        # artik basariyla indirildiyse isareti kaldir.
        db.execute(
            "DELETE FROM stale_symbol_checks WHERE symbol = ?",
            (symbol,),
        )

        db.commit()

    print(
        f"TAMAM: {symbol} | yeni_mum={len(new_candles)} "
        f"| sayfa={pages}",
        flush=True,
    )

    return "updated"


def main():
    if not DB_PATH.is_file():
        raise FileNotFoundError(DB_PATH)

    market = get_market_data()
    top_symbols = [
        pair["symbol"] for pair in market["pairs"]
    ]

    if not top_symbols:
        raise RuntimeError("Piyasa motoru parite dondurmedi")

    now_ms = int(time.time() * 1000)

    with sqlite3.connect(DB_PATH, timeout=20) as db:
        initialize(db)
        existing = existing_symbols(db)

        deferred = {
            row[0] for row in db.execute("""
                SELECT symbol
                FROM stale_symbol_checks
                WHERE retry_after_ms > ?
            """, (now_ms,))
        }

    old_symbols = sorted(existing)

    # Eski veri nedeniyle ertelenenler yeni parite
    # kotasini doldurmaz; sonraki uygunlara gecilir.
    new_symbols = [
        symbol for symbol in top_symbols
        if symbol not in existing
        and symbol not in deferred
    ][:NEW_SYMBOLS_PER_RUN]

    selected = old_symbols + new_symbols

    current_minute = (
        now_ms // MINUTE_MS
    ) * MINUTE_MS

    end_ms = current_minute - MINUTE_MS

    print("PORTFOLIOAI - PIYASA VERISI GUNCELLEME")
    print(f"Arsivdeki parite: {len(old_symbols)}")
    print(
        f"Yeni eklenecek: {', '.join(new_symbols) or 'YOK'}"
    )
    print(
        f"Gecici ertelenen parite: "
        f"{', '.join(sorted(deferred)) or 'YOK'}"
    )
    print(f"Son kapanmis dakika: {utc_text(end_ms)}")

    failures = 0
    stale_count = 0

    with requests.Session() as session:
        for symbol in selected:
            try:
                status = update_symbol(
                    session, symbol, end_ms
                )

                if status == "stale":
                    stale_count += 1

            except Exception as exc:
                failures += 1

                print(
                    f"HATA: {symbol} | "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )

                if "API hiz/erisim siniri" in str(exc):
                    break

    print(
        f"\nGUNCELLEME_TURU_BITTI | "
        f"hata={failures} | guncel_veri_yok={stale_count}",
        flush=True,
    )

    if failures:
        raise RuntimeError(
            f"Kisa piyasa guncellemesinde {failures} hata var"
        )

    print(
        "Islem ajani ve portfoy veritabanlari degistirilmedi.",
        flush=True,
    )


if __name__ == "__main__":
    main()
