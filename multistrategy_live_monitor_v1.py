import csv
import json
import time
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path

import requests

getcontext().prec = 28
D = Decimal

ROOT = Path(__file__).resolve().parent

STATE   = ROOT / "multistrategy_live_state_v1.json"
SIGNALS = ROOT / "multistrategy_live_signals_v1.csv"
TRADES  = ROOT / "multistrategy_live_trades_v1.csv"
RUNS    = ROOT / "multistrategy_live_runs_v1.csv"

TICKER_API = "https://api.binance.me/api/v3/ticker/price"

STRATEGIES = [
    "SMA20_50",
    "EMA12_26",
    "RSI14"
]

def money(x):
    return f"{D(str(x)):,.2f}"

def pct(x):
    return f"{D(str(x)):.2f}%"

def read_csv(path):
    if not path.exists():
        return []

    with path.open(
        "r",
        newline="",
        encoding="utf-8"
    ) as f:
        return list(csv.DictReader(f))

def get_price(symbol):
    last_error = None

    for attempt in range(4):
        try:
            r = requests.get(
                TICKER_API,
                params={"symbol": symbol},
                timeout=15
            )
            r.raise_for_status()
            j = r.json()
            return D(str(j["price"]))

        except Exception as e:
            last_error = e

            if attempt < 3:
                time.sleep(1)

    raise RuntimeError(last_error)

if not STATE.exists():
    raise SystemExit(
        "multistrategy_live_state_v1.json bulunamadi."
    )

state = json.loads(
    STATE.read_text(encoding="utf-8")
)

signals = read_csv(SIGNALS)
trades  = read_csv(TRADES)
runs    = read_csv(RUNS)

now = datetime.now(timezone.utc)

print()
print("=" * 94)
print("PORTFOLIOAI - MULTISTRATEGY LIVE MONITOR V1")
print("=" * 94)

print("UTC NOW        :", now.isoformat())
print("EXPERIMENT     :", state.get("experiment"))
print("STATUS         :", state.get("status"))
print("FREEZE UTC     :", state.get("created_at_utc"))
print("REAL MONEY     :", state["rules"].get("real_money"))
print()

# ----------------------------------------------------------------
# DATA / AUTOMATION HEALTH
# ----------------------------------------------------------------

print("=" * 94)
print("DATA / AUTOMATION HEALTH")
print("=" * 94)

print("Successful runs :", len(runs))
print("Signal rows     :", len(signals))
print("Trade rows      :", len(trades))

health_ok = True

if runs:
    last_run = runs[-1]

    print("Last run UTC    :", last_run.get("run_utc"))
    print("Last candle     :", last_run.get("candle_close_utc"))
    print("Last symbols    :", last_run.get("symbols"))
    print("Last sig rows   :", last_run.get("signal_rows"))
    print("Last trades     :", last_run.get("paper_trades"))
    print("Last status     :", last_run.get("status"))

    if (
        last_run.get("status") != "OK"
        or int(last_run.get("symbols", 0)) != 21
        or int(last_run.get("signal_rows", 0)) != 63
    ):
        health_ok = False
else:
    print("Last run        : YOK")
    health_ok = False

# Her basarili run 63 signal row olmali.
expected_signal_rows = len(runs) * 63

if len(signals) != expected_signal_rows:
    health_ok = False

print(
    "Expected signals:",
    expected_signal_rows
)

print(
    "Signal integrity:",
    "OK"
    if len(signals) == expected_signal_rows
    else "HATA"
)

# Candle continuity
candle_times = []

for r in runs:
    try:
        t = datetime.fromisoformat(
            r["candle_close_utc"].replace(
                "Z", "+00:00"
            )
        )
        candle_times.append(t)
    except Exception:
        health_ok = False

gaps = []

for a, b in zip(
    candle_times,
    candle_times[1:]
):
    diff = (
        b - a
    ).total_seconds()

    if diff != 3600:
        gaps.append(
            (
                a.isoformat(),
                b.isoformat(),
                diff
            )
        )

if gaps:
    health_ok = False

print(
    "Hourly continuity:",
    "OK"
    if not gaps
    else f"GAP={len(gaps)}"
)

if gaps:
    for g in gaps[-5:]:
        print(
            "  GAP:",
            g[0],
            "->",
            g[1],
            "seconds=",
            g[2]
        )

print(
    "OVERALL HEALTH  :",
    "OK" if health_ok else "CHECK"
)

# ----------------------------------------------------------------
# COLLECT ONLY PRICES ACTUALLY NEEDED
# ----------------------------------------------------------------

symbols_needed = set()

for strategy in STRATEGIES:

    account = state["strategies"][strategy]

    for symbol in account["positions"]:
        symbols_needed.add(symbol)

prices = {}
price_errors = {}

for symbol in sorted(symbols_needed):

    try:
        prices[symbol] = get_price(symbol)

    except Exception as e:
        price_errors[symbol] = str(e)

# ----------------------------------------------------------------
# PORTFOLIO SUMMARY
# ----------------------------------------------------------------

print()
print("=" * 94)
print("LIVE PORTFOLIO SUMMARY")
print("=" * 94)

header = (
    f"{'STRATEGY':<12}"
    f"{'CASH':>14}"
    f"{'POS VALUE':>14}"
    f"{'EQUITY':>14}"
    f"{'REALIZED':>14}"
    f"{'UNREAL':>14}"
    f"{'RETURN':>11}"
    f"{'POS':>6}"
    f"{'TRADES':>8}"
)

