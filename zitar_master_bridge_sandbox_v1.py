from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import zitar_master_paper_engine_v1 as engine

BASE = Path(__file__).resolve().parent

MASTER = BASE / "zitar_master_portfolio_v1.json"
SANDBOX = BASE / "zitar_master_bridge_sandbox_v1.json"


def load_json(path: Path) -> dict:
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def prepare_master() -> dict:

    state = copy.deepcopy(
        load_json(MASTER)
    )

    state.setdefault(
        "processed_event_ids",
        []
    )

    state["rules"]["max_positions"] = int(
        state["rules"]["max_spot_positions"]
    )

    state["rules"]["fee_rate"] = "0.001"
    state["rules"]["slippage_rate"] = "0.001"

    return state


def execute_event(
    state: dict,
    event: dict
) -> str:

    event_id = event["source_trade_id"]

    symbol = event["symbol"]
    strategy = event["strategy"]

    # KRİTİK:
    # V3 modeled_fill_price kullanılmaz.
    # Master kendi slippage + fee modelini uygular.
    price = Decimal(
        str(event["reference_price"])
    )

    side = event["side"]

    if side == "BUY":

        return engine.buy(
            state,
            symbol=symbol,
            strategy=strategy,
            reference_price=price,
            event_id=event_id
        )

    if side == "SELL":

        return engine.remove_support_or_sell(
            state,
            symbol=symbol,
            strategy=strategy,
            reference_price=price,
            event_id=event_id
        )

    raise RuntimeError(
        "FAIL: unsupported side"
    )


def main():

    print("ZITAR MASTER BRIDGE SANDBOX V1")
    print(
        "REAL EVENT FORMAT • "
        "SANDBOX MASTER ONLY • "
        "NO REAL MASTER WRITE • "
        "NO V3 WRITE"
    )
    print()

    master_before = MASTER.read_bytes()

    state = prepare_master()

    # Paper Engine save() hedefini SADECE
    # sandbox dosyasına yönlendir.
    engine.STATE = SANDBOX

    # -----------------------------------------
    # Gerçek detector event şemasıyla BUY
    # -----------------------------------------

    buy_event = {
        "schema":
            "ZITAR_MASTER_TRADE_EVENT_V1",

        "source_trade_id":
            "BRIDGE_SANDBOX_BUY_001",

        "strategy":
            "SMA20_50",

        "symbol":
            "TESTTRY",

        "side":
            "BUY",

        "reference_price":
            "100.00",

        # Bilerek farklı değer.
        # Bunun kullanılmadığını kanıtlayacağız.
        "modeled_fill_price":
            "999.00"
    }

    result = execute_event(
        state,
        buy_event
    )

    print("BUY:", result)

    if result != "BOUGHT":
        raise RuntimeError(
            "FAIL: BUY"
        )

    position = state[
        "account"
    ]["positions"]["TESTTRY"]

    print(
        "ENTRY REFERENCE:",
        position["entry_reference_price"]
    )

    print(
        "ENTRY FILL:",
        position["entry_fill_price"]
    )

    if Decimal(
        position["entry_reference_price"]
    ) != Decimal("100.00"):
        raise RuntimeError(
            "FAIL: wrong reference price"
        )

    if Decimal(
        position["entry_fill_price"]
    ) != Decimal("100.10000"):
        raise RuntimeError(
            "FAIL: Master slippage model incorrect"
        )

    # -----------------------------------------
    # Restart
    # -----------------------------------------

    del state

    restarted = load_json(SANDBOX)

    duplicate = execute_event(
        restarted,
        buy_event
    )

    print(
        "DUPLICATE BUY AFTER RESTART:",
        duplicate
    )

    if duplicate != "DUPLICATE_EVENT":
        raise RuntimeError(
            "FAIL: duplicate BUY"
        )

    # -----------------------------------------
    # SELL
    # -----------------------------------------

    sell_event = {
        "schema":
            "ZITAR_MASTER_TRADE_EVENT_V1",

        "source_trade_id":
            "BRIDGE_SANDBOX_SELL_001",

        "strategy":
            "SMA20_50",

        "symbol":
            "TESTTRY",

        "side":
            "SELL",

        "reference_price":
            "105.00",

        # Yine bilerek kullanılmaması gereken fiyat.
        "modeled_fill_price":
            "1.00"
    }

    sell_result = execute_event(
        restarted,
        sell_event
    )

    print(
        "SELL:",
        sell_result
    )

    if not sell_result.startswith(
        "SOLD REALIZED_PNL="
    ):
        raise RuntimeError(
            "FAIL: SELL"
        )

    engine.assert_identity(
        restarted
    )

    print(
        "FINAL EQUITY:",
        restarted["account"]["equity_try"]
    )

    if restarted[
        "account"
    ]["equity_try"] != "10045.81":
        raise RuntimeError(
            "FAIL: final equity"
        )

    # -----------------------------------------
    # Restart + duplicate SELL
    # -----------------------------------------

    del restarted

    restarted_again = load_json(
        SANDBOX
    )

    duplicate_sell = execute_event(
        restarted_again,
        sell_event
    )

    print(
        "DUPLICATE SELL AFTER RESTART:",
        duplicate_sell
    )

    if duplicate_sell != "DUPLICATE_EVENT":
        raise RuntimeError(
            "FAIL: duplicate SELL"
        )

    # -----------------------------------------
    # Gerçek Master kesinlikle değişmemeli.
    # -----------------------------------------

    if MASTER.read_bytes() != master_before:
        raise RuntimeError(
            "FAIL: REAL MASTER MODIFIED"
        )

    print()
    print("REFERENCE PRICE ROUTING: PASS")
    print("NO DOUBLE SLIPPAGE INPUT: PASS")
    print("ENGINE SANDBOX WRITE: PASS")
    print("RESTART PERSISTENCE: PASS")
    print("DUPLICATE BUY BLOCK: PASS")
    print("DUPLICATE SELL BLOCK: PASS")
    print("ACCOUNTING IDENTITY: PASS")
    print("REAL MASTER UNCHANGED: PASS")
    print()
    print("sandbox:", SANDBOX)
    print("STATUS: PASS")


if __name__ == "__main__":
    main()
