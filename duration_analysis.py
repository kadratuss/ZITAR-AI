import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPORT_DIR = BASE_DIR / "trade_reports"

STRATEGIES = {
    "EMA 9/21 v0.2": "development_ema_9_21_v02_trades.csv",
    "EMA 9/21 - 3 mum onayi": (
        "development_ema_9_21_confirm3_trades.csv"
    ),
}

GROUPS = [
    ("0-2 dakika", 0, 2),
    ("3-5 dakika", 3, 5),
    ("6-10 dakika", 6, 10),
    ("11-20 dakika", 11, 20),
    ("21-60 dakika", 21, 60),
    ("61+ dakika", 61, float("inf")),
]


def read_trades(filename):
    path = REPORT_DIR / filename

    if not path.is_file():
        raise FileNotFoundError(f"Rapor bulunamadi: {path}")

    trades = []

    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        required = {
            "holding_minutes",
            "gross_pnl",
            "total_fees",
            "net_pnl",
            "status",
        }

        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                f"CSV sutunlari eksik: {path.name}"
            )

        for row in reader:
            if row["status"] != "CLOSED":
                continue

            trades.append({
                "minutes": int(row["holding_minutes"]),
                "gross": float(row["gross_pnl"]),
                "fees": float(row["total_fees"]),
                "net": float(row["net_pnl"]),
            })

    return trades


def show_group(label, trades):
    count = len(trades)
    gross = sum(t["gross"] for t in trades)
    fees = sum(t["fees"] for t in trades)
    net = sum(t["net"] for t in trades)
    wins = sum(t["net"] > 0 for t in trades)

    print(
        f"{label:<17}"
        f"{count:>7}"
        f"{wins:>8}"
        f"{gross:>13.2f}"
        f"{fees:>13.2f}"
        f"{net:>13.2f}"
    )


def main():
    print("PORTFOLIOAI - ISLEM SURESI ANALIZI")
    print("Yalnizca gelistirme donemi / kapanmis islemler")
    print("Tutarlar TRY cinsindendir.")
    print()

    for strategy_name, filename in STRATEGIES.items():
        trades = read_trades(filename)

        print("=" * 75)
        print(strategy_name)
        print("=" * 75)
        print(
            f"{'Sure':<17}"
            f"{'Islem':>7}"
            f"{'Karli':>8}"
            f"{'Brut sonuc':>13}"
            f"{'Komisyon':>13}"
            f"{'Net sonuc':>13}"
        )
        print("-" * 75)

        counted = 0

        for label, minimum, maximum in GROUPS:
            group = [
                trade
                for trade in trades
                if minimum <= trade["minutes"] <= maximum
            ]

            counted += len(group)
            show_group(label, group)

        print("-" * 75)
        show_group("TOPLAM", trades)

        if counted != len(trades):
            raise ValueError(
                "Bazi islemler sure gruplarina girmedi."
            )

        print()

    print(
        "Not: Sure gruplari gecmis islemleri aciklar; "
        "tek basina bir alim filtresi degildir."
    )
    print("Calisan ajan ve ayri test verisi degistirilmedi.")


if __name__ == "__main__":
    main()