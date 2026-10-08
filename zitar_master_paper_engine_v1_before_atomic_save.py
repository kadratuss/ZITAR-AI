from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ŞİMDİLİK SADECE TEST STATE.
STATE = BASE / "zitar_master_paper_test_state_v1.json"

INITIAL_CAPITAL = Decimal("10000.00")
MAX_POSITIONS = 10

FEE_RATE = Decimal("0.001")
SLIPPAGE_RATE = Decimal("0.001")

MONEY = Decimal("0.01")
QTY = Decimal("0.00000001")


def money(v: Decimal) -> Decimal:
    return v.quantize(
        MONEY,
        rounding=ROUND_HALF_UP
    )


def qty(v: Decimal) -> Decimal:
    return v.quantize(
        QTY,
        rounding=ROUND_HALF_UP
    )


def now_utc() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def default_state() -> dict:

    capital = money(INITIAL_CAPITAL)

    return {
        "schema":
            "ZITAR_MASTER_PAPER_TEST_STATE_V1",

        "mode":
            "TEST_ONLY",

        "authorities": {
            "paper_order": False,
            "real_order": False,
            "modify_master": False,
            "modify_v3": False
        },

        "rules": {
            "initial_capital_try":
                str(capital),

            "max_positions":
                MAX_POSITIONS,

            "fee_rate":
                str(FEE_RATE),

            "slippage_rate":
                str(SLIPPAGE_RATE)
        },

        "account": {
            "cash_try":
                str(capital),

            "positions": {},

            "position_market_value_try":
                "0.00",

            "realized_pnl_try":
                "0.00",

            "unrealized_pnl_try":
                "0.00",

            "equity_try":
                str(capital),

            "open_position_count":
                0
        },

        "processed_event_ids": [],

        "created_utc":
            now_utc(),

        "last_updated_utc":
            now_utc()
    }


def save(state: dict) -> None:

    state["last_updated_utc"] = now_utc()

    STATE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def load() -> dict:

    if not STATE.exists():
        state = default_state()
        save(state)
        return state

    return json.loads(
        STATE.read_text(
            encoding="utf-8-sig"
        )
    )


def D(value) -> Decimal:
    return Decimal(str(value))


def slot_budget(state: dict) -> Decimal:

    # Gerçek Master entegrasyonunda slot bütçesi
    # gün başlangıcında sabitlenir.
    #
    # Gün içindeki realized/unrealized değişimleri
    # yeni pozisyon büyüklüğünü değiştirmez.
    #
    # Yeni slot bütçesi yalnız 00:00 Türkiye
    # rollover sonrasında hesaplanır.

    if "current_period" in state:

        value = state[
            "current_period"
        ].get(
            "spot_slot_budget_try"
        )

        if value is not None:
            return money(D(value))

    # İzole test state için fallback.
    initial = D(
        state["rules"][
            "initial_capital_try"
        ]
    )

    return money(
        initial /
        Decimal(MAX_POSITIONS)
    )


def recalculate(
    state: dict,
    marks: dict[str, Decimal] | None = None
) -> None:

    account = state["account"]
    positions = account["positions"]

    cash = D(account["cash_try"])

    market_value = Decimal("0")
    unrealized = Decimal("0")

    for symbol, pos in positions.items():

        quantity = D(pos["quantity"])
        entry_total = D(
            pos["total_cost_try"]
        )

        if marks and symbol in marks:
            mark = D(marks[symbol])
            pos["last_mark_price"] = str(mark)
        else:
            mark = D(
                pos.get(
                    "last_mark_price",
                    pos["entry_reference_price"]
                )
            )

        value = quantity * mark
        pnl = value - entry_total

        pos["market_value_try"] = str(
            money(value)
        )

        pos["unrealized_pnl_try"] = str(
            money(pnl)
        )

        market_value += value
        unrealized += pnl

    equity = cash + market_value

    account[
        "position_market_value_try"
    ] = str(money(market_value))

    account[
        "unrealized_pnl_try"
    ] = str(money(unrealized))

    account[
        "equity_try"
    ] = str(money(equity))

    account[
        "open_position_count"
    ] = len(positions)


def assert_identity(state: dict) -> None:

    a = state["account"]

    cash = D(a["cash_try"])
    value = D(
        a["position_market_value_try"]
    )
    equity = D(a["equity_try"])

    if money(cash + value) != money(equity):
        raise RuntimeError(
            "ACCOUNTING IDENTITY FAIL: "
            "cash + position value != equity"
        )


