from pathlib import Path

p = Path("zitar_master_portfolio_v1.py")
s = p.read_text(encoding="utf-8-sig")

needle = '''def save_state(state: dict) -> None:

    state["last_updated_utc"] = now_utc().isoformat()

    STATE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )
'''

insert = needle + '''

def append_daily_record(record: dict) -> None:

    with DAILY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":")
            ) + "\\n"
        )


def rollover_if_needed(state: dict) -> bool:

    period = state["current_period"]
    today = current_period_id()

    if period["period_id"] == today:
        return False

    start_equity = Decimal(
        period["start_equity_try"]
    )

    closing_equity = Decimal(
        period["current_equity_try"]
    )

    realized = Decimal(
        period["daily_realized_pnl_try"]
    )

    equity_change = (
        closing_equity - start_equity
    )

    if start_equity != 0:
        equity_return_pct = (
            equity_change /
            start_equity *
            Decimal("100")
        )
    else:
        equity_return_pct = Decimal("0")

    record = {
        "schema":
            "ZITAR_DAILY_PERFORMANCE_V1",

        "period_id":
            period["period_id"],

        "timezone":
            state["timezone"],

        "start_equity_try":
            str(money(start_equity)),

        "closing_equity_try":
            str(money(closing_equity)),

        "realized_pnl_try":
            str(money(realized)),

        "equity_change_try":
            str(money(equity_change)),

        "equity_return_pct":
            str(
                equity_return_pct.quantize(
                    Decimal("0.0001"),
                    rounding=ROUND_HALF_UP
                )
            ),

        "closed_trade_count":
            int(
                period.get(
                    "closed_trade_count",
                    0
                )
            ),

        "archived_utc":
            now_utc().isoformat()
    }

    append_daily_record(record)

    max_positions = int(
        state["rules"]["max_spot_positions"]
    )

    new_slot_budget = money(
        closing_equity /
        Decimal(max_positions)
    )

    state["current_period"] = {
        "period_id": today,

        "start_equity_try":
            str(money(closing_equity)),

        "current_equity_try":
            str(money(closing_equity)),

        "daily_realized_pnl_try":
            "0.00",

        "daily_return_pct":
            "0.0000",

        "closed_trade_count":
            0,

        "spot_slot_budget_try":
            str(new_slot_budget)
    }

    save_state(state)

    return True
'''

if needle not in s:
    raise SystemExit("PATCH FAIL: save_state block not found")

s = s.replace(needle, insert, 1)

old = '''    state = load_state()

    period = state["current_period"]
'''

new = '''    state = load_state()

    rolled = rollover_if_needed(state)

    period = state["current_period"]
'''

if old not in s:
    raise SystemExit("PATCH FAIL: main block not found")

s = s.replace(old, new, 1)

old2 = '''    print()
    print("timezone:", state["timezone"])
'''

new2 = '''    print()
    print(
        "rollover:",
        "PERFORMED" if rolled else "NOT_REQUIRED"
    )

    print("timezone:", state["timezone"])
'''

if old2 not in s:
    raise SystemExit("PATCH FAIL: print block not found")

s = s.replace(old2, new2, 1)

p.write_text(s, encoding="utf-8")

print("MASTER DAILY ROLLOVER PATCH PASS")
