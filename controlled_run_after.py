import csv
import json
from pathlib import Path
from decimal import Decimal

ROOT = Path.cwd()


state = json.loads(
    (
        ROOT
        / "multistrategy_live_state_v3.json"
    ).read_text(
        encoding="utf-8-sig"
    )
)


print("")
print("=" * 72)
print("CONTROLLED PAPER RUN - AFTER")
print("=" * 72)

processed = state.get(
    "processed_candle_closes",
    []
)

print(
    "Processed candles:",
    len(processed)
)

if processed:
    print(
        "Last processed:",
        processed[-1]
    )


print("")
print("=== ACCOUNTS ===")

for strategy, account in state[
    "accounts"
].items():

    positions = account.get(
        "positions",
        {}
    )

    print("")
    print(strategy)

    print(
        "  Cash:",
        account.get(
            "cash_try"
        )
    )

    print(
        "  Positions:",
        len(positions)
    )

    for symbol, pos in positions.items():

        print(
            "   ",
            symbol,
            "qty=",
            pos.get("quantity"),
            "entry=",
            pos.get(
                "modeled_entry_price"
            ),
        )


def rows(name):

    p = ROOT / name

    if not p.exists():
        return []

    with p.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as f:

        return list(
            csv.DictReader(f)
        )


signals = rows(
    "multistrategy_live_signals_v3.csv"
)

trades = rows(
    "multistrategy_live_trades_v3.csv"
)

runs = rows(
    "multistrategy_live_runs_v3.csv"
)


print("")
print("=== V3 FILE COUNTS ===")

print(
    "Signals:",
    len(signals)
)

print(
    "Trades :",
    len(trades)
)

print(
    "Runs   :",
    len(runs)
)


if runs:

    print("")
    print("=== LATEST RUN ===")

    for k, v in runs[-1].items():
        print(
            f"{k}: {v}"
        )


if trades:

    print("")
    print("=== LATEST PAPER TRADES ===")

    for row in trades[-10:]:

        print(
            row.get(
                "executed_at_utc"
            ),
            row.get(
                "strategy"
            ),
            row.get(
                "symbol"
            ),
            row.get(
                "side"
            ),
            "fill=",
            row.get(
                "modeled_fill_price"
            ),
            "status=",
            row.get(
                "status"
            ),
        )


if signals:

    latest_close = signals[-1].get(
        "candle_close_utc"
    )

    latest = [
        r
        for r in signals
        if r.get(
            "candle_close_utc"
        ) == latest_close
    ]

    active = [
        r
        for r in latest
        if r.get(
            "signal"
        ) not in (
            None,
            "",
            "NONE",
        )
    ]

    print("")
    print(
        "=== LATEST CANDLE SIGNALS ==="
    )

    print(
        "Candle:",
        latest_close
    )

    print(
        "Rows:",
        len(latest)
    )

    print(
        "Active:",
        len(active)
    )

    for row in active:

        print(
            row.get(
                "strategy"
            ),
            row.get(
                "symbol"
            ),
            row.get(
                "signal"
            ),
        )


print("")
print("=" * 72)
print("PAPER RESULT READ : PASS")
print("REAL ORDER        : NO")
print("=" * 72)
