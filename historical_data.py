import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


BASE_URL = "https://api.binance.me"
SYMBOL = "BTCTRY"
INTERVAL = "1m"
DAYS = 7
LIMIT = 1000

MINUTE_MS = 60_000

BASE_DIR = Path(__file__).resolve().parent
OUTPUT = BASE_DIR / "btctry_1m_history.csv"
INITIAL_BACKUP = (
    BASE_DIR / "btctry_1m_history_initial_10080.csv"
)

COLUMNS = [
    "open_ms",
    "close_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
]


def utc_text(milliseconds):
    return datetime.fromtimestamp(
        milliseconds / 1000,
        tz=timezone.utc,
    ).strftime("%Y-%m-%d %H:%M UTC")


def validate_candle(row):
    open_ms = int(row["open_ms"])
    close_ms = int(row["close_ms"])

    if open_ms % MINUTE_MS != 0:
        raise ValueError(
            f"Dakika baslangici gecersiz: {open_ms}"
        )

    if close_ms != open_ms + MINUTE_MS - 1:
        raise ValueError(
            f"Mum kapanis zamani gecersiz: {open_ms}"
        )

    open_price = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    close = float(row["close"])
    volume = float(row["volume"])

    if (
        min(open_price, high, low, close) <= 0
        or volume < 0
        or low > min(open_price, close)
        or high < max(open_price, close)
        or high < low
    ):
        raise ValueError(
            f"Gecersiz fiyat veya hacim: {open_ms}"
        )


def parse_candle(item):
    if not isinstance(item, list) or len(item) < 7:
        raise ValueError("Eksik mum verisi")

    row = {
        "open_ms": int(item[0]),
        "close_ms": int(item[6]),
        "open": str(item[1]),
        "high": str(item[2]),
        "low": str(item[3]),
        "close": str(item[4]),
        "volume": str(item[5]),
    }

    validate_candle(row)
    return row


def load_existing():
    if not OUTPUT.exists():
        return {}

    candles = {}

    with OUTPUT.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        reader = csv.DictReader(file)

        if reader.fieldnames != COLUMNS:
            raise ValueError(
                "Mevcut CSV sutunlari beklenen formatta degil"
            )

        for row in reader:
            candle = {
                key: row[key]
                for key in COLUMNS
            }

            candle["open_ms"] = int(candle["open_ms"])
            candle["close_ms"] = int(candle["close_ms"])

            validate_candle(candle)

            open_ms = candle["open_ms"]

            if open_ms in candles:
                raise ValueError(
                    "Mevcut CSV'de tekrar eden dakika: "
                    f"{utc_text(open_ms)}"
                )

            candles[open_ms] = candle

    check_continuity(candles)

    return candles


def check_continuity(candles):
    if not candles:
        return

    times = sorted(candles)

    for previous, current in zip(times, times[1:]):
        if current - previous != MINUTE_MS:
            raise ValueError(
                "Eksik veya tekrar eden dakika: "
                f"{utc_text(previous)} -> "
                f"{utc_text(current)}"
            )


def same_candle(first, second):
    if (
        first["open_ms"] != second["open_ms"]
        or first["close_ms"] != second["close_ms"]
    ):
        return False

    # API ve CSV sayisal degerlerini karsilastir.
    # Metinsel yazim farki (ornegin 1 ve 1.0)
    # tek basina veri degisikligi sayilmaz.
    return all(
        float(first[key]) == float(second[key])
        for key in (
            "open",
            "high",
            "low",
            "close",
            "volume",
        )
    )


def fetch_page(session, end_ms):
    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "limit": LIMIT,
        "endTime": end_ms,
    }

    for attempt in range(1, 4):
        try:
            response = session.get(
                BASE_URL + "/api/v3/klines",
                params=params,
                timeout=25,
            )
            response.raise_for_status()

            data = response.json()

            if not isinstance(data, list):
                raise ValueError(
                    "Beklenmeyen API yaniti"
                )

            return data

        except (
            requests.RequestException,
            ValueError,
        ) as error:
            if attempt == 3:
                raise RuntimeError(
                    f"Veri alinamadi: {error}"
                ) from error

            print(
                f"Baglanti denemesi {attempt}: {error}"
            )
            time.sleep(attempt * 2)


