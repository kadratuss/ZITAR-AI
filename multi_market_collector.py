import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from historical_data import parse_candle
from market_engine import BASE_URL, get_market_data

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "learning_lab.db"
MINUTE_MS = 60_000
DAYS = 7
SYMBOLS_PER_RUN = 2
PAGE_LIMIT = 1000


def utc_text(ms):
    return datetime.fromtimestamp(
        ms / 1000, timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")


def fetch_page(session, symbol, start_ms, end_ms):
    params = {
        "symbol": symbol,
        "interval": "1m",
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": PAGE_LIMIT,
    }

    for attempt in range(1, 4):
        try:
            response = session.get(
                BASE_URL + "/api/v3/klines",
                params=params,
                timeout=25,
            )

            # Hiz sinirina takilirsak zorlamadan dur.
            if response.status_code in (418, 429):
                raise RuntimeError(
                    f"API hiz/erisim siniri: HTTP {response.status_code}"
                )

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                raise ValueError("Beklenmeyen mum API yaniti")

            return data

        except RuntimeError:
            raise
        except (requests.RequestException, ValueError) as exc:
            if attempt == 3:
                raise RuntimeError(
                    f"{symbol} veri alinamadi: {exc}"
                ) from exc

            time.sleep(attempt * 2)


def download_symbol(session, symbol, start_ms, end_ms):
    candles = {}
    cursor = start_ms
    page_count = 0

    while cursor <= end_ms:
        page = fetch_page(session, symbol, cursor, end_ms)

        if not page:
            break

        page_count += 1
        previous_open = None

        for item in page:
            candle = parse_candle(item)
            open_ms = int(candle["open_ms"])

            if not start_ms <= open_ms <= end_ms:
                continue

            if previous_open is not None and open_ms <= previous_open:
                raise ValueError(
                    f"{symbol}: API sayfasi sirali degil"
                )

            previous_open = open_ms

            if open_ms in candles:
                raise ValueError(
                    f"{symbol}: tekrar eden mum {utc_text(open_ms)}"
                )

            candles[open_ms] = candle

        if previous_open is None:
            raise ValueError(
                f"{symbol}: API sayfasi istenen aralikta mum icermiyor"
            )

        next_cursor = previous_open + MINUTE_MS

        if next_cursor <= cursor:
            raise ValueError(
                f"{symbol}: sayfalama ilerlemiyor"
            )

        cursor = next_cursor
        time.sleep(0.2)

    if not candles:
        raise ValueError(
            f"{symbol}: istenen aralikta mum bulunamadi"
        )

    times = sorted(candles)

    for previous, current in zip(times, times[1:]):
        if current - previous != MINUTE_MS:
            raise ValueError(
                f"{symbol}: eksik dakika: "
                f"{utc_text(previous)} -> {utc_text(current)}"
            )

    if times[-1] != end_ms:
        raise ValueError(
            f"{symbol}: son kapanmis muma ulasilamadi; "
            f"son veri {utc_text(times[-1])}"
        )

    return [candles[t] for t in times], page_count


def check_schema(db):
    columns = {
        row[1] for row in db.execute(
            "PRAGMA table_info(candles)"
        )
    }

    required = {
        "symbol", "interval", "open_time_ms",
        "close_time_ms", "open_price", "high_price",
        "low_price", "close_price", "volume",
    }

    missing = required - columns

    if missing:
        raise RuntimeError(
            "learning_lab.db mum tablosu beklenen yapida degil: "
            + ", ".join(sorted(missing))
        )


def main():
    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"Mevcut ogrenme veritabani bulunamadi: {DB_PATH}"
        )

    market = get_market_data()
    pairs = [
        item["symbol"]
        for item in market["pairs"]
    ]

    if not pairs:
        raise RuntimeError("Piyasa motoru parite dondurmedi")

    with sqlite3.connect(DB_PATH, timeout=20) as db:
        db.execute("PRAGMA busy_timeout=20000")
        check_schema(db)

        existing = {
            row[0] for row in db.execute("""
                SELECT DISTINCT symbol
                FROM candles
                WHERE interval = '1m'
            """)
        }

    selected = [
        symbol for symbol in pairs
        if symbol not in existing
    ][:SYMBOLS_PER_RUN]

    print("PORTFOLIOAI - COKLU PARITE VERI TOPLAMA")
    print(f"Piyasa motorundaki parite: {len(pairs)}")
    print(f"Arsivde zaten bulunan: {len(existing)}")
    print(f"Bu calismada secilen: {', '.join(selected) or 'YOK'}")

    if not selected:
        print("Yeni parite yok; mevcut veriler degistirilmedi.")
        return

    # Tum pariteler icin ayni kapanmis dakika siniri.
    current_minute = (
        int(time.time() * 1000) // MINUTE_MS
    ) * MINUTE_MS
    end_ms = current_minute - MINUTE_MS
    start_ms = end_ms - (
        DAYS * 24 * 60 - 1
    ) * MINUTE_MS

    print(
        f"Veri araligi: {utc_text(start_ms)} "
        f"-> {utc_text(end_ms)}"
    )

    with requests.Session() as session:
        for symbol in selected:
            print(f"\nINDIRILIYOR: {symbol}", flush=True)

            try:
                candles, pages = download_symbol(
                    session, symbol, start_ms, end_ms
                )

                # Indirme ve sureklilik kontrolleri bitmeden
                # bu sembol icin veritabanina yazilmaz.
                with sqlite3.connect(DB_PATH, timeout=20) as db:
                    db.execute("PRAGMA busy_timeout=20000")
                    check_schema(db)

                    db.executemany("""
                        INSERT OR IGNORE INTO candles (
                            symbol, interval, open_time_ms,
                            close_time_ms, open_price, high_price,
                            low_price, close_price, volume
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        (
                            symbol,
                            "1m",
                            int(c["open_ms"]),
                            int(c["close_ms"]),
                            c["open"],
                            c["high"],
                            c["low"],
                            c["close"],
                            c["volume"],
                        )
                        for c in candles
                    ])

                    db.commit()

                print(
                    f"TAMAM: {symbol} | "
                    f"mum={len(candles)} | sayfa={pages} | "
                    f"ilk={utc_text(int(candles[0]['open_ms']))}",
                    flush=True
                )

            except Exception as exc:
                print(
                    f"HATA: {symbol} | "
                    f"{type(exc).__name__}: {exc}",
                    flush=True
                )

                # API hiz sinirinda diger pariteye gecme.
                if "API hiz/erisim siniri" in str(exc):
                    break

    print("\nTOPLAMA_TURU_BITTI")
    print("Mevcut BTCTRY mumlari ve islem ajani degistirilmedi.")
    print(
        "Sonraki adim: toplanan pariteleri zaman dilimi "
        "arsivine ve tek baslangic sistemine baglamak."
    )


if __name__ == "__main__":
    main()
