from strategy_lab import (
    DATA_FILE,
    FEE_RATE,
    STARTING_CASH,
    TRADE_AMOUNT,
    ema_series,
    load_candles,
)

# EMA'lar arasindaki asgari yuzde fark.
# 0.00 = filtresiz; digerleri arastirma adaylari.
GAP_THRESHOLDS_PCT = (0.00, 0.02, 0.05, 0.10, 0.20)

# Mevcut strategy_lab.py gelistirme sonuclari.
# Ilk kontrol icin kullanilir; bunlar hedef degil.
EXPECTED_BASELINE = {
    1: (-253.47, 116, 9),
    3: (-201.11, 95, 10),
}


def run_gap_strategy(
    candles, fast, slow, start, end,
    confirmation, minimum_gap_pct,
):
    cash = STARTING_CASH
    quantity = 0.0
    entry_cost = 0.0

    closed_trades = 0
    wins = 0
    realized_pnl = 0.0
    peak_equity = STARTING_CASH
    max_drawdown = 0.0

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

        # Filtre yalnizca YENI ALIS icin kullanilir.
        gap_pct = 0.0
        if above:
            gap_pct = (
                (fast_value - slow_value)
                / slow_value
                * 100.0
            )

        if (
            quantity == 0
            and confirmed
            and gap_pct >= minimum_gap_pct
        ):
            spend = min(TRADE_AMOUNT, cash)
            if spend > 0:
                buy_fee = spend * FEE_RATE
                quantity = (spend - buy_fee) / price
                entry_cost = spend
                cash -= spend

        elif quantity > 0 and below:
            gross = quantity * price
            received = gross * (1.0 - FEE_RATE)
            pnl = received - entry_cost

            cash += received
            realized_pnl += pnl
            closed_trades += 1
            if pnl > 0:
                wins += 1

            quantity = 0.0
            entry_cost = 0.0

        # Mevcut laboratuvarla ayni gerileme hesabi.
        equity = cash + quantity * price
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity
        max_drawdown = max(max_drawdown, drawdown)

    # Acik pozisyon satilmis sayilmaz; son fiyattan
    # tahmini satis komisyonu dusulerek degerlenir.
    last_price = candles[end - 1]["close"]
    final_equity = (
        cash + quantity * last_price * (1.0 - FEE_RATE)
    )

    return {
        "net_result": final_equity - STARTING_CASH,
        "closed_trades": closed_trades,
        "wins": wins,
        "open_position": quantity > 0,
        "max_drawdown_pct": max_drawdown * 100.0,
        "realized_pnl": realized_pnl,
    }


def main():
    candles = load_candles()
    prices = [candle["close"] for candle in candles]
    fast = ema_series(prices, 9)
    slow = ema_series(prices, 21)

    warmup = 100
    split = warmup + (len(candles) - warmup) // 2

    print("PORTFOLIOAI - EMA FARKI DENEYI")
    print(f"Veri: {DATA_FILE.name}")
    print(f"Toplam mum: {len(candles)}")
    print(f"Gelistirme mumu: {split - warmup}")
    print("Ayri test donemi bu deneyde kullanilmiyor.")
    print("Alis/satis komisyonu: %0.1 / %0.1")
    print("Alis-satis farki ve fiyat kaymasi dahil degil.")

    if len(candles) != 10080 or split - warmup != 4990:
        raise ValueError(
            "Veri uzunlugu degismis. Once test "
            "donemini yeniden tanimlamaliyiz."
        )

    # Filtresiz hali, mevcut laboratuvarin ayni
    # gelistirme donemi sonucuyla eslesmeli.
    for confirmation in (1, 3):
        result = run_gap_strategy(
            candles, fast, slow, warmup, split,
            confirmation, 0.0,
        )
        expected_net, expected_count, expected_wins = (
            EXPECTED_BASELINE[confirmation]
        )

        if (
            abs(result["net_result"] - expected_net) > 0.02
            or result["closed_trades"] != expected_count
            or result["wins"] != expected_wins
        ):
            raise ValueError(
                "Filtresiz kontrol eslesmedi! "
                f"Onay={confirmation}, "
                f"sonuc={result}. "
                "Esik deneyleri durduruldu."
            )

    print("\nFiltresiz kontrol: BASARILI")

    print(
        "\n"
        f"{'Onay':<7}"
        f"{'EMA farki':>11}"
        f"{'Net TRY':>12}"
        f"{'Islem':>9}"
        f"{'Karli':>8}"
        f"{'Acik':>8}"
        f"{'Max DD %':>11}"
    )
    print("-" * 66)

    for confirmation in (1, 3):
        for threshold in GAP_THRESHOLDS_PCT:
            result = run_gap_strategy(
                candles, fast, slow, warmup, split,
                confirmation, threshold,
            )
            print(
                f"{confirmation:<7}"
                f"{threshold:>10.2f}%"
                f"{result['net_result']:>12.2f}"
                f"{result['closed_trades']:>9}"
                f"{result['wins']:>8}"
                f"{str(result['open_position']):>8}"
                f"{result['max_drawdown_pct']:>11.3f}"
            )

    print(
        "\nYalnizca gelistirme donemi incelendi. "
        "Calisan ajan degistirilmedi."
    )


if __name__ == "__main__":
    main()