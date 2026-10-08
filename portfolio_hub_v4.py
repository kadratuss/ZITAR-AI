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

# Kisa piyasa ve haber: 5 dakikada bir.
# Uzun gecmis ve takvim arsivi: 6 saatte bir.
INTERVALS = {
    "market_pipeline": 300,
    "news_collection": 300,
    "long_history_pipeline": 21600,
}


def market_pipeline():
    print(
        "PIYASA: 1m verileri guncelleniyor.",
        flush=True,
    )
    market_updater.main()

    print(
        "PIYASA: Kisa zaman dilimleri yenileniyor.",
        flush=True,
    )
    market_archive.main()

    return "Kisa piyasa turu bitti; parite hata satirlarini kontrol et"


def long_history_pipeline():
    print(
        "UZUN_GECMIS: Saatlik ve gunluk mumlar guncelleniyor.",
        flush=True,
    )
    long_history_updater.main()

    print(
        "TAKVIM: Haftalik ve aylik mumlar yenileniyor.",
        flush=True,
    )
    calendar_archive.main()

    return "Uzun gecmis ve takvim arsivi turu bitti"


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
            lock_file.fileno(),
            msvcrt.LK_NBLCK,
            1,
        )
    except OSError:
        lock_file.close()
        raise RuntimeError(
            "PortfolioAI hub zaten calisiyor. "
            "Ikinci kopya baslatilmadi."
        )

    return lock_file


def main():
    lock_file = acquire_lock()

    try:
        hub.initialize()

        jobs = {
            "market_pipeline": market_pipeline,
            "news_collection": hub.collect_and_register_news,
            "long_history_pipeline": long_history_pipeline,
        }

        next_run = {name: 0.0 for name in jobs}
        running = {}

        print("PORTFOLIOAI HUB v4", flush=True)
        print(
            "Tek baslangic: kisa piyasa + uzun gecmis "
            "+ haftalik/aylik arsiv + haber.",
            flush=True,
        )
        print(
            "Gorevler birbirini beklemeden calisir.",
            flush=True,
        )
        print(
            "Islem ajani ikinci kez baslatilmaz.",
            flush=True,
        )
        print("Durdurmak icin Ctrl+C.", flush=True)

        with ThreadPoolExecutor(max_workers=3) as pool:
            try:
                while True:
                    current = time.monotonic()

                    for name, function in jobs.items():
                        future = running.get(name)

                        if future is not None and not future.done():
                            continue

                        if current >= next_run[name]:
                            running[name] = pool.submit(
                                hub.execute_job,
                                name,
                                function,
                            )
                            next_run[name] = (
                                current + INTERVALS[name]
                            )

                    time.sleep(1)

            except KeyboardInterrupt:
                print(
                    "\nHub durduruluyor; baslamis "
                    "islemler bekleniyor.",
                    flush=True,
                )

    finally:
        lock_file.seek(0)
        msvcrt.locking(
            lock_file.fileno(),
            msvcrt.LK_UNLCK,
            1,
        )
        lock_file.close()


if __name__ == "__main__":
    main()
