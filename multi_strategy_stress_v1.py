from pathlib import Path
from decimal import Decimal as D
import importlib.util

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "multi_strategy_backtest_v1.py"

spec = importlib.util.spec_from_file_location("ms", SRC)
ms = importlib.util.module_from_spec(spec)

# Import sirasinda ana backtest ekrana basilabilir; normal.
spec.loader.exec_module(ms)

ORIGINAL_START = ms.START
ORIGINAL_END   = ms.END
ORIGINAL_SLIP  = ms.SLIP

HOUR = ms.HOUR

# 648 saatlik ortak pencereyi iki esit parcaya ayir.
TOTAL_HOURS = ((ORIGINAL_END - ORIGINAL_START) // HOUR) + 1
HALF = TOTAL_HOURS // 2

PERIODS = [
    (
        "FIRST_HALF",
        ORIGINAL_START,
        ORIGINAL_START + (HALF - 1) * HOUR
    ),
    (
        "SECOND_HALF",
        ORIGINAL_START + HALF * HOUR,
        ORIGINAL_END
    ),
    (
        "FULL",
        ORIGINAL_START,
        ORIGINAL_END
    )
]

SLIPS = [
    D("0.001"),
    D("0.003"),
    D("0.005")
]

print()
print("=" * 105)
print("PORTFOLIOAI MULTI-STRATEGY STRESS V1")
print("3 STRATEGIES x 3 PERIODS x 3 SLIPPAGE LEVELS")
print("=" * 105)

results = []

for period_name, start, end in PERIODS:

    ms.START = start
    ms.END = end

    # run() global data/maps kullandigi icin her period icin
    # gerekli history'yi tekrar yukle.
    ms.data = ms.load_all()

    ms.maps = {}
    for symbol, rows in ms.data.items():
        ms.maps[symbol] = {
            t: (o, c)
            for t, o, c in rows
        }

    for slip in SLIPS:

        ms.SLIP = slip

        for strategy_name, fn in ms.STRATS.items():

            r = ms.run(strategy_name, fn)

            results.append({
                "period": period_name,
                "strategy": strategy_name,
                "slip": slip,
                "equity": r["equity"],
                "net": r["net"],
                "pct": r["pct"],
                "dd": r["dd"],
                "buys": r["buys"],
                "sells": r["sells"],
                "open": r["open"]
            })

# Restore
ms.START = ORIGINAL_START
ms.END = ORIGINAL_END
ms.SLIP = ORIGINAL_SLIP

print()
print(
    f"{'PERIOD':<13}"
    f"{'STRATEGY':<12}"
    f"{'SLIP':>8}"
    f"{'NET':>14}"
    f"{'RETURN':>11}"
    f"{'MAXDD':>11}"
    f"{'BUY':>7}"
    f"{'SELL':>7}"
    f"{'OPEN':>7}"
)

print("-" * 105)

for r in results:

    print(
        f"{r['period']:<13}"
        f"{r['strategy']:<12}"
        f"{float(r['slip'])*100:>7.1f}%"
        f"{r['net']:>14.2f}"
        f"{r['pct']:>10.2f}%"
        f"{r['dd']:>10.2f}%"
        f"{r['buys']:>7}"
        f"{r['sells']:>7}"
        f"{r['open']:>7}"
    )

print()
print("=" * 105)
print("QUICK ROBUSTNESS CHECK")
print("=" * 105)

for strategy in ms.STRATS.keys():

    rr = [x for x in results if x["strategy"] == strategy]

    positive = sum(1 for x in rr if x["net"] > 0)
    negative = sum(1 for x in rr if x["net"] < 0)

    worst = min(rr, key=lambda x: x["net"])
    best  = max(rr, key=lambda x: x["net"])

    print()
    print(strategy)
    print("  Positive scenarios :", positive, "/", len(rr))
    print("  Negative scenarios :", negative, "/", len(rr))
    print(
        "  Worst scenario     :",
        worst["period"],
        f"slip={float(worst['slip'])*100:.1f}%",
        f"net={worst['net']:.2f}",
        f"return={worst['pct']:.2f}%"
    )
    print(
        "  Best scenario      :",
        best["period"],
        f"slip={float(best['slip'])*100:.1f}%",
        f"net={best['net']:.2f}",
        f"return={best['pct']:.2f}%"
    )

print()
print("HISTORICAL STRESS TEST ONLY.")
print("NO REAL ORDERS.")
