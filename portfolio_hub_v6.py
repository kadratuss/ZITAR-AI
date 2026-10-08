import msvcrt
import sqlite3
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

MARKET_SECONDS = 300
NEWS_SECONDS = 300
LONG_SECONDS = 21600


def source_symbols():
    with sqlite3.connect(ROOT / "learning_lab.db", timeout=20) as db:
        return {
            row[0] for row in db.execute("""
                SELECT DISTINCT symbol FROM candles
                WHERE interval = '1m'
            """)
        }


def missing_long_history():
    symbols = source_symbols()

    with sqlite3.connect(ROOT / "long_history.db", timeout=20) as db:
        archived = {
            row[0] for row in db.execute("""
                SELECT symbol
                FROM historical_candles
                WHERE interval IN ('1h', '1d')
                GROUP BY symbol
                HAVING COUNT(DISTINCT interval) = 2
            """)
        }

    return sorted(symbols - archived)


def long_pipeline():
    print("UZUN: Saatlik ve gunluk veriler guncelleniyor.", flush=True)
    long_history_updater.main()

    print("TAKVIM: Haftalik ve aylik mumlar yenileniyor.", flush=True)
    calendar_archive.main()

    return "Uzun gecmis ve takvim arsivi tamamlandi"


def market_pipeline():
    before = source_symbols()

    print("PIYASA: 1m veriler guncelleniyor.", flush=True)

    # market_updater artik hata varsa exception firlatir.
    # Boylece basarisiz tur, basarili diye raporlanmaz.
    market_updater.main()

    print("PIYASA: Kisa zaman dilimleri yenileniyor.", flush=True)
    market_archive.main()

    after = source_symbols()
    new_symbols = sorted(after - before)
    missing = missing_long_history()

    long_done = False

    if new_symbols or missing:
        print(
            "UZUN_ARSIV_TETIKLENDI | "
            f"yeni={','.join(new_symbols) or 'yok'} | "
            f"eksik={','.join(missing) or 'yok'}",
            flush=True,
        )
        long_pipeline()
        long_done = True

    return {
        "symbols": len(after),
        "new": len(new_symbols),
        "long_done": long_done,
    }


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
            "PortfolioAI hub zaten calisiyor; ikinci kopya acilmadi."
        )

    return lock_file


def main():
    lock_file = acquire_lock()

    try:
        hub.initialize()

        print("PORTFOLIOAI HUB v6", flush=True)
        print(
            "Piyasa + kisa/uzun arsiv + haftalik/aylik + haber",
            flush=True,
        )
        print(
            "Kisa piyasa hatalari ust goreve aktarilir.",
            flush=True,
        )
        print(
            "Yeni parite uzun arsivi hemen alinir; "
            "gereksiz ikinci tur baslatilmaz.",
            flush=True,
        )
        print(
            "Islem ajani baslatilmaz veya durdurulmaz.",
            flush=True,
        )
        print("Durdurmak icin Ctrl+C.", flush=True)

        with ThreadPoolExecutor(max_workers=2) as pool:
            market_future = None
            news_future = None
            next_market = 0.0
            next_news = 0.0

            # Ilk piyasa turu yeni/eksik pariteleri zaten
            # kontrol edecek. Uzun arşivi hemen ikinci kez
            # calistirmamak icin sayac simdi baslar.
            next_long = time.monotonic() + LONG_SECONDS

            try:
                while True:
                    now = time.monotonic()

                    if market_future is not None and market_future.done():
                        try:
                            result = market_future.result()
                            if isinstance(result, dict) and result.get(
                                "long_done"
                            ):
                                next_long = (
                                    time.monotonic() + LONG_SECONDS
                                )
                        except Exception as exc:
                            print(
                                f"PIYASA_GOREV_HATASI: {exc}",
                                flush=True,
                            )
                        market_future = None

                    if market_future is None:
                        if now >= next_market:
                            market_future = pool.submit(
                                market_pipeline
                            )
                            next_market = now + MARKET_SECONDS
                        elif now >= next_long:
                            market_future = pool.submit(
                                long_pipeline
                            )
                            next_long = now + LONG_SECONDS

                    if news_future is not None and news_future.done():
                        try:
                            news_future.result()
                        except Exception as exc:
                            print(
                                f"HABER_GOREV_HATASI: {exc}",
                                flush=True,
                            )
                        news_future = None

                    if news_future is None and now >= next_news:
                        news_future = pool.submit(
                            hub.collect_and_register_news
                        )
                        next_news = now + NEWS_SECONDS

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
