from strategy_lab import (
    DATA_FILE,
    FEE_RATE,
    STARTING_CASH,
    TRADE_AMOUNT,
    ema_series,
    load_candles,
    run_strategy,
)

THRESHOLDS = (0.00, 0.02, 0.05, 0.10, 0.20)


def analyze(candles, fast, slow, start, end, confirmation, threshold):
    cash = STARTING_CASH
    quantity = 0.0
    entry_cost = 0.0
    buy_fee = 0.0

    closed = 0
    wins = 0
    gross_total = 0.0
    fee_total = 0.0
    net_total = 0.0

    # Bunlar islem sayisi degil, filtre nedeniyle
    # alis yapilmayan uygun sinyal MUMU sayisidir.
    blocked_signal_minutes = 0

    for index in range(start, end):
        signal_index = index - 1
        price = candles[index]["open"]

        fast_value = fast[signal_index]
        slow_value = slow[signal_index]

        above = (
            fast_value is not None
            and slow_value is not None
            and fast_value > slow_value
        )
        below = (
            fast_value is not None
            and slow_value is not None
            and fast_value < slow_value
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

        gap_pct = (
            (fast_value - slow_value) / slow_value * 100.0
            if above else 0.0
        )

        if quantity == 0 and confirmed:
            if gap_pct < threshold:
                blocked_signal_minutes += 1
                continue

            spend = min(TRADE_AMOUNT, cash)
            if spend > 0:
                buy_fee = spend * FEE_RATE
                quantity = (spend - buy_fee) / price
                entry_cost = spend
                cash -= spend

        elif quantity > 0 and below:
            gross_proceeds = quantity * price
            sell_fee = gross_proceeds * FEE_RATE
            received = gross_proceeds - sell_fee

            # Brut sonuc: alis/satis komisyonu haric
            # yalnizca fiyat hareketinin etkisi.
            gross_pnl = gross_proceeds - (entry_cost - buy_fee)
            fees = buy_fee + sell_fee
            net_pnl = received - entry_cost

            gross_total += gross_pnl
            fee_total += fees
            net_total += net_pnl
            closed += 1
            if net_pnl > 0:
                wins += 1

            cash += received
            quantity = 0.0
            entry_cost = 0.0
            buy_fee = 0.0

    open_estimate = None
    if quantity > 0:
        last_price = candles[end - 1]["close"]
        estimated_proceeds = quantity * last_price * (1.0 - FEE_RATE)
        open_estimate = estimated_proceeds - entry_cost

    final_equity = cash
    if quantity > 0:
        final_equity += quantity * candles[end - 1]["close"] * (
            1.0 - FEE_RATE
        )

    return {
        "closed": closed,
        "wins": wins,
        "gross": gross_total,
        "fees": fee_total,
        "net_closed": net_total,
        "open_estimate": open_estimate,
        "net_equity": final_equity - STARTING_CASH,
        "blocked_minutes": blocked_signal_minutes,
    }


def main():
    candles = load_candles()
    prices = [c["close"] for c in candles]
    fast = ema_series(prices, 9)
    slow = ema_series(prices, 21)

    warmup = 100
    split = warmup + (len(candles) - warmup) // 2

    if len(candles) != 10080 or split - warmup != 4990:
        raise ValueError(
            "Veri uzunlugu degismis. Donemleri yeniden "
            "tanimlamadan deneye devam etmiyoruz."
        )

    print("PORTFOLIOAI - EMA FARKI / MALIYET ANALIZI")
    print(f"Veri: {DATA_FILE.name}")
    print("Yalnizca gelistirme donemi: 4990 mum")
    print("Komisyon: alis %0.1 + satis %0.1")
    print("Alis-satis farki ve fiyat kaymasi dahil degil.")

    # Yeni hesaplamanin filtresiz sonucu, mevcut
    # laboratuvarla eslesmezse raporu durdur.
    for confirmation in (1, 3):
        reference = run_strategy(
            candles, fast, slow, warmup, split, confirmation
        )
        check = analyze(
            candles, fast, slow, warmup, split,
            confirmation, 0.0
        )

        if (
            abs(reference["net_result"] - check["net_equity"]) > 0.01
            or reference["closed_trades"] != check["closed"]
            or reference["wins"] != check["wins"]
        ):
            raise ValueError(
                f"Kontrol eslesmedi: onay={confirmation}. "
                "Analiz durduruldu."
            )

    print("\nFiltresiz kontrol: BASARILI")
    print(
        "\nNot: Engellenen mum, engellenen bagimsiz "
        "islem sayisi degildir."
    )

    for confirmation in (1, 3):
        print("\n" + "=" * 91)
        print(f"ONAY: {confirmation} MUM")
        print("=" * 91)
        print(
            f"{'Esik':>7} {'Islem':>7} {'Karli':>6} "
            f"{'Brut TRY':>11} {'Kom. TRY':>11} "
            f"{'Net TRY':>11} {'Acik TRY':>11} "
            f"{'Eng. mum':>9}"
        )
        print("-" * 91)

        for threshold in THRESHOLDS:
            result = analyze(
                candles, fast, slow, warmup, split,
                confirmation, threshold
            )

            open_text = (
                f"{result['open_estimate']:.2f}"
                if result["open_estimate"] is not None
                else "Yok"
            )

            print(
                f"{threshold:>6.2f}% "
                f"{result['closed']:>7} "
                f"{result['wins']:>6} "
                f"{result['gross']:>11.2f} "
                f"{result['fees']:>11.2f} "
                f"{result['net_closed']:>11.2f} "
                f"{open_text:>11} "
                f"{result['blocked_minutes']:>9}"
            )

    print(
        "\nNet TRY yalnizca KAPANMIS islemlerdir. "
        "Acik TRY tahmini degerdir; gerceklesmis sonuca eklenmedi."
    )
    print("Calisan ajan ve ayri test donemi degistirilmedi.")


if __name__ == "__main__":
    main()