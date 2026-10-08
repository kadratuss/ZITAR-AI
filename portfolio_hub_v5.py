import msvcrt
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import portfolio_hub_v2 as hub
import market_updater
import market_archive
import long_history_updater
import calendar_archive

ROOT = Path(__file__).resolve().parent
LOCK_PATH = ROOT / "portfolio_hub.lock"

MARKET_INTERVAL_SECONDS = 300
NEWS_INTERVAL_SECONDS = 300
LONG_INTERVAL_SECONDS = 21600


def count_symbols():
    import sqlite3

    with sqlite3.connect(
        ROOT / "learning_lab.db", timeout=20
    ) as db:
        return db.execute("""
            SELECT COUNT(DISTINCT symbol)
            FROM candles
            WHERE interval = '1m'
        """).fetchone()[0]


def run_market_pipeline():
    before = count_symbols()

    print("PIYASA: 1m mumlar guncelleniyor.", flush=True)
    market_updater.main()

    after = count_symbols()

    print("PIYASA: Kisa zaman dilimleri yenileniyor.", flush=True)
    market_archive.main()

    return {
        "new_symbols": max(0, after - before),
        "symbol_count": after,
    }


def run_long_pipeline():
    print("UZUN: Saatlik/gunluk arsiv guncelleniyor.", flush=True)
    long_history_updater.main()

    print("TAKVIM: Haftalik/aylik arsiv yenileniyor.", flush=True)
    calendar_archive.main()

    return "Uzun gecmis ve takvim arsivi tamamlandi"


def run_market_then_long():
    result = run_market_pipeline()

    # Yeni parite varsa uzun gecmisini hemen al.
    # Yoksa uzun gecmis kendi 6 saatlik dongusunde calisir.
    if result["new_symbols"] > 0:
        print(
            "YENI_PARITE: "
            f"{result['new_symbols']} yeni parite; "
            "uzun arsiv hemen guncellenecek.",
            flush=True,
        )
        run_long_pipeline()

    return (
        f"Parite={result['symbol_count']} | "
        f"yeni={result['new_symbols']}"
    )


def acquire_lock():
    lock_file = LOCK_PATH.open("a+b")
    lock_file.seek(0)

    if lock_file.read(1) == b"":
        lock_file.seek(0)
        lock_file.write(b"1")
        lock_file.flush()

    lock_file.seek(0)

    try:
        msvcrt.locking(
            lock_file.fileno(), msvcrt.LK_NBLCK, 1
        )
    except OSError:
        lock_file.close()
        raise RuntimeError(
            "PortfolioAI hub zaten calisiyor; "
            "ikinci kopya baslatilmadi."
        )

    return lock_file


def main():
    lock_file = acquire_lock()

    try:
        hub.initialize()

        print("PORTFOLIOAI HUB v5", flush=True)
        print(
            "Tek baslangic: piyasa + uzun gecmis "
            "+ takvim arsivi + haber.",
            flush=True,
        )
        print(
            "Yeni paritelerin uzun gecmisi hemen alinir.",
            flush=True,
        )
        print(
            "Islem ajani baslatilmaz veya durdurulmaz.",
            flush=True,
        )
        print("Durdurmak icin Ctrl+C.", flush=True)

        # Tek piyasa calisani: kisa ve uzun veri
        # gorevleri birbirinin ustune binmez.
        # Haber ayri calisanda devam eder.
        with ThreadPoolExecutor(max_workers=2) as pool:
            market_future = None
            news_future = None
            next_market = 0.0
            next_news = 0.0
            next_long = 0.0

            try:
                while True:
                    now = time.monotonic()

                    if (
                        market_future is None
                        or market_future.done()
                    ):
                        if now >= next_market:
                            market_future = pool.submit(
                                hub.execute_job,
                                "market_pipeline",
                                run_market_then_long,
                            )
                            next_market = (
                                now + MARKET_INTERVAL_SECONDS
                            )

                        elif now >= next_long:
                            market_future = pool.submit(
                                hub.execute_job,
                                "long_history_pipeline",
                                run_long_pipeline,
                            )
                            next_long = (
                                now + LONG_INTERVAL_SECONDS
                            )

                    if (
                        (news_future is None or news_future.done())
                        and now >= next_news
                    ):
                        news_future = pool.submit(
                            hub.execute_job,
                            "news_collection",
                            hub.collect_and_register_news,
                        )
                        next_news = (
                            now + NEWS_INTERVAL_SECONDS
                        )

                    time.sleep(1)

            except KeyboardInterrupt:
                print(
                    "\nHub durduruluyor; aktif gorevler bekleniyor.",
                    flush=True,
                )

    finally:
        lock_file.seek(0)
        msvcrt.locking(
            lock_file.fileno(), msvcrt.LK_UNLCK, 1
        )
        lock_file.close()


if __name__ == "__main__":
    main()