def buy(
    state: dict,
    symbol: str,
    strategy: str,
    reference_price: Decimal,
    event_id: str
) -> str:

    if event_id in state["processed_event_ids"]:
        return "DUPLICATE_EVENT"

    account = state["account"]
    positions = account["positions"]

    # Aynı sembol açıksa yeni sermaye ayırma.
    if symbol in positions:

        supporters = positions[
            symbol
        ].setdefault(
            "strategy_support",
            []
        )

        if strategy not in supporters:
            supporters.append(strategy)

        state[
            "processed_event_ids"
        ].append(event_id)

        recalculate(state)
        assert_identity(state)
        save(state)

        return "SUPPORT_ADDED"

    if len(positions) >= MAX_POSITIONS:
        return "MAX_POSITIONS"

    budget = slot_budget(state)
    cash = D(account["cash_try"])

    if cash < budget:
        return "INSUFFICIENT_CASH"

    # BUY için olumsuz slippage:
    # referans fiyatın %0.1 üstü.
    fill_price = (
        reference_price *
        (
            Decimal("1") +
            SLIPPAGE_RATE
        )
    )

    # Budget toplam cash çıkışıdır.
    # gross + fee = budget
    gross = (
        budget /
        (
            Decimal("1") +
            FEE_RATE
        )
    )

    fee = gross * FEE_RATE

    quantity = qty(
        gross / fill_price
    )

    actual_gross = (
        quantity * fill_price
    )

    actual_fee = (
        actual_gross * FEE_RATE
    )

    total_cost = (
        actual_gross +
        actual_fee
    )

    if total_cost > cash:
        raise RuntimeError(
            "BUY COST EXCEEDS CASH"
        )

    account["cash_try"] = str(
        money(
            cash - total_cost
        )
    )

    positions[symbol] = {
        "symbol":
            symbol,

        "strategy_support": [
            strategy
        ],

        "quantity":
            str(quantity),

        "entry_reference_price":
            str(reference_price),

        "entry_fill_price":
            str(fill_price),

        "gross_try":
            str(money(actual_gross)),

        "entry_fee_try":
            str(money(actual_fee)),

        "total_cost_try":
            str(money(total_cost)),

        "last_mark_price":
            str(reference_price),

        "opened_utc":
            now_utc(),

        "source_event_id":
            event_id
    }

    state[
        "processed_event_ids"
    ].append(event_id)

    recalculate(state)
    assert_identity(state)
    save(state)

    return "BOUGHT"


def remove_support_or_sell(
    state: dict,
    symbol: str,
    strategy: str,
    reference_price: Decimal,
    event_id: str
) -> str:

    if event_id in state["processed_event_ids"]:
        return "DUPLICATE_EVENT"

    account = state["account"]
    positions = account["positions"]

    if symbol not in positions:
        state[
            "processed_event_ids"
        ].append(event_id)
        save(state)
        return "NO_POSITION"

    pos = positions[symbol]

    supporters = pos.setdefault(
        "strategy_support",
        []
    )

    if strategy in supporters:
        supporters.remove(strategy)

    # Başka strateji hâlâ destekliyorsa
    # pozisyon açık kalır.
    if supporters:

        state[
            "processed_event_ids"
        ].append(event_id)

        recalculate(
            state,
            {symbol: reference_price}
        )

        assert_identity(state)
        save(state)

        return "SUPPORT_REMOVED_POSITION_HELD"

    quantity = D(pos["quantity"])

    # SELL için olumsuz slippage:
    # referans fiyatın %0.1 altı.
    fill_price = (
        reference_price *
        (
            Decimal("1") -
            SLIPPAGE_RATE
        )
    )

    gross = quantity * fill_price
    fee = gross * FEE_RATE
    proceeds = gross - fee

    total_cost = D(
        pos["total_cost_try"]
    )

    realized = (
        proceeds -
        total_cost
    )

    old_realized = D(
        account["realized_pnl_try"]
    )

    cash = D(
        account["cash_try"]
    )

    account["cash_try"] = str(
        money(
            cash + proceeds
        )
    )

    account[
        "realized_pnl_try"
    ] = str(
        money(
            old_realized +
            realized
        )
    )

    del positions[symbol]

    state[
        "processed_event_ids"
    ].append(event_id)

    recalculate(state)
    assert_identity(state)
    save(state)

    return (
        "SOLD "
        f"REALIZED_PNL={money(realized)}"
    )


def print_state(
    state: dict,
    title: str
) -> None:

    a = state["account"]

    print()
    print(title)
    print("-" * len(title))

    print(
        "cash:",
        a["cash_try"]
    )

    print(
        "positions:",
        a["open_position_count"]
    )

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

    print(
        "equity:",
        a["equity_try"]
    )


