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

STATE  = ROOT / "multistrategy_live_state_v1.json"
RUNS   = ROOT / "multistrategy_live_runs_v1.csv"
TRADES = ROOT / "multistrategy_live_trades_v1.csv"
CONFIG = ROOT / "multistrategy_risk_config_v1.json"

PEAKS  = ROOT / "multistrategy_risk_peaks_v3.json"
STATUS = ROOT / "multistrategy_risk_status_v3.json"

TICKER_API = "https://api.binance.me/api/v3/ticker/price"

STRATEGIES = [
    "SMA20_50",
    "EMA12_26",
    "RSI14"
]


def read_csv(path):
    if not path.exists():
        return []

    with path.open(
        "r",
        newline="",
        encoding="utf-8"
    ) as f:
        return list(csv.DictReader(f))


def parse_iso(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


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

            return D(str(r.json()["price"]))

        except Exception as e:
            last_error = e

            if attempt < 3:
                time.sleep(1)

    raise RuntimeError(last_error)


def get_trade_time(row):
    for key in (
        "executed_at_utc",
        "execution_time_utc",
        "run_utc",
        "timestamp_utc"
    ):
        value = row.get(key)

        if value:
            try:
                return parse_iso(value)
            except Exception:
                pass

    return None


def get_realized_from_trade(row):
    """
    SELL satirinda realized PnL alani varsa kullan.
    Farkli olasi kolon adlarini kontrollu sekilde destekler.

    BUY islemleri realized PnL sayilmaz.
    """

    if str(row.get("side", "")).upper() != "SELL":
        return D(0)

    for key in (
        "realized_pnl_try",
        "realized_pnl",
        "pnl_try",
        "realized"
    ):
        value = row.get(key)

        if value not in (None, ""):
            try:
                return D(str(value))
            except Exception:
                return D(0)

    return D(0)


def daily_realized_pnl(
    trades,
    strategy,
    utc_date
):
    total = D(0)
    matched_sells = 0

    for row in trades:

        if row.get("strategy") != strategy:
            continue

        if str(
            row.get("side", "")
        ).upper() != "SELL":
            continue

        t = get_trade_time(row)

        if t is None:
            continue

        if t.astimezone(
            timezone.utc
        ).date() != utc_date:
            continue

        total += get_realized_from_trade(row)
        matched_sells += 1

    return total, matched_sells


def evaluate_policy(
    *,
    initial,
    cash,
    position_count,
    invested_cost,
    daily_realized,
    equity,
    peak,
    global_reasons,
    max_positions,
    max_invested_fraction,
    daily_loss_fraction,
    dd_fraction
):
    """
    Pure risk decision function.

    Canli dosyalara veya API'ye dokunmaz.
    Self-test bunun uzerinden calisir.
    """

    reasons = list(global_reasons)

    if position_count >= max_positions:
        reasons.append(
            "MAX_POSITIONS"
        )

    max_invested = (
        initial
        * max_invested_fraction
    )

    if invested_cost >= max_invested:
        reasons.append(
            "MAX_INVESTED_CAPITAL"
        )

    daily_loss_limit = (
        initial
        * daily_loss_fraction
    )

    if daily_realized <= -daily_loss_limit:
        reasons.append(
            "DAILY_REALIZED_LOSS_LIMIT"
        )

    if peak > 0:
        drawdown = (
            peak - equity
        ) / peak
    else:
        drawdown = D(0)

    if drawdown >= dd_fraction:
        reasons.append(
            "EQUITY_DRAWDOWN_KILL"
        )

    return {
        "buy_allowed":
            len(reasons) == 0,

        # Spotta risk azaltici SELL acik.
        "sell_allowed":
            True,

        "reasons":
            reasons,

        "drawdown":
            drawdown,

        "daily_loss_limit":
            daily_loss_limit,

        "max_invested":
            max_invested
    }


# ============================================================
# LOAD LIVE READ-ONLY INPUTS
# ============================================================

if not STATE.exists():
    raise SystemExit(
        "Live state bulunamadi."
    )

if not CONFIG.exists():
    raise SystemExit(
        "Risk config bulunamadi."
    )

state = json.loads(
    STATE.read_text(
        encoding="utf-8"
    )
)

config = json.loads(
    CONFIG.read_text(
        encoding="utf-8"
    )
)

runs = read_csv(RUNS)
trades = read_csv(TRADES)

now = datetime.now(timezone.utc)
today_utc = now.date()

fee = D(
    state["rules"]["fee_rate"]
)

slip = D(
    state["rules"]["slippage_rate"]
)


# ============================================================
# GLOBAL DATA HEALTH
# ============================================================

global_reasons = []
last_run = None
data_age_hours = None

if not runs:

    global_reasons.append(
        "NO_SUCCESSFUL_RUN"
    )

else:

    last_run = runs[-1]

    if (
        config["require_last_run_ok"]
        and last_run.get("status") != "OK"
    ):
        global_reasons.append(
            "LAST_RUN_NOT_OK"
        )

    if (
        config["require_21_symbols"]
        and int(
            last_run.get("symbols", 0)
        ) != 21
    ):
        global_reasons.append(
            "SYMBOL_COUNT_NOT_21"
        )

    if (
        config["require_63_signal_rows"]
        and int(
            last_run.get("signal_rows", 0)
        ) != 63
    ):
        global_reasons.append(
            "SIGNAL_ROWS_NOT_63"
        )

    try:
        last_close = parse_iso(
            last_run[
                "candle_close_utc"
            ]
        )

        data_age_hours = D(
            str(
                (
                    now - last_close
                ).total_seconds()
                / 3600
            )
        )

        if data_age_hours > D(
            str(
                config[
                    "max_data_age_hours"
                ]
            )
        ):
            global_reasons.append(
                "STALE_DATA"
            )

    except Exception:
        global_reasons.append(
            "INVALID_LAST_CANDLE_TIME"
        )


# ============================================================
# CURRENT PRICES
# ============================================================

needed_symbols = set()

for strategy in STRATEGIES:
    needed_symbols.update(
        state[
            "strategies"
        ][strategy][
            "positions"
        ].keys()
    )

prices = {}
price_errors = {}

for symbol in sorted(
    needed_symbols
):
    try:
        prices[symbol] = get_price(
            symbol
        )
    except Exception as e:
        price_errors[symbol] = str(e)

if price_errors:
    global_reasons.append(
        "LIVE_PRICE_ERROR"
    )


# ============================================================
# PEAK STATE
# ============================================================

if PEAKS.exists():
    peak_state = json.loads(
        PEAKS.read_text(
            encoding="utf-8"
        )
    )
else:
    peak_state = {
        "created_at_utc":
            now.isoformat(),
        "strategies": {}
    }


# ============================================================
# LIVE EVALUATION
# ============================================================

result = {
    "generated_at_utc":
        now.isoformat(),

    "utc_date":
        str(today_utc),

    "paper_only":
        True,

    "global": {
        "buy_allowed":
            len(global_reasons) == 0,

        "reasons":
            global_reasons,

        "data_age_hours":
            (
                str(data_age_hours)
                if data_age_hours
                is not None
                else None
            ),

        "price_errors":
            price_errors
    },

    "strategies": {}
}


for strategy in STRATEGIES:

    account = state[
        "strategies"
    ][strategy]

    initial = D(
        account.get(
            "initial_cash_try",
            "10000"
        )
    )

    cash = D(
        account["cash_try"]
    )

    positions = account[
        "positions"
    ]

    invested_cost = D(0)
    liquidation_value = D(0)
    valuation_complete = True

    for symbol, p in positions.items():

        cost = D(
            p["total_cost_try"]
        )

        invested_cost += cost

        if symbol not in prices:
            valuation_complete = False
            continue

        qty = D(
            p["quantity"]
        )

        live = prices[symbol]

        liquidation_value += (
            qty
            * live
            * (D(1) - slip)
            * (D(1) - fee)
        )

    local_global_reasons = list(
        global_reasons
    )

    if not valuation_complete:
        local_global_reasons.append(
            "INCOMPLETE_EQUITY_VALUATION"
        )

    equity = (
        cash
        + liquidation_value
    )

    old_peak = D(
        peak_state[
            "strategies"
        ].get(
            strategy,
            {}
        ).get(
            "peak_equity_try",
            str(initial)
        )
    )

    peak = max(
        initial,
        old_peak,
        equity
    )

    daily_realized, daily_sell_count = (
        daily_realized_pnl(
            trades,
            strategy,
            today_utc
        )
    )

    policy = evaluate_policy(
        initial=initial,
        cash=cash,
        position_count=len(
            positions
        ),
        invested_cost=invested_cost,
        daily_realized=daily_realized,
        equity=equity,
        peak=peak,
        global_reasons=
            local_global_reasons,

        max_positions=int(
            config[
                "max_positions_per_strategy"
            ]
        ),

        max_invested_fraction=D(
            config[
                "max_invested_fraction"
            ]
        ),

        daily_loss_fraction=D(
            config[
                "daily_realized_loss_limit_fraction"
            ]
        ),

        dd_fraction=D(
            config[
                "equity_drawdown_kill_fraction"
            ]
        )
    )

    peak_state[
        "strategies"
    ][strategy] = {
        "peak_equity_try":
            str(peak),

        "last_equity_try":
            str(equity),

        "last_drawdown_fraction":
            str(
                policy["drawdown"]
            ),

        "updated_at_utc":
            now.isoformat()
    }

    result[
        "strategies"
    ][strategy] = {
        "buy_allowed":
            policy[
                "buy_allowed"
            ],

        "sell_allowed":
            policy[
                "sell_allowed"
            ],

        "reasons":
            policy["reasons"],

        "cash_try":
            str(cash),

        "invested_cost_try":
            str(invested_cost),

        "liquidation_value_try":
            str(
                liquidation_value
            ),

        "equity_try":
            str(equity),

        "peak_equity_try":
            str(peak),

        "drawdown_percent":
            str(
                policy[
                    "drawdown"
                ] * D(100)
            ),

        "daily_realized_pnl_try":
            str(
                daily_realized
            ),

        "daily_sell_count":
            daily_sell_count,

        "daily_loss_limit_try":
            str(
                policy[
                    "daily_loss_limit"
                ]
            ),

        "positions":
            len(positions),

        "valuation_complete":
            valuation_complete
    }


# ============================================================
# SAVE ONLY RISK OUTPUT FILES
# ============================================================

peak_state[
    "updated_at_utc"
] = now.isoformat()

PEAKS.write_text(
    json.dumps(
        peak_state,
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)

STATUS.write_text(
    json.dumps(
        result,
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)


# ============================================================
# SELF TEST
# ============================================================

print()
print("=" * 108)
print("PORTFOLIOAI RISK ENGINE V3 + SELF TEST")
print("=" * 108)

tests = []


def run_test(
    name,
    expected_buy,
    expected_reason=None,
    **kwargs
):
    r = evaluate_policy(
        **kwargs
    )

    ok = (
        r["buy_allowed"]
        == expected_buy
    )

    if expected_reason:
        ok = (
            ok
            and expected_reason
            in r["reasons"]
        )

    tests.append(
        (name, ok)
    )

    print(
        f"{name:<42}",
        "PASS" if ok else "FAIL",
        "| BUY =",
        "OPEN"
        if r["buy_allowed"]
        else "LOCKED",
        "|",
        ",".join(
            r["reasons"]
        )
        if r["reasons"]
        else "-"
    )


BASE = dict(
    initial=D("10000"),
    cash=D("10000"),
    position_count=0,
    invested_cost=D("0"),
    daily_realized=D("0"),
    equity=D("10000"),
    peak=D("10000"),
    global_reasons=[],
    max_positions=10,
    max_invested_fraction=D("1.00"),
    daily_loss_fraction=D("0.05"),
    dd_fraction=D("0.15")
)


run_test(
    "01 NORMAL",
    True,
    **BASE
)


x = dict(BASE)
x["global_reasons"] = [
    "STALE_DATA"
]

run_test(
    "02 STALE DATA",
    False,
    "STALE_DATA",
    **x
)


x = dict(BASE)
x["position_count"] = 10

run_test(
    "03 MAX 10 POSITIONS",
    False,
    "MAX_POSITIONS",
    **x
)


x = dict(BASE)
x["invested_cost"] = D(
    "10000"
)

run_test(
    "04 MAX INVESTED CAPITAL",
    False,
    "MAX_INVESTED_CAPITAL",
    **x
)


x = dict(BASE)
x["daily_realized"] = D(
    "-500"
)

run_test(
    "05 DAILY LOSS -500 TRY",
    False,
    "DAILY_REALIZED_LOSS_LIMIT",
    **x
)


x = dict(BASE)
x["peak"] = D("10000")
x["equity"] = D("8500")

run_test(
    "06 EXACT 15% DRAWDOWN",
    False,
    "EQUITY_DRAWDOWN_KILL",
    **x
)


x = dict(BASE)
x["peak"] = D("12000")
x["equity"] = D("10199")

run_test(
    "07 DD FROM HIGHER PEAK",
    False,
    "EQUITY_DRAWDOWN_KILL",
    **x
)


x = dict(BASE)
x["global_reasons"] = [
    "LIVE_PRICE_ERROR"
]

run_test(
    "08 LIVE PRICE FAILURE",
    False,
    "LIVE_PRICE_ERROR",
    **x
)


passed = sum(
    1
    for _, ok in tests
    if ok
)

total = len(tests)


# ============================================================
# LIVE STATUS
# ============================================================

print()
print("=" * 108)
print("LIVE RISK STATUS")
print("=" * 108)

print(
    "UTC DATE          :",
    today_utc
)

print(
    "GLOBAL BUY GATE   :",
    "OPEN"
    if result["global"][
        "buy_allowed"
    ]
    else "LOCKED"
)

print(
    "GLOBAL REASONS    :",
    (
        ", ".join(
            result[
                "global"
            ]["reasons"]
        )
        if result[
            "global"
        ]["reasons"]
        else "-"
    )
)

print(
    "DATA AGE HOURS    :",
    result[
        "global"
    ]["data_age_hours"]
)

print()

print(
    f"{'STRATEGY':<12}"
    f"{'BUY':>9}"
    f"{'SELL':>9}"
    f"{'EQUITY':>14}"
    f"{'PEAK':>14}"
    f"{'DD':>10}"
    f"{'DAY PNL':>14}"
    f"{'POS':>7}"
)

print("-" * 108)


for strategy in STRATEGIES:

    r = result[
        "strategies"
    ][strategy]

    print(
        f"{strategy:<12}"
        f"{('OPEN' if r['buy_allowed'] else 'LOCKED'):>9}"
        f"{('OPEN' if r['sell_allowed'] else 'LOCKED'):>9}"
        f"{D(r['equity_try']):>14.2f}"
        f"{D(r['peak_equity_try']):>14.2f}"
        f"{D(r['drawdown_percent']):>9.2f}%"
        f"{D(r['daily_realized_pnl_try']):>14.2f}"
        f"{r['positions']:>7}"
    )

    if r["reasons"]:
        print(
            "   REASON:",
            ", ".join(
                r["reasons"]
            )
        )


print()
print("=" * 108)
print("SELF TEST RESULT")
print("=" * 108)

print(
    f"PASS : {passed}/{total}"
)

if passed == total:
    print(
        "STATUS: ALL RISK TESTS PASSED"
    )
else:
    print(
        "STATUS: RISK TEST FAILURE"
    )

print()
print(
    "LIVE STATE MODIFIED : NO"
)

print(
    "LIVE RUNNER MODIFIED: NO"
)

print(
    "REAL ORDERS         : NO"
)

print(
    "RISK STATUS         :",
    STATUS.name
)

print(
    "RISK PEAKS          :",
    PEAKS.name
)

print()
