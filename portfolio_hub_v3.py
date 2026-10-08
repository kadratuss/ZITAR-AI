import msvcrt
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import portfolio_hub_v2 as hub
import market_updater
import market_archive

ROOT = Path(__file__).resolve().parent
LOCK_PATH = ROOT / "portfolio_hub.lock"

# Her iki gorev kendi zamaninda calisir.
INTERVALS = {
    "market_pipeline": 300,
    "news_collection": 300,
}


def market_pipeline():
    print("PIYASA: Mevcut mumlar guncelleniyor, yeni pariteler ekleniyor.", flush=True)
    market_updater.main()

    print("PIYASA: Zaman dilimi arsivi yenileniyor.", flush=True)
    market_archive.main()

    return "Piyasa guncelleme ve zaman dilimi arsivi turu bitti"


def acquire_lock():
    # Windows'ta ayni ana programin ikinci kopyasini engeller.
    lock_file = LOCK_PATH.open("a+b")
    lock_file.seek(0)

    if lock_file.read(1) == b"":
        lock_file.seek(0)
        lock_file.write(b"1")
        lock_file.flush()

    lock_file.seek(0)

    try:
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_file.close()
        raise RuntimeError(
            "PortfolioAI ana programi zaten calisiyor. "
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
        }

        next_run = {name: 0.0 for name in jobs}
        running = {}

        print("PORTFOLIOAI HUB v3", flush=True)
        print("Tek baslangic: piyasa + arsiv + haber.", flush=True)
        print("Gorevler birbirini beklemeden calisir.", flush=True)
        print("Ayni hub ikinci kez baslatilamaz.", flush=True)
        print("Mevcut islem ajanina dokunulmaz.", flush=True)
        print("Durdurmak icin Ctrl+C.", flush=True)

        with ThreadPoolExecutor(max_workers=2) as pool:
            try:
                while True:
                    current = time.monotonic()

                    for name, function in jobs.items():
                        future = running.get(name)

                        # Ayni gorev tamamlanmadan yeniden baslamaz.
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
                    "\nHub durduruluyor. Baslamis islemler bekleniyor.",
                    flush=True,
                )

    finally:
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        lock_file.close()


if __name__ == "__main__":
    main()
