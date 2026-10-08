from pathlib import Path

P = Path("zitar_master_paper_engine_v1.py")

text = P.read_text(
    encoding="utf-8-sig"
)

old = '''    account[
        "open_position_count"
    ] = len(positions)


def assert_identity(state: dict) -> None:
'''

new = '''    account[
        "open_position_count"
    ] = len(positions)

    # Gerçek Master state kullanılıyorsa,
    # hesap equity'sini günlük muhasebe dönemiyle
    # aynı anda senkron tut.
    if "current_period" in state:

        period = state["current_period"]

        current_equity = money(equity)

        period[
            "current_equity_try"
        ] = str(current_equity)

        start_equity = D(
            period["start_equity_try"]
        )

        if start_equity != 0:
            daily_return = (
                (
                    current_equity -
                    start_equity
                )
                /
                start_equity
                *
                Decimal("100")
            )
        else:
            daily_return = Decimal("0")

        period[
            "daily_return_pct"
        ] = str(
            daily_return.quantize(
                Decimal("0.0001"),
                rounding=ROUND_HALF_UP
            )
        )


def assert_identity(state: dict) -> None:
'''

count = text.count(old)

if count != 1:
    raise SystemExit(
        f"FAIL: recalculate insertion point count={count}"
    )

text = text.replace(
    old,
    new,
    1
)

P.write_text(
    text,
    encoding="utf-8"
)

print("MASTER PERIOD EQUITY SYNC PATCH PASS")
