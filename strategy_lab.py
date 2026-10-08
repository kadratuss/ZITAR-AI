import csv
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = (
    Path(__file__).resolve().parent
    / "btctry_1m_history_initial_10080.csv"
)
SYMBOL = "BTCTRY"
INTERVAL = "1m"

FEE_RATE = 0.001
STARTING_CASH = 10000.0
TRADE_AMOUNT = 1000.0
MINUTE_MS = 60_000


def utc_text(milliseconds):
    return datetime.fromtimestamp(
        milliseconds / 1000,
        tz=timezone.utc,
    ).strftime("%Y-%m-%d %H:%M UTC")


def load_candles():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Veri dosyasi bulunamadi: {DATA_FILE}"
        )

    candles = []

    with DATA_FILE.open(
        "r", newline="", encoding="utf-8"
    ) as file:
        reader = csv.DictReader(file)

        required = {
            "open_ms", "close_ms",
            "open", "high", "low", "close", "volume"
        }

        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                "CSV dosyasinda gerekli sutunlar eksik"
            )

        for row in reader:
            candle = {
                "open_ms": int(row["open_ms"]),
                "close_ms": int(row["close_ms"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }

            if (
                candle["open"] <= 0
                or candle["high"] <= 0
                or candle["low"] <= 0
                or candle["close"] <= 0
                or candle["volume"] < 0
            ):
                raise ValueError(
                    "CSV dosyasinda gecersiz fiyat veya hacim"
                )

            if candle["close_ms"] <= candle["open_ms"]:
                raise ValueError("Gecersiz mum zamani")

            candles.append(candle)

    candles.sort(key=lambda candle: candle["open_ms"])

    if len(candles) < 300:
        raise ValueError("Test icin yeterli mum yok")

    for previous, current in zip(
        candles, candles[1:]
    ):
        difference = (
            current["open_ms"] - previous["open_ms"]
        )

        if difference != MINUTE_MS:
            raise ValueError(
                "Eksik veya tekrar eden dakika: "
                f"{utc_text(previous['open_ms'])} -> "
                f"{utc_text(current['open_ms'])}"
            )

    return candles


def ema_series(prices, period):
    results = [None] * len(prices)

    seed = sum(prices[:period]) / period
    results[period - 1] = seed

    multiplier = 2.0 / (period + 1)
    previous = seed

    for index in range(period, len(prices)):
        previous = (
            prices[index] - previous
        ) * multiplier + previous

        results[index] = previous

    return results


def run_strategy(
    candles,
    fast,
    slow,
    start,
    end,
    confirmation,
):
    cash = STARTING_CASH
    quantity = 0.0
    entry_cost = 0.0

    closed_trades = 0
    wins = 0
    realized_pnl = 0.0

    peak_equity = STARTING_CASH
    max_drawdown = 0.0

    # Karar onceki kapanmis mumdan alinir.
    # Islem sonraki mumun acilis fiyatindan
    # varsayimsal olarak gerceklestirilir.
    for index in range(start, end):
        signal_index = index - 1
        price = candles[index]["open"]

        above = (
            fast[signal_index] is not None
            and slow[signal_index] is not None
            and fast[signal_index] > slow[signal_index]
        )

        below = (
            fast[signal_index] is not None
            and slow[signal_index] is not None
            and fast[signal_index] < slow[signal_index]
        )

        confirmed = above

        if confirmation > 1:
            confirmed = all(
                fast[j] is not None
                and slow[j] is not None
                and fast[j] > slow[j]
                for j in range(
                    signal_index - confirmation + 1,
                    signal_index + 1,
                )
            )

        if quantity == 0 and confirmed:
            spend = min(TRADE_AMOUNT, cash)

            if spend > 0:
                fee = spend * FEE_RATE

                quantity = (
                    spend - fee
                ) / price

                entry_cost = spend
                cash -= spend

        elif quantity > 0 and below:
            gross = quantity * price
            received = gross * (1 - FEE_RATE)
            pnl = received - entry_cost

            cash += received
            realized_pnl += pnl
            closed_trades += 1

            if pnl > 0:
                wins += 1

            quantity = 0.0
            entry_cost = 0.0

        equity = cash + quantity * price

        peak_equity = max(
            peak_equity, equity
        )

        drawdown = (
            peak_equity - equity
        ) / peak_equity

        max_drawdown = max(
            max_drawdown, drawdown
        )

    # Test sonunda acik pozisyon varsa
    # satis komisyonu dusulerek degerlenir.
    # Gercek bir satis kaydi olusturulmaz.
    last_price = candles[end - 1]["close"]

    final_equity = (
        cash
        + quantity * last_price * (1 - FEE_RATE)
    )

    return {
        "net_result": final_equity - STARTING_CASH,
        "closed_trades": closed_trades,
        "wins": wins,
        "open_position": quantity > 0,
        "max_drawdown_pct": max_drawdown * 100,
        "realized_pnl": realized_pnl,
    }


def show_result(label, result):
    print()
    print(label)
    print("-" * 45)

    print(
        f"Net sonuc: "
        f"{result['net_result']:.2f} TRY"
    )

    print(
        f"Kapanan islem: "
        f"{result['closed_trades']}"
    )

    print(
        f"Karli kapanan: "
        f"{result['wins']}"
    )

    print(
        f"Acik pozisyon: "
        f"{result['open_position']}"
    )

    print(
        f"Maksimum gerileme: "
        f"%{result['max_drawdown_pct']:.3f}"
    )


def main():
    candles = load_candles()

    prices = [
        candle["close"]
        for candle in candles
    ]

    fast = ema_series(prices, 9)
    slow = ema_series(prices, 21)

    warmup = 100

    split = (
        warmup
        + (len(candles) - warmup) // 2
    )

    print("=" * 45)
    print("PORTFOLIOAI - STRATEJI LABORATUVARI")
    print("=" * 45)

    print(f"Kaynak dosya: {DATA_FILE.name}")
    print(f"Sembol: {SYMBOL} | Aralik: {INTERVAL}")
    print(f"Toplam mum: {len(candles)}")

    print(
        f"Veri baslangici: "
        f"{utc_text(candles[0]['open_ms'])}"
    )

    print(
        f"Veri bitisi: "
        f"{utc_text(candles[-1]['open_ms'])}"
    )

    print(
        "Komisyon: alis %0.1 + satis %0.1"
    )

    print(
        "Sinyal: kapanis | "
        "Islem: sonraki mum acilisi"
    )

    print(
        "Not: Alis-satis farki ve "
        "fiyat kaymasi modellenmedi."
    )

    periods = [
        (
            "GELISTIRME DONEMI",
            warmup,
            split,
        ),
        (
            "AYRI TEST DONEMI",
            split,
            len(candles),
        ),
    ]

    for period_name, start, end in periods:
        print()
        print("=" * 45)
        print(period_name)
        print("=" * 45)

        print(
            f"Baslangic: "
            f"{utc_text(candles[start]['open_ms'])}"
        )

        print(
            f"Bitis: "
            f"{utc_text(candles[end - 1]['open_ms'])}"
        )

        print(f"Test edilen mum: {end - start}")

        baseline = run_strategy(
            candles,
            fast,
            slow,
            start,
            end,
            confirmation=1,
        )

        candidate = run_strategy(
            candles,
            fast,
            slow,
            start,
            end,
            confirmation=3,
        )

        show_result(
            "EMA 9/21 - BASLANGIC v0.2",
            baseline,
        )

        show_result(
            "EMA 9/21 - 3 MUM ONAYLI ADAY",
            candidate,
        )

    print()
    print(
        "Test tamamlandi. "
        "Calisan ajanin stratejisi degistirilmedi."
    )


if __name__ == "__main__":
    main()