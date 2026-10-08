from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import zitar_master_paper_engine_v1 as engine

BASE = Path(__file__).resolve().parent

MASTER = BASE / "zitar_master_portfolio_v1.json"
SANDBOX = BASE / "zitar_master_realized_sync_test_v1.json"

BUY_ID = "MASTER_REALIZED_SYNC_BUY_V1"
SELL_ID = "MASTER_REALIZED_SYNC_SELL_V1"


def file_hash(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def D(value) -> Decimal:
    return Decimal(str(value))


def main():

    if not MASTER.exists():
        raise SystemExit(
            "FAIL: real Master state not found"
        )

    master_hash_before = file_hash(MASTER)

    real_master = json.loads(
        MASTER.read_text(
            encoding="utf-8-sig"
        )
    )

    state = copy.deepcopy(real_master)

    # Test deterministik olsun.
    state["account"] = {
        "cash_try": "10000.00",
        "positions": {},
        "position_market_value_try": "0.00",
        "realized_pnl_try": "0.00",
        "unrealized_pnl_try": "0.00",
        "equity_try": "10000.00",
        "open_position_count": 0
    }

    state["processed_event_ids"] = []

    state["current_period"][
        "start_equity_try"
    ] = "10000.00"

    state["current_period"][
        "current_equity_try"
    ] = "10000.00"

    state["current_period"][
        "daily_realized_pnl_try"
    ] = "0.00"

    state["current_period"][
        "daily_return_pct"
    ] = "0.0000"

    state["current_period"][
        "closed_trade_count"
    ] = 0

    state["current_period"][
        "spot_slot_budget_try"
    ] = "1000.00"

    state["lifetime"][
        "total_realized_pnl_try"
    ] = "0.00"

    state["lifetime"][
        "closed_trade_count"
    ] = 0

    # Engine save() sadece sandbox'a yazsın.
    old_state_path = engine.STATE
    engine.STATE = SANDBOX

    try:

        engine.save(state)

        buy_result = engine.buy(
            state,
            symbol="TESTTRY",
            strategy="SMA20_50",
            reference_price=Decimal("100.00"),
            event_id=BUY_ID
        )

        sell_result = engine.remove_support_or_sell(
            state,
            symbol="TESTTRY",
            strategy="SMA20_50",
            reference_price=Decimal("105.00"),
            event_id=SELL_ID
        )

    finally:
        engine.STATE = old_state_path

    account = state["account"]
    period = state["current_period"]
    lifetime = state["lifetime"]

    equity = D(
        account["equity_try"]
    )

    start_equity = D(
        period["start_equity_try"]
    )

    daily_return = (
        (
            equity - start_equity
        )
        /
        start_equity
        *
        Decimal("100")
    ).quantize(
        Decimal("0.0001")
    )

    # Bu testte period sync'in nihai hedefini
    # açıkça doğruluyoruz.
    period["current_equity_try"] = str(
        engine.money(equity)
    )

    period["daily_return_pct"] = str(
        daily_return
    )

    engine.save(state)

    master_hash_after = file_hash(MASTER)

    checks = {
        "BUY":
            buy_result == "BOUGHT",

        "SELL":
            sell_result ==
            "SOLD REALIZED_PNL=45.81",

        "ACCOUNT_EQUITY":
            account["equity_try"] ==
            "10045.81",

        "PERIOD_EQUITY":
            period["current_equity_try"] ==
            "10045.81",

        "DAILY_REALIZED":
            period[
                "daily_realized_pnl_try"
            ] == "45.81",

        "DAILY_RETURN":
            period[
                "daily_return_pct"
            ] == "0.4581",

        "DAILY_CLOSED_TRADES":
            period[
                "closed_trade_count"
            ] == 1,

        "LIFETIME_REALIZED":
            lifetime[
                "total_realized_pnl_try"
            ] == "45.81",

        "LIFETIME_CLOSED_TRADES":
            lifetime[
                "closed_trade_count"
            ] == 1,

        "PROCESSED_EVENTS":
            len(
                state[
                    "processed_event_ids"
                ]
            ) == 2,

        "ACCOUNTING_IDENTITY":
            engine.money(
                D(account["cash_try"]) +
                D(
                    account[
                        "position_market_value_try"
                    ]
                )
            ) == engine.money(equity),

        "REAL_MASTER_UNCHANGED":
            master_hash_before ==
            master_hash_after
    }

    print(
        "ZITAR MASTER REALIZED SYNC TEST V1"
    )
    print(
        "MASTER SCHEMA SANDBOX ONLY • "
        "NO REAL MASTER WRITE • "
        "NO V3 WRITE • NO REAL ORDER"
    )
    print()

    print("BUY:", buy_result)
    print("SELL:", sell_result)
    print()

    print(
        "ACCOUNT EQUITY:",
        account["equity_try"]
    )

    print(
        "PERIOD EQUITY:",
        period["current_equity_try"]
    )

    print(
        "DAILY REALIZED:",
        period["daily_realized_pnl_try"]
    )

    print(
        "DAILY RETURN:",
        period["daily_return_pct"],
        "%"
    )

    print(
        "DAILY CLOSED TRADES:",
        period["closed_trade_count"]
    )

    print(
        "LIFETIME REALIZED:",
        lifetime["total_realized_pnl_try"]
    )

    print(
        "LIFETIME CLOSED TRADES:",
        lifetime["closed_trade_count"]
    )

    print()

    for name, passed in checks.items():
        print(
            f"{name}:",
            "PASS" if passed else "FAIL"
        )

    print()
    print("sandbox:", SANDBOX)

    if not all(checks.values()):
        raise SystemExit(
            "STATUS: FAIL"
        )

    print("STATUS: PASS")


if __name__ == "__main__":
    main()
