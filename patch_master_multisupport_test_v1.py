from pathlib import Path

p = Path("zitar_master_paper_engine_v1.py")
s = p.read_text(encoding="utf-8-sig")

start = s.find("def main():")

if start == -1:
    raise SystemExit("FAIL: main() not found")

new_main = '''def main():

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
'''

s = s[:start] + new_main

p.write_text(
    s,
    encoding="utf-8"
)

print("MULTI-SUPPORT TEST PATCH PASS")