print(header)
print("-" * 94)

summary = {}

for strategy in STRATEGIES:

    account = state["strategies"][strategy]

    initial = D(
        account.get(
            "initial_cash_try",
            "10000"
        )
    )

    cash = D(account["cash_try"])
    realized = D(
        account["realized_pnl_try"]
    )

    pos_value = D(0)
    unrealized = D(0)
    valuation_complete = True

    for symbol, p in account["positions"].items():

        if symbol not in prices:
            valuation_complete = False
            continue

        qty = D(p["quantity"])
        price = prices[symbol]
        cost = D(p["total_cost_try"])

        # Conservative liquidation value:
        # current price - modeled slippage - fee
        slip = D(
            state["rules"]["slippage_rate"]
        )

        fee_rate = D(
            state["rules"]["fee_rate"]
        )

        liquidation = (
            qty
            * price
            * (D(1) - slip)
            * (D(1) - fee_rate)
        )

        pos_value += liquidation
        unrealized += (
            liquidation - cost
        )

    equity = cash + pos_value

    ret = (
        (equity - initial)
        / initial
        * D(100)
    )

    summary[strategy] = {
        "cash": cash,
        "pos_value": pos_value,
        "equity": equity,
        "realized": realized,
        "unrealized": unrealized,
        "return": ret,
        "positions": len(
            account["positions"]
        ),
        "trades": int(
            account["trade_count"]
        ),
        "complete": valuation_complete
    }

    marker = "" if valuation_complete else "*"

    print(
        f"{strategy:<12}"
        f"{cash:>14.2f}"
        f"{pos_value:>14.2f}"
        f"{equity:>14.2f}"
        f"{realized:>14.2f}"
        f"{unrealized:>14.2f}"
        f"{ret:>10.2f}%"
        f"{len(account['positions']):>6}"
        f"{int(account['trade_count']):>8}"
        f"{marker}"
    )

# ----------------------------------------------------------------
# OPEN POSITIONS
# ----------------------------------------------------------------

print()
print("=" * 94)
print("OPEN POSITIONS")
print("=" * 94)

any_position = False

for strategy in STRATEGIES:

    account = state["strategies"][strategy]

    if not account["positions"]:
        continue

    any_position = True

    print()
    print(strategy)
    print("-" * 94)

    print(
        f"{'SYMBOL':<14}"
        f"{'QTY':>16}"
        f"{'ENTRY':>14}"
        f"{'LIVE':>14}"
        f"{'COST':>14}"
        f"{'LIQ VALUE':>14}"
        f"{'UPNL':>14}"
    )

    for symbol, p in sorted(
        account["positions"].items()
    ):

        qty = D(p["quantity"])
        entry = D(
            p["modeled_entry_price"]
        )
        cost = D(
            p["total_cost_try"]
        )

        if symbol not in prices:

            print(
                f"{symbol:<14}"
                f"{str(qty):>16}"
                f"{entry:>14.8f}"
                f"{'PRICE ERROR':>14}"
            )
            continue

        live = prices[symbol]

        slip = D(
            state["rules"]["slippage_rate"]
        )

        fee_rate = D(
            state["rules"]["fee_rate"]
        )

        liq = (
            qty
            * live
            * (D(1)-slip)
            * (D(1)-fee_rate)
        )

        upnl = liq-cost

        print(
            f"{symbol:<14}"
            f"{str(qty):>16}"
            f"{entry:>14.8f}"
            f"{live:>14.8f}"
            f"{cost:>14.2f}"
            f"{liq:>14.2f}"
            f"{upnl:>14.2f}"
        )

if not any_position:
    print("Henuz acik pozisyon yok.")

# ----------------------------------------------------------------
# RECENT SIGNALS
# ----------------------------------------------------------------

print()
print("=" * 94)
print("LATEST NON-NONE SIGNALS")
print("=" * 94)

non_none = [
    x for x in signals
    if x.get("signal") in (
        "BUY",
        "SELL"
    )
]

if non_none:

    for x in non_none[-20:]:

        print(
            x.get("candle_close_utc"),
            f"{x.get('strategy'):<10}",
            f"{x.get('symbol'):<12}",
            x.get("signal")
        )
else:
    print("Henuz BUY/SELL crossover yok.")

# ----------------------------------------------------------------
# RECENT TRADES
# ----------------------------------------------------------------

print()
print("=" * 94)
print("LATEST PAPER TRADES")
print("=" * 94)

if trades:

    for t in trades[-20:]:

        print(
            t.get("executed_at_utc"),
            f"{t.get('strategy'):<10}",
            f"{t.get('symbol'):<12}",
            f"{t.get('side'):<4}",
            "fill=",
            t.get("modeled_fill_price"),
            "qty=",
            t.get("quantity")
        )
else:
    print("Henuz paper trade yok.")

# ----------------------------------------------------------------
# PRICE ERRORS
# ----------------------------------------------------------------

if price_errors:

    print()
    print("=" * 94)
    print("PRICE ERRORS")
    print("=" * 94)

    for symbol, err in price_errors.items():
        print(symbol, "->", err)

print()
print("=" * 94)
print("MONITOR COMPLETE")
print("=" * 94)
print("READ ONLY          : YES")
print("REAL ORDERS        : NO")
print("STATE MODIFICATION : NO")
print()
