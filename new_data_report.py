import csv
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

RESEARCH_FILE = (
    BASE_DIR / "btctry_1m_history_initial_10080.csv"
)
CURRENT_FILE = BASE_DIR / "btctry_1m_history.csv"

MINUTE_MS = 60_000

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


def read_candles(path):
    if not path.is_file():
        raise FileNotFoundError(
            f"Dosya bulunamadi: {path}"
        )

    rows = []

    with path.open(
        "r", newline="", encoding="utf-8"
    ) as file:
        reader = csv.DictReader(file)

        if reader.fieldnames != COLUMNS:
            raise ValueError(
                f"Beklenmeyen CSV sutunlari: {path.name}"
            )

        for row in reader:
            candle = {
                key: row[key] for key in COLUMNS
            }

            candle["open_ms"] = int(
                candle["open_ms"]
            )
            candle["close_ms"] = int(
                candle["close_ms"]
            )

            if (
                candle["open_ms"] % MINUTE_MS != 0
                or candle["close_ms"]
                != candle["open_ms"] + MINUTE_MS - 1
            ):
                raise ValueError(
                    "Gecersiz mum zamani: "
                    f"{path.name}"
                )

            open_price = float(candle["open"])
            high = float(candle["high"])
            low = float(candle["low"])
            close = float(candle["close"])
            volume = float(candle["volume"])

            if (
                min(open_price, high, low, close) <= 0
                or volume < 0
                or low > min(open_price, close)
                or high < max(open_price, close)
            ):
                raise ValueError(
                    "Gecersiz fiyat veya hacim: "
                    f"{path.name}"
                )

            rows.append(candle)

    if not rows:
        raise ValueError(
            f"CSV bos: {path.name}"
        )

    for previous, current in zip(
        rows, rows[1:]
    ):
        if (
            current["open_ms"] - previous["open_ms"]
            != MINUTE_MS
        ):
            raise ValueError(
                "Eksik, tekrar eden veya sirasi "
                "bozuk dakika: "
                f"{path.name} | "
                f"{utc_text(previous['open_ms'])} -> "
                f"{utc_text(current['open_ms'])}"
            )

    return rows


def main():
    research = read_candles(RESEARCH_FILE)
    current = read_candles(CURRENT_FILE)

    if len(research) != 10080:
        raise ValueError(
            "Sabit arastirma dosyasi 10080 mum "
            "icermiyor. Rapor durduruldu."
        )

    if len(current) < len(research):
        raise ValueError(
            "Guncel CSV arastirma verisinden kisa."
        )

    # Ilk donem, yalnizca zaman olarak degil,
    # tum CSV alanlariyla birebir ayni olmali.
    for index, old_row in enumerate(research):
        if old_row != current[index]:
            raise ValueError(
                "Sabit arastirma verisi ile guncel "
                "CSV farkli! Ilk fark: "
                f"{utc_text(old_row['open_ms'])}"
            )

    new_rows = current[len(research):]

    print("PORTFOLIOAI - YENI VERI RAPORU")
    print("=" * 48)
    print(f"Arastirma dosyasi: {RESEARCH_FILE.name}")
    print(f"Guncel dosya:     {CURRENT_FILE.name}")
    print()
    print(f"Sabit arastirma mumu: {len(research)}")
    print(f"Yeni donem mumu:     {len(new_rows)}")
    print(f"Toplam mum:          {len(current)}")
    print()
    print(
        "Arastirma baslangici: "
        f"{utc_text(research[0]['open_ms'])}"
    )
    print(
        "Arastirma bitisi:     "
        f"{utc_text(research[-1]['open_ms'])}"
    )

    if new_rows:
        expected_first = (
            research[-1]["open_ms"] + MINUTE_MS
        )

        if new_rows[0]["open_ms"] != expected_first:
            raise ValueError(
                "Yeni donem arastirma doneminin "
                "hemen ardindan baslamiyor."
            )

        print()
        print(
            "Yeni donem baslangici: "
            f"{utc_text(new_rows[0]['open_ms'])}"
        )
        print(
            "Yeni donem bitisi:     "
            f"{utc_text(new_rows[-1]['open_ms'])}"
        )
        print(
            "Yeni donem suresi:    "
            f"{len(new_rows) / 60:.2f} saat"
        )
    else:
        print()
        print("Henuz yeni mum eklenmemis.")

    print()
    print("KONTROL: Ilk 10080 mum birebir ayni.")
    print("KONTROL: Tum CSV'de eksik dakika yok.")
    print(
        "Bu rapor strateji secmez ve "
        "dosyalari degistirmez."
    )


if __name__ == "__main__":
    main()