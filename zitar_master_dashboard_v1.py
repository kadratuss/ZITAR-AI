from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

BASE = Path(__file__).resolve().parent

MASTER = BASE / "zitar_master_portfolio_v1.json"
EVENTS = BASE / "zitar_master_trade_events_v1.jsonl"
WATERMARK = BASE / "zitar_master_trade_watermark_v1.json"
BRIDGE = BASE / "zitar_master_execution_bridge_v1.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}

    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def read_events() -> list[dict]:
    if not EVENTS.exists():
        return []

    result = []

    for line in EVENTS.read_text(
        encoding="utf-8-sig"
    ).splitlines():

        if not line.strip():
            continue

        result.append(json.loads(line))

    return result


def D(value) -> Decimal:
    return Decimal(str(value or "0"))


def fmt_money(value) -> str:
    return f"{D(value):,.2f}"


def print_header(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def main():

    print("ZITAR MASTER DASHBOARD V1")
    print(
        "READ ONLY • NO MASTER WRITE • "
        "NO V3 WRITE • NO PAPER ORDER • NO REAL ORDER"
    )

    if not MASTER.exists():
        raise SystemExit(
            "FAIL: Master portfolio state not found"
        )

    master = load_json(MASTER)

    if master.get("schema") != \
            "ZITAR_MASTER_PORTFOLIO_V1":
        raise SystemExit(
            "FAIL: unexpected Master schema"
        )

    account = master.get("account", {})
    period = master.get("current_period", {})
    lifetime = master.get("lifetime", {})
    positions = account.get("positions", {})

    print_header("MASTER PORTFOLIO")

    print(
        "Period             :",
        period.get("period_id", "-")
    )

    print(
        "Equity             :",
        fmt_money(account.get("equity_try")),
        "TRY"
    )

    print(
        "Cash               :",
        fmt_money(account.get("cash_try")),
        "TRY"
    )

    print(
        "Position Value     :",
        fmt_money(
            account.get(
                "position_market_value_try"
            )
        ),
        "TRY"
    )

    print(
        "Unrealized P/L     :",
        fmt_money(
            account.get(
                "unrealized_pnl_try"
            )
        ),
        "TRY"
    )

    print(
        "Daily Realized P/L :",
        fmt_money(
            period.get(
                "daily_realized_pnl_try"
            )
        ),
        "TRY"
    )

    print(
        "Daily Return       :",
        period.get(
            "daily_return_pct",
            "0.0000"
        ),
        "%"
    )

    print(
        "Lifetime Realized  :",
        fmt_money(
            lifetime.get(
                "total_realized_pnl_try"
            )
        ),
        "TRY"
    )

    print(
        "Open Positions     :",
        account.get(
            "open_position_count",
            len(positions)
        )
    )

    print(
        "Daily Slot Budget  :",
        fmt_money(
            period.get(
                "spot_slot_budget_try"
            )
        ),
        "TRY"
    )

    print_header("OPEN POSITIONS")

    if not positions:
        print("No open Master positions.")

    else:
        for symbol, pos in positions.items():

            print()
            print(symbol)
            print("-" * len(symbol))

            print(
                "Strategies       :",
                ", ".join(
                    pos.get(
                        "strategy_support",
                        []
                    )
                )
            )

            print(
                "Quantity         :",
                pos.get("quantity", "-")
            )

            print(
                "Entry Reference  :",
                pos.get(
                    "entry_reference_price",
                    "-"
                )
            )

            print(
                "Entry Fill       :",
                pos.get(
                    "entry_fill_price",
                    "-"
                )
            )

            print(
                "Last Mark        :",
                pos.get(
                    "last_mark_price",
                    "-"
                )
            )

            print(
                "Market Value     :",
                fmt_money(
                    pos.get(
                        "market_value_try"
                    )
                ),
                "TRY"
            )

            print(
                "Unrealized P/L   :",
                fmt_money(
                    pos.get(
                        "unrealized_pnl_try"
                    )
                ),
                "TRY"
            )

            print(
                "Opened UTC       :",
                pos.get(
                    "opened_utc",
                    "-"
                )
            )

    events = read_events()
    watermark = load_json(WATERMARK)
    bridge = load_json(BRIDGE)

    print_header("SYSTEM STATUS")

    print(
        "Master State       : PASS"
    )

    print(
        "V3 Baseline Trades :",
        watermark.get(
            "baseline_trade_count",
            "-"
        )
    )

    print(
        "Detector Processed :",
        len(
            watermark.get(
                "processed_trade_ids",
                []
            )
        )
    )

    print(
        "Master Events      :",
        len(events)
    )

    print(
        "Bridge Processed   :",
        len(
            bridge.get(
                "processed_event_ids",
                []
            )
        )
    )

    master_processed = master.get(
        "processed_event_ids",
        []
    )

    print(
        "Master Processed   :",
        len(master_processed)
    )

    print_header("RECENT MASTER EVENTS")

    if not events:
        print("No Master events.")

    else:
        for event in events[-10:][::-1]:

            print(
                event.get(
                    "executed_at_utc",
                    "-"
                ),
                "|",
                event.get("side", "-"),
                "|",
                event.get("strategy", "-"),
                "|",
                event.get("symbol", "-"),
                "|",
                (
                    event.get(
                        "source_trade_id",
                        ""
                    )[:12]
                )
            )

    print_header("SAFETY")

    print("Dashboard write authority : FALSE")
    print("Master order authority    : FALSE")
    print("Real order authority      : FALSE")
    print("V3 write authority        : FALSE")

    print()
    print(
        "Dashboard generated:",
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    print()
    print("STATUS: PASS")


if __name__ == "__main__":
    main()
