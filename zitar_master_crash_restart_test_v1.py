from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import zitar_master_paper_engine_v1 as engine

BASE = Path(__file__).resolve().parent

MASTER = BASE / "zitar_master_portfolio_v1.json"
CRASH_STATE = BASE / "zitar_master_crash_restart_test_v1.json"


def load_json(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def save_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def prepare_state(master: dict) -> dict:

    state = copy.deepcopy(master)

    state["processed_event_ids"] = []

    state["rules"]["max_positions"] = int(
        state["rules"]["max_spot_positions"]
    )

    state["rules"]["fee_rate"] = "0.001"
    state["rules"]["slippage_rate"] = "0.001"

    return state


def account_snapshot(state: dict) -> dict:

    a = state["account"]

    return {
        "cash_try": a["cash_try"],
        "open_position_count":
            a["open_position_count"],
        "position_market_value_try":
            a["position_market_value_try"],
        "realized_pnl_try":
            a["realized_pnl_try"],
        "unrealized_pnl_try":
            a["unrealized_pnl_try"],
        "equity_try":
            a["equity_try"],
        "positions":
            copy.deepcopy(a["positions"])
    }


def main():

    print("ZITAR MASTER CRASH/RESTART TEST V1")
    print(
        "SANDBOX ONLY • "
        "NO REAL MASTER WRITE • "
        "NO V3 WRITE • NO REAL ORDER"
    )
    print()

    real_master_before = MASTER.read_bytes()

    master = load_json(MASTER)
    state = prepare_state(master)

    # ==================================================
    # PHASE 1
    # BUY event gelir.
    # ==================================================

    buy_event = "CRASH_TEST_BUY_001"

    result = engine.buy(
        state,
        symbol="TESTTRY",
        strategy="SMA20_50",
        reference_price=Decimal("100.00"),
        event_id=buy_event
    )

    print("PHASE 1 BUY:", result)

    if result != "BOUGHT":
        raise RuntimeError(
            "FAIL: initial BUY was not executed"
        )

    engine.assert_identity(state)

    save_json(
        CRASH_STATE,
        state
    )

    before_restart = account_snapshot(state)

    print(
        "STATE SAVED BEFORE SIMULATED CRASH"
    )
    print(
        "cash:",
        state["account"]["cash_try"]
    )
    print(
        "positions:",
        state["account"]["open_position_count"]
    )

    # ==================================================
    # PHASE 2
    # PROGRAM ÇÖKTÜ / RESTART OLDU.
    #
    # Bellekteki state artık kullanılmıyor.
    # Diskten yeniden okunuyor.
    # ==================================================

    del state

    restarted = load_json(CRASH_STATE)

    print()
    print("SIMULATED RESTART: STATE RELOADED")

    engine.assert_identity(restarted)

    # Aynı BUY event tekrar geliyor.
    duplicate_buy = engine.buy(
        restarted,
        symbol="TESTTRY",
        strategy="SMA20_50",
        reference_price=Decimal("100.00"),
        event_id=buy_event
    )

    print(
        "DUPLICATE BUY AFTER RESTART:",
        duplicate_buy
    )

    if duplicate_buy != "DUPLICATE_EVENT":
        raise RuntimeError(
            "FAIL: duplicate BUY executed after restart"
        )

    after_duplicate_buy = account_snapshot(
        restarted
    )

    if before_restart != after_duplicate_buy:
        raise RuntimeError(
            "FAIL: account changed after duplicate BUY"
        )

    # ==================================================
    # PHASE 3
    # SELL gelir ve pozisyon kapanır.
    # ==================================================

    sell_event = "CRASH_TEST_SELL_001"

    sell_result = engine.remove_support_or_sell(
        restarted,
        symbol="TESTTRY",
        strategy="SMA20_50",
        reference_price=Decimal("105.00"),
        event_id=sell_event
    )

    print()
    print("SELL:", sell_result)

    engine.assert_identity(restarted)

    if restarted[
        "account"
    ]["open_position_count"] != 0:
        raise RuntimeError(
            "FAIL: position did not close"
        )

    if restarted[
        "account"
    ]["equity_try"] != "10045.81":
        raise RuntimeError(
            "FAIL: unexpected final equity "
            + restarted[
                "account"
            ]["equity_try"]
        )

    # SELL sonrası state'i diske yaz.
    save_json(
        CRASH_STATE,
        restarted
    )

    before_second_restart = account_snapshot(
        restarted
    )

    print(
        "SELL STATE SAVED BEFORE SECOND CRASH"
    )

    # ==================================================
    # PHASE 4
    # SELL'den hemen sonra crash/restart.
    # Aynı SELL tekrar geliyor.
    # ==================================================

    del restarted

    restarted_again = load_json(
        CRASH_STATE
    )

    print()
    print(
        "SECOND SIMULATED RESTART: "
        "STATE RELOADED"
    )

    duplicate_sell = (
        engine.remove_support_or_sell(
            restarted_again,
            symbol="TESTTRY",
            strategy="SMA20_50",
            reference_price=Decimal("105.00"),
            event_id=sell_event
        )
    )

    print(
        "DUPLICATE SELL AFTER RESTART:",
        duplicate_sell
    )

    if duplicate_sell != "DUPLICATE_EVENT":
        raise RuntimeError(
            "FAIL: duplicate SELL executed after restart"
        )

    after_duplicate_sell = account_snapshot(
        restarted_again
    )

    if (
        before_second_restart
        != after_duplicate_sell
    ):
        raise RuntimeError(
            "FAIL: account changed after duplicate SELL"
        )

    engine.assert_identity(
        restarted_again
    )

    # ==================================================
    # PHASE 5
    # Event ID persistence kontrolü.
    # ==================================================

    processed = restarted_again[
        "processed_event_ids"
    ]

    if buy_event not in processed:
        raise RuntimeError(
            "FAIL: BUY event id not persisted"
        )

    if sell_event not in processed:
        raise RuntimeError(
            "FAIL: SELL event id not persisted"
        )

    if processed.count(buy_event) != 1:
        raise RuntimeError(
            "FAIL: BUY event id duplicated"
        )

    if processed.count(sell_event) != 1:
        raise RuntimeError(
            "FAIL: SELL event id duplicated"
        )

    # ==================================================
    # Gerçek Master değişmemiş olmalı.
    # ==================================================

    if MASTER.read_bytes() != real_master_before:
        raise RuntimeError(
            "FAIL: REAL MASTER WAS MODIFIED"
        )

    print()
    print(
        "FINAL CASH:",
        restarted_again[
            "account"
        ]["cash_try"]
    )

    print(
        "FINAL EQUITY:",
        restarted_again[
            "account"
        ]["equity_try"]
    )

    print(
        "PROCESSED EVENTS:",
        len(processed)
    )

    print()
    print("BUY PERSISTENCE: PASS")
    print("BUY RESTART DUPLICATE BLOCK: PASS")
    print("SELL PERSISTENCE: PASS")
    print("SELL RESTART DUPLICATE BLOCK: PASS")
    print("EVENT ID PERSISTENCE: PASS")
    print("ACCOUNTING IDENTITY: PASS")
    print("REAL MASTER UNCHANGED: PASS")

    print()
    print("test state:", CRASH_STATE)
    print("STATUS: PASS")


if __name__ == "__main__":
    main()
