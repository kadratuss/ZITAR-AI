import csv
from datetime import datetime, timezone
from pathlib import Path

from strategy_lab import (
    DATA_FILE,
    FEE_RATE,
    STARTING_CASH,
    TRADE_AMOUNT,
    ema_series,
    load_candles,
)

BASE_DIR = Path(__file__).resolve().parent
REPORT_DIR = BASE_DIR / "trade_reports"


def utc_text(milliseconds):
    return datetime.fromtimestamp(
        milliseconds / 1000,
        tz=timezone.utc,
    ).isoformat()


def analyze_period(candles, fast, slow, start, end, confirmation):
    cash = STARTING_CASH
    quantity = 0.0
    entry = None
    trades = []

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
                buy_fee = spend * FEE_RATE
                quantity = (spend - buy_fee) / price
                cash -= spend

                entry = {
                    "entry_time": utc_text(
                        candles[index]["open_ms"]
                    ),
                    "entry_price": price,
                    "quantity": quantity,
                    "entry_cost": spend,
                    "buy_fee": buy_fee,
                    "entry_index": index,
                }

        elif quantity > 0 and below:
            gross = quantity * price
            sell_fee = gross * FEE_RATE
            received = gross - sell_fee

            gross_pnl = gross - (
                entry["entry_cost"] - entry["buy_fee"]
            )
            net_pnl = received - entry["entry_cost"]

            trades.append({
                "entry_time": entry["entry_time"],
                "exit_time": utc_text(
                    candles[index]["open_ms"]
                ),
                "entry_price": entry["entry_price"],
                "exit_price": price,
                "quantity": quantity,
                "entry_cost": entry["entry_cost"],
                "gross_proceeds": gross,
                "buy_fee": entry["buy_fee"],
                "sell_fee": sell_fee,
                "total_fees": entry["buy_fee"] + sell_fee,
                "gross_pnl": gross_pnl,
                "net_pnl": net_pnl,
                "holding_minutes": (
                    index - entry["entry_index"]
                ),
                "status": "CLOSED",
            })

            cash += received
            quantity = 0.0
            entry = None

    open_position = None

    if quantity > 0:
        last_price = candles[end - 1]["close"]
        estimated_gross = quantity * last_price
        estimated_sell_fee = estimated_gross * FEE_RATE

        open_position = {
            "entry_time": entry["entry_time"],
            "entry_price": entry["entry_price"],
            "quantity": quantity,
            "entry_cost": entry["entry_cost"],
            "buy_fee": entry["buy_fee"],
            "last_price": last_price,
            "estimated_exit_fee": estimated_sell_fee,
            "estimated_net_pnl": (
                estimated_gross
                - estimated_sell_fee
                - entry["entry_cost"]
            ),
            "status": "OPEN_ESTIMATE",
        }

    return trades, open_position


def save_csv(path, rows, columns):
    with path.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=columns
        )
        writer.writeheader()
        writer.writerows(rows)


def print_summary(label, trades, open_position):
    gross = sum(t["gross_pnl"] for t in trades)
    fees = sum(t["total_fees"] for t in trades)
    net = sum(t["net_pnl"] for t in trades)
    wins = sum(t["net_pnl"] > 0 for t in trades)

    print()
    print(label)
    print("-" * 45)
    print(f"Kapanan islem: {len(trades)}")
    print(f"Karli kapanan: {wins}")
    print(f"Komisyon oncesi sonuc: {gross:.2f} TRY")
    print(f"Toplam komisyon: {fees:.2f} TRY")
    print(f"Gerceklesmis net sonuc: {net:.2f} TRY")

    if open_position:
        print(
            "Acik pozisyon tahmini net sonucu: "
            f"{open_position['estimated_net_pnl']:.2f} TRY"
        )
        print(
            "NOT: Acik pozisyon gerceklesmis kara "
            "veya zarara eklenmedi."
        )
    else:
        print("Acik pozisyon: Yok")


def main():
    candles = load_candles()
    prices = [c["close"] for c in candles]

    fast = ema_series(prices, 9)
    slow = ema_series(prices, 21)

    warmup = 100
    split = warmup + (len(candles) - warmup) // 2

    REPORT_DIR.mkdir(exist_ok=True)

    print("PORTFOLIOAI - ISLEM RAPORU")
    print(f"Veri: {DATA_FILE.name}")
    print(f"Mum sayisi: {len(candles)}")
    print("Komisyon: alis %0.1, satis %0.1")
    print(
        "Sinyal kapanmis mumdan; "
        "islem sonraki mum acilisindan."
    )

    periods = [
        ("development", warmup, split),
        ("holdout", split, len(candles)),
    ]

    strategies = [
        ("ema_9_21_v02", 1),
        ("ema_9_21_confirm3", 3),
    ]

    columns = [
        "entry_time",
        "exit_time",
        "entry_price",
        "exit_price",
        "quantity",
        "entry_cost",
        "gross_proceeds",
        "buy_fee",
        "sell_fee",
        "total_fees",
        "gross_pnl",
        "net_pnl",
        "holding_minutes",
        "status",
    ]

    open_columns = [
        "entry_time",
        "entry_price",
        "quantity",
        "entry_cost",
        "buy_fee",
        "last_price",
        "estimated_exit_fee",
        "estimated_net_pnl",
        "status",
    ]

    for period_name, start, end in periods:
        for strategy_name, confirmation in strategies:
            trades, open_position = analyze_period(
                candles,
                fast,
                slow,
                start,
                end,
                confirmation,
            )

            name = f"{period_name}_{strategy_name}"

            save_csv(
                REPORT_DIR / f"{name}_trades.csv",
                trades,
                columns,
            )

            if open_position:
                save_csv(
                    REPORT_DIR / f"{name}_open.csv",
                    [open_position],
                    open_columns,
                )

            print_summary(
                name,
                trades,
                open_position,
            )

    print()
    print(f"Rapor klasoru: {REPORT_DIR}")
    print(
        "Test raporu tamamlandi. "
        "Calisan ajana dokunulmadi."
    )


if __name__ == "__main__":
    main()