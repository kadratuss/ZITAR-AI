from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import zitar_master_paper_engine_v1 as engine

BASE = Path(__file__).resolve().parent

MASTER = BASE / "zitar_master_portfolio_v1.json"
SANDBOX = BASE / "zitar_master_integration_sandbox_v1.json"


def load_master():
    return json.loads(
        MASTER.read_text(encoding="utf-8-sig")
    )


def prepare_sandbox(master):

    state = copy.deepcopy(master)

    # Paper Engine duplicate koruması.
    state["processed_event_ids"] = []

    # Engine'in beklediği test kurallarını,
    # gerçek Master kurallarından türetiyoruz.
    state["rules"]["max_positions"] = int(
        state["rules"]["max_spot_positions"]
    )

    state["rules"]["fee_rate"] = "0.001"
    state["rules"]["slippage_rate"] = "0.001"

    return state


def save_sandbox(state):

    SANDBOX.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def show(state, title):

    a = state["account"]

    print()
    print(title)
    print("-" * len(title))

    print("cash:", a["cash_try"])
    print("positions:", a["open_position_count"])
    print(
        "position value:",
        a["position_market_value_try"]
    )
    print(
        "realized P/L:",
        a["realized_pnl_try"]
    )
    print(
        "unrealized P/L:",
        a["unrealized_pnl_try"]
    )
    print("equity:", a["equity_try"])


def main():

    print("ZITAR MASTER INTEGRATION SANDBOX V1")
    print(
        "MASTER COPY ONLY • "
        "NO REAL MASTER WRITE • "
        "NO V3 WRITE • NO REAL ORDER"
    )

    original = load_master()

    original_text = MASTER.read_bytes()

    state = prepare_sandbox(original)

    # Kritik kontrol:
    # Gerçek günlük slot 1000 TL olmalı.
    budget = engine.slot_budget(state)

    print()
    print("MASTER DAILY SLOT:", budget)

    if budget != Decimal("1000.00"):
        raise RuntimeError(
            "FAIL: unexpected daily slot budget"
        )

    show(state, "INITIAL MASTER COPY")

    # --------------------------------------------
    # SMA BUY
    # --------------------------------------------

    r1 = engine.buy(
        state,
        symbol="TESTTRY",
        strategy="SMA20_50",
        reference_price=Decimal("100.00"),
        event_id="SANDBOX_SMA_BUY_001"
    )

    print()
    print("SMA BUY:", r1)

    # --------------------------------------------
    # EMA BUY - ikinci slot harcanmamalı
    # --------------------------------------------

    r2 = engine.buy(
        state,
        symbol="TESTTRY",
        strategy="EMA12_26",
        reference_price=Decimal("101.00"),
        event_id="SANDBOX_EMA_BUY_001"
    )

    print("EMA BUY:", r2)

    pos = state["account"]["positions"]["TESTTRY"]

    print(
        "SUPPORTERS:",
        pos["strategy_support"]
    )

    show(
        state,
        "AFTER TWO BUY EVENTS"
    )

    if state["account"]["open_position_count"] != 1:
        raise RuntimeError(
            "FAIL: duplicate position"
        )

    if state["account"]["cash_try"] != "9000.00":
        raise RuntimeError(
            "FAIL: second strategy consumed cash"
        )

    # --------------------------------------------
    # Mark = 105
    # --------------------------------------------

    engine.recalculate(
        state,
        {
            "TESTTRY": Decimal("105.00")
        }
    )

    engine.assert_identity(state)

    show(state, "MARK 105")

    # --------------------------------------------
    # SMA SELL
    # --------------------------------------------

    r3 = engine.remove_support_or_sell(
        state,
        symbol="TESTTRY",
        strategy="SMA20_50",
        reference_price=Decimal("105.00"),
        event_id="SANDBOX_SMA_SELL_001"
    )

    print()
    print("SMA SELL:", r3)

    if "TESTTRY" not in \
            state["account"]["positions"]:
        raise RuntimeError(
            "FAIL: closed with EMA support remaining"
        )

    # --------------------------------------------
    # EMA SELL
    # --------------------------------------------

    r4 = engine.remove_support_or_sell(
        state,
        symbol="TESTTRY",
        strategy="EMA12_26",
        reference_price=Decimal("105.00"),
        event_id="SANDBOX_EMA_SELL_001"
    )

    print("EMA SELL:", r4)

    show(
        state,
        "AFTER LAST SUPPORT SELL"
    )

    if state["account"]["equity_try"] != "10045.81":
        raise RuntimeError(
            "FAIL: unexpected final equity "
            + state["account"]["equity_try"]
        )

    if state["account"]["open_position_count"] != 0:
        raise RuntimeError(
            "FAIL: position still open"
        )

    # --------------------------------------------
    # Duplicate test
    # --------------------------------------------

    duplicate = engine.remove_support_or_sell(
        state,
        symbol="TESTTRY",
        strategy="EMA12_26",
        reference_price=Decimal("105.00"),
        event_id="SANDBOX_EMA_SELL_001"
    )

    print()
    print(
        "DUPLICATE:",
        duplicate
    )

    if duplicate != "DUPLICATE_EVENT":
        raise RuntimeError(
            "FAIL: duplicate protection"
        )

    engine.assert_identity(state)

    save_sandbox(state)

    # --------------------------------------------
    # Gerçek Master değişmiş mi?
    # --------------------------------------------

    if MASTER.read_bytes() != original_text:
        raise RuntimeError(
            "FAIL: REAL MASTER WAS MODIFIED"
        )

    print()
    print("DAILY FIXED SLOT: PASS")
    print("MASTER SCHEMA ADAPTER: PASS")
    print("MULTI-STRATEGY POSITION: PASS")
    print("LAST-SUPPORT CLOSE: PASS")
    print("DUPLICATE PROTECTION: PASS")
    print("ACCOUNTING IDENTITY: PASS")
    print("REAL MASTER UNCHANGED: PASS")

    print()
    print("sandbox:", SANDBOX)
    print("STATUS: PASS")


if __name__ == "__main__":
    main()
