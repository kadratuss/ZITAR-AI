import json
import sys
from pathlib import Path
from decimal import Decimal

ROOT = Path.cwd()
STATE = ROOT / "multistrategy_live_state_v3.json"

print("")
print("=== LOAD STATE ===")

state = json.loads(
    STATE.read_text(encoding="utf-8-sig")
)

print("STATE LOAD : PASS")

required_top = [
    "universe",
    "strategies",
    "rules",
    "processed_candle_closes",
]

for key in required_top:
    if key not in state:
        raise RuntimeError(
            f"Missing state key: {key}"
        )

print("TOP LEVEL  : PASS")

print("")
print("=== UNIVERSE ===")

universe = state["universe"]

print("SYMBOLS :", len(universe))

if len(universe) != 21:
    raise RuntimeError(
        f"Expected 21 symbols, got {len(universe)}"
    )

print("UNIVERSE : PASS")

print("")
print("=== STRATEGIES ===")

for name in (
    "SMA20_50",
    "EMA12_26",
    "RSI14",
):
    if name not in state["strategies"]:
        raise RuntimeError(
            f"Missing strategy: {name}"
        )

    a = state["strategies"][name]

    for key in (
        "cash_try",
        "positions",
        "realized_pnl_try",
        "trade_count",
    ):
        if key not in a:
            raise RuntimeError(
                f"{name} missing {key}"
            )

    Decimal(str(a["cash_try"]))
    Decimal(str(a["realized_pnl_try"]))

    print(
        name,
        "| cash:",
        a["cash_try"],
        "| positions:",
        len(a["positions"]),
        "| trades:",
        a["trade_count"],
    )

print("STRATEGIES : PASS")

print("")
print("=== RULE SCHEMA ===")

required_rules = [
    "fee_rate",
    "slippage_rate",
    "order_budget_try",
    "max_positions_per_strategy",
]

for key in required_rules:
    if key not in state["rules"]:
        print("MISSING RULE:", key)
        raise RuntimeError(
            f"V3 expects rule key not present: {key}"
        )

print(
    "fee_rate                  :",
    state["rules"]["fee_rate"],
)
print(
    "slippage_rate             :",
    state["rules"]["slippage_rate"],
)
print(
    "order_budget_try           :",
    state["rules"]["order_budget_try"],
)
print(
    "max_positions_per_strategy:",
    state["rules"]["max_positions_per_strategy"],
)

print("RULE SCHEMA : PASS")

print("")
print("=== EXISTING POSITIONS ===")

for strategy, account in state[
    "strategies"
].items():

    for symbol, pos in account[
        "positions"
    ].items():

        required_pos = [
            "quantity",
            "total_cost_try",
        ]

        for key in required_pos:
            if key not in pos:
                raise RuntimeError(
                    f"{strategy}/{symbol} missing {key}"
                )

        Decimal(str(pos["quantity"]))
        Decimal(str(pos["total_cost_try"]))

        print(
            strategy,
            symbol,
            "| qty:",
            pos["quantity"],
            "| cost:",
            pos["total_cost_try"],
        )

print("POSITION SCHEMA : PASS")

print("")
print("=== PROCESSED CANDLES ===")

processed = state[
    "processed_candle_closes"
]

print("COUNT :", len(processed))

if processed:
    print(
        "LAST  :",
        processed[-1],
    )

print("PROCESSED LIST : PASS")

print("")
print("=" * 72)
print("V3 STATE PREFLIGHT : PASS")
print("=" * 72)