def main():

    # Her test çalışmasında temiz test state.
    if STATE.exists():
        STATE.unlink()

    state = load()

    print("ZITAR MASTER PAPER ENGINE V1")
    print("MULTI-STRATEGY SUPPORT TEST")
    print(
        "ISOLATED TEST ONLY • "
        "NO MASTER WRITE • NO V3 WRITE"
    )

    print_state(
        state,
        "INITIAL"
    )

    # -------------------------------------------------
    # 1) SMA BUY -> gerçek pozisyon açılmalı
    # -------------------------------------------------

    r = buy(
        state,
        symbol="TESTTRY",
        strategy="SMA20_50",
        reference_price=Decimal("100.00"),
        event_id="TEST_SMA_BUY_001"
    )

    print()
    print("SMA BUY:", r)

    # -------------------------------------------------
    # 2) EMA BUY -> ikinci pozisyon açılmamalı.
    #    Sadece destek eklenmeli.
    # -------------------------------------------------

    r = buy(
        state,
        symbol="TESTTRY",
        strategy="EMA12_26",
        reference_price=Decimal("101.00"),
        event_id="TEST_EMA_BUY_001"
    )

    print("EMA BUY:", r)

    pos = state["account"]["positions"]["TESTTRY"]

    print(
        "SUPPORTERS:",
        pos["strategy_support"]
    )

    print_state(
        state,
        "AFTER TWO BUY SIGNALS"
    )

    if state["account"]["open_position_count"] != 1:
        raise RuntimeError(
            "FAIL: duplicate symbol position created"
        )

    if set(pos["strategy_support"]) != {
        "SMA20_50",
        "EMA12_26"
    }:
        raise RuntimeError(
            "FAIL: strategy support mismatch"
        )

    # -------------------------------------------------
    # 3) Fiyat 105
    # -------------------------------------------------

    recalculate(
        state,
        {
            "TESTTRY":
                Decimal("105.00")
        }
    )

    assert_identity(state)
    save(state)

    print_state(
        state,
        "MARK 105"
    )

    # -------------------------------------------------
    # 4) SMA SELL
    #    EMA desteği kaldığı için pozisyon kapanmamalı.
    # -------------------------------------------------

    r = remove_support_or_sell(
        state,
        symbol="TESTTRY",
        strategy="SMA20_50",
        reference_price=Decimal("105.00"),
        event_id="TEST_SMA_SELL_001"
    )

    print()
    print("SMA SELL:", r)

    if "TESTTRY" not in state["account"]["positions"]:
        raise RuntimeError(
            "FAIL: position closed while EMA support remained"
        )

    pos = state["account"]["positions"]["TESTTRY"]

    print(
        "SUPPORTERS AFTER SMA SELL:",
        pos["strategy_support"]
    )

    if pos["strategy_support"] != ["EMA12_26"]:
        raise RuntimeError(
            "FAIL: EMA support should remain"
        )

    print_state(
        state,
        "AFTER SMA SELL"
    )

    # -------------------------------------------------
    # 5) EMA SELL
    #    Son destek kalkıyor -> pozisyon kapanmalı.
    # -------------------------------------------------

    r = remove_support_or_sell(
        state,
        symbol="TESTTRY",
        strategy="EMA12_26",
        reference_price=Decimal("105.00"),
        event_id="TEST_EMA_SELL_001"
    )

    print()
    print("EMA SELL:", r)

    print_state(
        state,
        "AFTER EMA SELL"
    )

    if state["account"]["open_position_count"] != 0:
        raise RuntimeError(
            "FAIL: position should be closed"
        )

    if "TESTTRY" in state["account"]["positions"]:
        raise RuntimeError(
            "FAIL: TESTTRY still exists"
        )

    # -------------------------------------------------
    # 6) Duplicate koruması
    # -------------------------------------------------

    r = remove_support_or_sell(
        state,
        symbol="TESTTRY",
        strategy="EMA12_26",
        reference_price=Decimal("105.00"),
        event_id="TEST_EMA_SELL_001"
    )

    print()
    print(
        "DUPLICATE EMA SELL:",
        r
    )

    if r != "DUPLICATE_EVENT":
        raise RuntimeError(
            "FAIL: duplicate protection failed"
        )

    assert_identity(state)

    print()
    print("MULTI-STRATEGY SUPPORT: PASS")
    print("SINGLE-SYMBOL POSITION: PASS")
    print("LAST-SUPPORT CLOSE: PASS")
    print("DUPLICATE PROTECTION: PASS")
    print("ACCOUNTING IDENTITY: PASS")

    print()
    print(
        "test state:",
        STATE
    )

    print("STATUS: PASS")


if __name__ == "__main__":
    main()
