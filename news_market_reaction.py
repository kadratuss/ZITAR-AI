import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MINUTE = 60_000
NEWS_IDS = (30, 28, 25, 24)
WINDOWS = (5, 15, 60, 240)


def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def pct(start, end):
    if start == 0:
        return "HESAPLANAMADI"
    return f"{((end / start) - 1) * 100:+.4f}%"


def main():
    with sqlite3.connect(ROOT / "ai_core.db", timeout=10) as db:
        news = db.execute("""
            SELECT id, title, published_at
            FROM knowledge
            WHERE id IN (30, 28, 25, 24)
            ORDER BY id DESC
        """).fetchall()

    with sqlite3.connect(ROOT / "learning_lab.db", timeout=10) as db:
        candles = db.execute("""
            SELECT open_time_ms, close_price, volume
            FROM candles
            WHERE symbol = 'BTCTRY' AND interval = '1m'
            ORDER BY open_time_ms
        """).fetchall()

    market = {
        int(t): (Decimal(close), Decimal(volume))
        for t, close, volume in candles
    }

    for source_id, title, published in news:
        published_ms = int(
            parsedate_to_datetime(published)
            .astimezone(timezone.utc)
            .timestamp() * 1000
        )

        # Yayin anindan once TAMAMEN kapanmis son mum.
        # Mum kapanis zamani open_time_ms + 60_000 - 1.
        baseline_t = (published_ms // MINUTE) * MINUTE - MINUTE

        # Yayin sonrasinda baslayan ilk TAM mum.
        first_after_t = (
            (published_ms + MINUTE - 1) // MINUTE
        ) * MINUTE

        print(f"\n{'=' * 65}")
        print(f"HABER {source_id}: {title}")
        print("YAYIN:", utc(published_ms))
        print("BAZ_MUM:", utc(baseline_t))
        print("ILK_TAM_SONRA_MUM:", utc(first_after_t))

        if baseline_t not in market:
            print("SONUC: BAZ_FIYAT_YOK")
            continue

        baseline = market[baseline_t][0]
        before_t = baseline_t - 60 * MINUTE

        if before_t in market:
            print(
                "YAYIN_ONCESI_60DK:",
                pct(market[before_t][0], baseline)
            )
        else:
            print("YAYIN_ONCESI_60DK: VERI_YOK")

        print("BAZ_FIYAT_BTCTRY:", baseline)

        for minutes in WINDOWS:
            times = [
                first_after_t + i * MINUTE
                for i in range(minutes)
            ]
            if any(t not in market for t in times):
                print(f"SONRAKI_{minutes}DK: EKSIK_VERI")
                continue

            end_price = market[times[-1]][0]
            volume = sum(
                (market[t][1] for t in times),
                Decimal("0")
            )

            print(
                f"SONRAKI_{minutes}DK:",
                f"FIYAT_DEGISIMI={pct(baseline, end_price)}",
                f"BTC_HACIM={volume:.8f}",
                f"BITIS_MUMU={utc(times[-1])}"
            )

    print("\nUYARI: Bunlar yayin saati cevresindeki BTCTRY")
    print("hareketleridir; haberin harekete neden oldugunu kanitlamaz.")
    print("Yayin mumunun icindeki ilk saniyeler olcume dahil degildir.")


if __name__ == "__main__":
    main()
