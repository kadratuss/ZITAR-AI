from pathlib import Path

P = Path("zitar_master_paper_engine_v1.py")

text = P.read_text(
    encoding="utf-8-sig"
)

old = '''    account[
        "realized_pnl_try"
    ] = str(
        money(
            old_realized +
            realized
        )
    )

    del positions[symbol]
'''

new = '''    realized_money = money(realized)

    account[
        "realized_pnl_try"
    ] = str(
        money(
            old_realized +
            realized_money
        )
    )

    # Gerçek Master state kullanılıyorsa
    # yalnızca GERÇEK pozisyon kapanışını
    # günlük ve lifetime muhasebeye ekle.
    #
    # DUPLICATE_EVENT, NO_POSITION ve
    # SUPPORT_REMOVED_POSITION_HELD
    # bu noktaya ulaşmaz.

    if "current_period" in state:

        period = state["current_period"]

        old_daily_realized = D(
            period.get(
                "daily_realized_pnl_try",
                "0.00"
            )
        )

        period[
            "daily_realized_pnl_try"
        ] = str(
            money(
                old_daily_realized +
                realized_money
            )
        )

        period[
            "closed_trade_count"
        ] = int(
            period.get(
                "closed_trade_count",
                0
            )
        ) + 1

    if "lifetime" in state:

        lifetime = state["lifetime"]

        old_lifetime_realized = D(
            lifetime.get(
                "total_realized_pnl_try",
                "0.00"
            )
        )

        lifetime[
            "total_realized_pnl_try"
        ] = str(
            money(
                old_lifetime_realized +
                realized_money
            )
        )

        lifetime[
            "closed_trade_count"
        ] = int(
            lifetime.get(
                "closed_trade_count",
                0
            )
        ) + 1

    del positions[symbol]
'''

count = text.count(old)

if count != 1:
    raise SystemExit(
        f"FAIL: SELL accounting insertion count={count}"
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

print("MASTER REALIZED ACCOUNTING SYNC PATCH PASS")
print("replacements:", count)
