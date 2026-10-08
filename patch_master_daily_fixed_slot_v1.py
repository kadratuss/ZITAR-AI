from pathlib import Path

p = Path("zitar_master_paper_engine_v1.py")
s = p.read_text(encoding="utf-8-sig")

old = '''def slot_budget(state: dict) -> Decimal:

    equity = D(
        state["account"]["equity_try"]
    )

    return money(
        equity /
        Decimal(MAX_POSITIONS)
    )
'''

new = '''def slot_budget(state: dict) -> Decimal:

    # Gün içinde slot büyüklüğü sabittir.
    # Yeni slot bütçesi yalnız günlük rollover
    # sonrasında değiştirilir.

    if "current_period" in state:

        value = state[
            "current_period"
        ].get(
            "spot_slot_budget_try"
        )

        if value is not None:
            return money(D(value))

    # İzole test state fallback.
    initial = D(
        state["rules"][
            "initial_capital_try"
        ]
    )

    return money(
        initial /
        Decimal(MAX_POSITIONS)
    )
'''

if old not in s:
    raise SystemExit(
        "FAIL: slot_budget target not found"
    )

s = s.replace(old, new, 1)

p.write_text(
    s,
    encoding="utf-8"
)

print("DAILY FIXED SLOT PATCH PASS")