def save_atomically(candles):
    temporary = OUTPUT.with_suffix(".csv.tmp")

    try:
        with temporary.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=COLUMNS,
            )
            writer.writeheader()

            for open_ms in sorted(candles):
                writer.writerow(candles[open_ms])

            file.flush()
            os.fsync(file.fileno())

        temporary.replace(OUTPUT)

    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    if not INITIAL_BACKUP.is_file():
        raise FileNotFoundError(
            "Ilk 10080 mumluk yedek bulunamadi. "
            f"Beklenen: {INITIAL_BACKUP}"
        )

    now_ms = int(time.time() * 1000)
    current_minute = (
        now_ms // MINUTE_MS
    ) * MINUTE_MS

    # Yalnizca tamamen kapanmis mumlar.
    end_ms = current_minute - MINUTE_MS

    existing = load_existing()
    original_count = len(existing)

    if existing:
        first_ms = min(existing)
        last_ms = max(existing)

        if last_ms > end_ms:
            raise ValueError(
                "CSV'de gelecekte veya henuz "
                "tamamlanmamis mum var."
            )

        # Son kayit yeniden indirilip API ile
        # karsilastirilir; eski veri degistirilmez.
        fetch_start_ms = last_ms
    else:
        first_ms = end_ms - (
            DAYS * 24 * 60 - 1
        ) * MINUTE_MS

        last_ms = None
        fetch_start_ms = first_ms

    print("PORTFOLIOAI - GUVENLI VERI GUNCELLEME")
    print(f"Sembol: {SYMBOL} | Aralik: {INTERVAL}")
    print(f"Mevcut mum: {original_count}")
    print(f"Ilk kayit: {utc_text(first_ms)}")
    print(f"Son tamamlanmis mum: {utc_text(end_ms)}")
    print(f"Indirme baslangici: {utc_text(fetch_start_ms)}")

    if last_ms == end_ms:
        print(
            "CSV zaten guncel. Dosya degistirilmedi."
        )
        return

    # Yeni mumlar once yalnizca bellekte tutulur.
    downloaded = {}
    cursor = current_minute - 1
    page_number = 0
    overlap_checked = False

    with requests.Session() as session:
        while cursor >= fetch_start_ms:
            page = fetch_page(session, cursor)

            if not page:
                raise RuntimeError(
                    "API bos sayfa dondurdu. "
                    "CSV degistirilmedi."
                )

            page_number += 1
            oldest_open = None
            added = 0

            for item in page:
                candle = parse_candle(item)
                open_ms = candle["open_ms"]

                if (
                    oldest_open is None
                    or open_ms < oldest_open
                ):
                    oldest_open = open_ms

                if not (
                    fetch_start_ms
                    <= open_ms
                    <= end_ms
                ):
                    continue

                if open_ms in existing:
                    if not same_candle(
                        existing[open_ms],
                        candle,
                    ):
                        raise ValueError(
                            "API ile eski CSV farkli! "
                            f"{utc_text(open_ms)}. "
                            "CSV degistirilmedi."
                        )

                    if open_ms == last_ms:
                        overlap_checked = True

                elif open_ms in downloaded:
                    if not same_candle(
                        downloaded[open_ms],
                        candle,
                    ):
                        raise ValueError(
                            "API sayfalari arasinda "
                            "mum farki var: "
                            f"{utc_text(open_ms)}"
                        )

                else:
                    downloaded[open_ms] = candle
                    added += 1

            if oldest_open is None:
                raise RuntimeError(
                    "Sayfada gecerli mum bulunamadi."
                )

            print(
                f"Sayfa {page_number}: "
                f"{len(page)} mum, "
                f"{added} yeni | "
                f"En eski: {utc_text(oldest_open)}"
            )

            if oldest_open <= fetch_start_ms:
                break

            next_cursor = oldest_open - 1

            if next_cursor >= cursor:
                raise RuntimeError(
                    "Sayfalama ilerlemiyor."
                )

            cursor = next_cursor
            time.sleep(0.2)

    if last_ms is not None and not overlap_checked:
        raise RuntimeError(
            "Son eski mum API ile dogrulanamadi. "
            "CSV degistirilmedi."
        )

    expected_new_start = (
        last_ms + MINUTE_MS
        if last_ms is not None
        else first_ms
    )

    expected_new = (
        (end_ms - expected_new_start) // MINUTE_MS + 1
    )

    missing = [
        open_ms
        for open_ms in range(
            expected_new_start,
            end_ms + 1,
            MINUTE_MS,
        )
        if open_ms not in downloaded
    ]

    print()
    print(f"Beklenen yeni mum: {expected_new}")
    print(f"Indirilen yeni mum: {len(downloaded)}")
    print(f"Eksik dakika: {len(missing)}")

    if missing:
        for open_ms in missing[:10]:
            print(
                "Eksik:",
                utc_text(open_ms),
            )

        raise RuntimeError(
            "Eksik dakika var. "
            "Mevcut CSV degistirilmedi."
        )

    combined = dict(existing)
    combined.update(downloaded)

    check_continuity(combined)

    if (
        len(combined)
        != original_count + expected_new
    ):
        raise RuntimeError(
            "Toplam mum sayisi uyusmuyor. "
            "CSV degistirilmedi."
        )

    # Butun kontrollerden SONRA tek seferde kaydet.
    save_atomically(combined)

    print()
    print("KONTROLLER BASARILI")
    print(f"Toplam mum: {len(combined)}")
    print(f"Kaydedilen CSV: {OUTPUT}")
    print(
        "Ilk 10080 mumluk yedek degistirilmedi."
    )
    print(
        "Calisan ajan ve portfoy veritabanlari "
        "degistirilmedi."
    )


if __name__ == "__main__":
    main()