import csv
import json
import hashlib
from pathlib import Path

ROOT = Path.cwd()

STATE = ROOT / "multistrategy_live_state_v3.json"
RUNNER = ROOT / "multistrategy_live_runner_v3.py"

EXPECTED_RUNNER = (
    "7859113476EE83205EF924F39355C36E9F310A8C6101C85BCEC37079F65E674A"
)


def sha(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest().upper()


state_before = sha(STATE)
runner_before = sha(RUNNER)

if runner_before != EXPECTED_RUNNER:
    raise RuntimeError(
        "RUNNER HASH CHANGED"
    )


state = json.loads(
    STATE.read_text(
        encoding="utf-8-sig"
    )
)


print("")
print("=== STATE SCHEMA ===")

print(
    "TOP LEVEL KEYS:"
)

for key in sorted(state):
    value = state[key]

    print(
        f"  {key:<28} "
        f"{type(value).__name__}"
    )


print("")
print("=== PROCESSED CANDLES ===")

processed = state.get(
    "processed_candle_closes",
    []
)

print(
    "Count:",
    len(processed)
)

if processed:
    print(
        "Last :",
        processed[-1]
    )


print("")
print("=== STRATEGY CONTAINERS ===")

# Do not assume the account key.
# Discover dictionary containers that look like strategies.

strategy_names = {
    "SMA20_50",
    "EMA12_26",
    "RSI14",
}

found = False

for top_key, value in state.items():

    if not isinstance(value, dict):
        continue

    matching = (
        strategy_names
        & set(value.keys())
    )

    if not matching:
        continue

    found = True

    print("")
    print(
        "CONTAINER:",
        top_key
    )

    for strategy in sorted(matching):

        account = value[strategy]

        print("")
        print(
            " ",
            strategy
        )

        if not isinstance(
            account,
            dict
        ):
            print(
                "   VALUE:",
                account
            )
            continue

        print(
            "   KEYS:",
            sorted(
                account.keys()
            )
        )

        for candidate in (
            "cash_try",
            "cash",
            "balance_try",
            "balance",
            "realized_pnl_try",
            "realized_pnl",
        ):

            if candidate in account:
                print(
                    f"   {candidate}:",
                    account[candidate]
                )

        positions = account.get(
            "positions"
        )

        if isinstance(
            positions,
            dict
        ):

            print(
                "   positions:",
                len(positions)
            )

            for symbol, pos in positions.items():

                print(
                    "     ",
                    symbol,
                    pos
                )


if not found:
    print(
        "No strategy container automatically detected."
    )


def read_csv(name):

    path = ROOT / name

    if not path.exists():
        return []

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as f:

        return list(
            csv.DictReader(f)
        )


signals = read_csv(
    "multistrategy_live_signals_v3.csv"
)

trades = read_csv(
    "multistrategy_live_trades_v3.csv"
)

runs = read_csv(
    "multistrategy_live_runs_v3.csv"
)


print("")
print("=== V3 OUTPUT FILES ===")

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
    print("LATEST RUN:")

    for k, v in runs[-1].items():
        print(
            f"  {k}: {v}"
        )


if signals:

    latest_close = signals[-1].get(
        "candle_close_utc"
    )

    latest = [
        row
        for row in signals
        if row.get(
            "candle_close_utc"
        ) == latest_close
    ]

    active = [
        row
        for row in latest
        if row.get("signal")
        not in (
            "",
            "NONE",
            None,
        )
    ]

    print("")
    print(
        "LATEST SIGNAL CANDLE:",
        latest_close
    )

    print(
        "Rows  :",
        len(latest)
    )

    print(
        "Active:",
        len(active)
    )

    for row in active:

        print(
            " ",
            row.get("strategy"),
            row.get("symbol"),
            row.get("signal"),
        )


if trades:

    print("")
    print("LATEST PAPER TRADES:")

    for row in trades[-10:]:

        print(
            " ",
            row.get("executed_at_utc"),
            row.get("strategy"),
            row.get("symbol"),
            row.get("side"),
            row.get("modeled_fill_price"),
        )


# Absolute read-only verification.
state_after = sha(STATE)
runner_after = sha(RUNNER)

if state_before != state_after:
    raise RuntimeError(
        "INSPECTOR CHANGED STATE"
    )

if runner_before != runner_after:
    raise RuntimeError(
        "INSPECTOR CHANGED RUNNER"
    )


print("")
print("============================================================")
print("STATE INSPECTION   : PASS")
print("STATE MODIFIED     : NO")
print("RUNNER MODIFIED    : NO")
print("RUNNER EXECUTED    : NO")
print("PAPER TRADE        : NO")
print("REAL ORDER         : NO")
print("============================================================")

