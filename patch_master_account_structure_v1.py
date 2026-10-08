from pathlib import Path

p = Path("zitar_master_portfolio_v1.py")
s = p.read_text(encoding="utf-8-sig")

old = '''        "current_period": {
            "period_id": current_period_id(),
            "start_equity_try": str(capital),
            "current_equity_try": str(capital),

            "daily_realized_pnl_try": "0.00",
            "daily_return_pct": "0.0000",

            "closed_trade_count": 0,

            "spot_slot_budget_try": str(slot_budget)
        },'''

new = '''        "account": {
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
        },'''

if old not in s:
    raise SystemExit(
        "FAIL: default_state target not found"
    )

s = s.replace(old, new, 1)


marker = '''def main():

    state = load_state()
'''

replacement = '''def ensure_account_structure(state: dict) -> None:

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
'''

if marker not in s:
    raise SystemExit(
        "FAIL: main target not found"
    )

s = s.replace(marker, replacement, 1)


old_print = '''    period = state["current_period"]

    print("ZITAR MASTER PORTFOLIO V1")'''

new_print = '''    period = state["current_period"]
    account = state["account"]

    print("ZITAR MASTER PORTFOLIO V1")'''

if old_print not in s:
    raise SystemExit(
        "FAIL: print target not found"
    )

s = s.replace(
    old_print,
    new_print,
    1
)


anchor = '''    print(
        "start equity:",
        period["start_equity_try"],
        "TRY"
    )
'''

addition = '''    print(
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
'''

if anchor not in s:
    raise SystemExit(
        "FAIL: output anchor not found"
    )

s = s.replace(
    anchor,
    addition,
    1
)

p.write_text(
    s,
    encoding="utf-8"
)

print("MASTER ACCOUNT STRUCTURE PATCH PASS")
