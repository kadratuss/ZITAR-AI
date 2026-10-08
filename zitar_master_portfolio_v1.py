from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent

STATE = BASE / "zitar_master_portfolio_v1.json"
DAILY_LOG = BASE / "zitar_daily_performance_v1.jsonl"

TZ = ZoneInfo("Europe/Istanbul")

INITIAL_CAPITAL_TRY = Decimal("10000.00")
MAX_SPOT_POSITIONS = 10

MONEY = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_tr() -> datetime:
    return now_utc().astimezone(TZ)


def current_period_id() -> str:
    # Türkiye saati 00:00 -> 23:59:59 aynı muhasebe günü.
    return now_tr().date().isoformat()


def default_state() -> dict:

    capital = money(INITIAL_CAPITAL_TRY)

    slot_budget = money(
        capital / Decimal(MAX_SPOT_POSITIONS)
    )

    return {
        "schema": "ZITAR_MASTER_PORTFOLIO_V1",

        "created_utc": now_utc().isoformat(),

        "timezone": "Europe/Istanbul",
        "daily_rollover_local": "00:00",

        "mode": "MEASUREMENT_ONLY",

        "authorities": {
            "directional_signal": False,
            "paper_order": False,
            "real_order": False,
            "futures_allocation": False
        },

        "rules": {
            "initial_capital_try": str(capital),
            "max_spot_positions": MAX_SPOT_POSITIONS,
            "compound_daily": True,
            "force_close_at_rollover": False,
            "futures_enabled": False
        },

        "account": {
            "cash_try": str(capital),

            "positions": {},

            "position_market_value_try": "0.00",

            "realized_pnl_try": "0.00",

            "unrealized_pnl_try": "0.00",

            "equity_try": str(capital),

            "open_position_count": 0
        },

        "current_period": {
            "period_id": current_period_id(),
            "start_equity_try": str(capital),
            "current_equity_try": str(capital),

            "daily_realized_pnl_try": "0.00",
            "daily_return_pct": "0.0000",

            "closed_trade_count": 0,

            "spot_slot_budget_try": str(slot_budget)
        },

        "lifetime": {
            "initial_capital_try": str(capital),
            "total_realized_pnl_try": "0.00",
            "closed_trade_count": 0
        },

        "sources": {
            "strategy_experiment":
                "multistrategy_live_state_v3.json",

            "strategy_trade_log":
                "multistrategy_live_trades_v3.csv",

            "note":
                "V3 remains an independent frozen prospective experiment."
        },

        "last_updated_utc": now_utc().isoformat()
    }


def load_state() -> dict:

    if not STATE.exists():
        state = default_state()
        save_state(state)
        return state

    return json.loads(
        STATE.read_text(encoding="utf-8-sig")
    )


def save_state(state: dict) -> None:

    state["last_updated_utc"] = now_utc().isoformat()

    STATE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def append_daily_record(record: dict) -> None:

    with DAILY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":")
            ) + "\n"
        )


def rollover_if_needed(state: dict) -> bool:

    period = state["current_period"]
    today = current_period_id()

    if period["period_id"] == today:
        return False

    start_equity = Decimal(
        period["start_equity_try"]
    )

    closing_equity = Decimal(
        period["current_equity_try"]
    )

    realized = Decimal(
        period["daily_realized_pnl_try"]
    )

    equity_change = (
        closing_equity - start_equity
    )

    if start_equity != 0:
        equity_return_pct = (
            equity_change /
            start_equity *
            Decimal("100")
        )
    else:
        equity_return_pct = Decimal("0")

    record = {
        "schema":
            "ZITAR_DAILY_PERFORMANCE_V1",

        "period_id":
            period["period_id"],

        "timezone":
            state["timezone"],

        "start_equity_try":
            str(money(start_equity)),

        "closing_equity_try":
            str(money(closing_equity)),

        "realized_pnl_try":
            str(money(realized)),

        "equity_change_try":
            str(money(equity_change)),

        "equity_return_pct":
            str(
                equity_return_pct.quantize(
                    Decimal("0.0001"),
                    rounding=ROUND_HALF_UP
                )
            ),

        "closed_trade_count":
            int(
                period.get(
                    "closed_trade_count",
                    0
                )
            ),

        "archived_utc":
            now_utc().isoformat()
    }

    append_daily_record(record)

    max_positions = int(
        state["rules"]["max_spot_positions"]
    )

    new_slot_budget = money(
        closing_equity /
        Decimal(max_positions)
    )

    state["current_period"] = {
        "period_id": today,

        "start_equity_try":
            str(money(closing_equity)),

        "current_equity_try":
            str(money(closing_equity)),

        "daily_realized_pnl_try":
            "0.00",

        "daily_return_pct":
            "0.0000",

        "closed_trade_count":
            0,

        "spot_slot_budget_try":
            str(new_slot_budget)
    }

    save_state(state)

    return True


def ensure_account_structure(state: dict) -> None:

    if "account" in state:
        return

    period = state["current_period"]

    equity = money(
        Decimal(
            period["current_equity_try"]
        )
    )

    state["account"] = {
        "cash_try": str(equity),

        "positions": {},

        "position_market_value_try": "0.00",

        "realized_pnl_try":
            str(
                money(
                    Decimal(
                        state.get(
                            "lifetime",
                            {}
                        ).get(
                            "total_realized_pnl_try",
                            "0.00"
                        )
                    )
                )
            ),

        "unrealized_pnl_try": "0.00",

        "equity_try": str(equity),

        "open_position_count": 0
    }

    save_state(state)


def main():

    state = load_state()

    ensure_account_structure(state)

    rolled = rollover_if_needed(state)

    period = state["current_period"]
    account = state["account"]

    print("ZITAR MASTER PORTFOLIO V1")
    print(
        "MEASUREMENT ONLY • "
        "NO PAPER ORDER • NO REAL ORDER"
    )

    print()
    print(
        "rollover:",
        "PERFORMED" if rolled else "NOT_REQUIRED"
    )

    print("timezone:", state["timezone"])
    print(
        "daily rollover:",
        state["daily_rollover_local"]
    )

    print(
        "period:",
        period["period_id"]
    )

    print(
        "start equity:",
        period["start_equity_try"],
        "TRY"
    )

    print()
    print("SPOT ACCOUNT")

    print(
        "cash:",
        account["cash_try"],
        "TRY"
    )

    print(
        "open positions:",
        account["open_position_count"]
    )

    print(
        "position value:",
        account["position_market_value_try"],
        "TRY"
    )

    print(
        "realized P/L:",
        account["realized_pnl_try"],
        "TRY"
    )

    print(
        "unrealized P/L:",
        account["unrealized_pnl_try"],
        "TRY"
    )

    print(
        "account equity:",
        account["equity_try"],
        "TRY"
    )

    print(
        "current equity:",
        period["current_equity_try"],
        "TRY"
    )

    print(
        "daily realized P/L:",
        period["daily_realized_pnl_try"],
        "TRY"
    )

    print(
        "daily return:",
        period["daily_return_pct"],
        "%"
    )

    print(
        "max spot positions:",
        state["rules"]["max_spot_positions"]
    )

    print(
        "spot slot budget:",
        period["spot_slot_budget_try"],
        "TRY"
    )

    print()
    print("state:", STATE)
    print("daily log:", DAILY_LOG)

    print("STATUS: PASS")


if __name__ == "__main__":
    main()
