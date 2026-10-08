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

STATE = ROOT / "multistrategy_live_state_v1.json"
RUNS = ROOT / "multistrategy_live_runs_v1.csv"

CONFIG = ROOT / "multistrategy_risk_config_v1.json"

PEAKS = ROOT / "multistrategy_risk_peaks_v2.json"
STATUS = ROOT / "multistrategy_risk_status_v2.json"

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


def parse_iso(x):

    return datetime.fromisoformat(
        x.replace("Z", "+00:00")
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

            return D(
                str(r.json()["price"])
            )

        except Exception as e:

            last_error = e

            if attempt < 3:
                time.sleep(1)

    raise RuntimeError(last_error)


if not STATE.exists():
    raise SystemExit("State bulunamadi.")

if not CONFIG.exists():
    raise SystemExit("Risk config bulunamadi.")

state = json.loads(
    STATE.read_text(encoding="utf-8")
)

config = json.loads(
    CONFIG.read_text(encoding="utf-8")
)

runs = read_csv(RUNS)

now = datetime.now(timezone.utc)

fee = D(
    state["rules"]["fee_rate"]
)

slip = D(
    state["rules"]["slippage_rate"]
)


# ==========================================================
# GLOBAL DATA HEALTH
# ==========================================================

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


# ==========================================================
# FETCH PRICES
# ==========================================================

needed = set()

for strategy in STRATEGIES:

    positions = state[
        "strategies"
    ][strategy]["positions"]

    needed.update(
        positions.keys()
    )


prices = {}
price_errors = {}


for symbol in sorted(needed):

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


# ==========================================================
# LOAD / INITIALIZE PEAK EQUITY
# ==========================================================

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


# ==========================================================
# STRATEGY EVALUATION
# ==========================================================

result = {

    "generated_at_utc":
        now.isoformat(),

    "paper_only": True,

    "global": {

        "buy_allowed":
            len(global_reasons) == 0,

        "reasons":
            global_reasons,

        "data_age_hours":
            (
                str(data_age_hours)
                if data_age_hours is not None
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

    realized = D(
        account["realized_pnl_try"]
    )

    positions = account[
        "positions"
    ]

    reasons = list(
        global_reasons
    )

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


    if not valuation_complete:

        reasons.append(
            "INCOMPLETE_EQUITY_VALUATION"
        )


    equity = (
        cash
        + liquidation_value
    )


    # ======================================================
    # PEAK EQUITY
    # ======================================================

    previous_peak = D(
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
        previous_peak,
        equity,
        initial
    )


    if peak > 0:

        drawdown = (
            peak - equity
        ) / peak

    else:

        drawdown = D(0)


    peak_state[
        "strategies"
    ][strategy] = {

        "peak_equity_try":
            str(peak),

        "last_equity_try":
            str(equity),

        "last_drawdown_fraction":
            str(drawdown),

        "updated_at_utc":
            now.isoformat()
    }


    # ======================================================
    # RISK CHECKS
    # ======================================================

    if len(positions) >= int(
        config[
            "max_positions_per_strategy"
        ]
    ):

        reasons.append(
            "MAX_POSITIONS"
        )


    max_invested = (
        initial
        * D(
            config[
                "max_invested_fraction"
            ]
        )
    )


    if invested_cost >= max_invested:

        reasons.append(
            "MAX_INVESTED_CAPITAL"
        )


    realized_loss_limit = (
        initial
        * D(
            config[
                "daily_realized_loss_limit_fraction"
            ]
        )
    )


    # V2 still uses cumulative realized PnL
    # until daily ledger gate is implemented.
    if realized <= -realized_loss_limit:

        reasons.append(
            "REALIZED_LOSS_LIMIT"
        )


    dd_limit = D(
        config[
            "equity_drawdown_kill_fraction"
        ]
    )


    if drawdown >= dd_limit:

        reasons.append(
            "EQUITY_DRAWDOWN_KILL"
        )


    buy_allowed = (
        len(reasons) == 0
    )


    result[
        "strategies"
    ][strategy] = {

        "buy_allowed":
            buy_allowed,

        # Spot risk reduction remains available.
        "sell_allowed":
            True,

        "reasons":
            reasons,

        "cash_try":
            str(cash),

        "invested_cost_try":
            str(invested_cost),

        "liquidation_value_try":
            str(liquidation_value),

        "equity_try":
            str(equity),

        "peak_equity_try":
            str(peak),

        "drawdown_fraction":
            str(drawdown),

        "drawdown_percent":
            str(
                drawdown * D(100)
            ),

        "drawdown_limit_percent":
            str(
                dd_limit * D(100)
            ),

        "positions":
            len(positions),

        "realized_pnl_try":
            str(realized),

        "valuation_complete":
            valuation_complete
    }


# ==========================================================
# SAVE PEAK + STATUS
# ==========================================================

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


# ==========================================================
# DISPLAY
# ==========================================================

print()
print("=" * 104)
print("PORTFOLIOAI RISK ENGINE V2")
print("=" * 104)

print(
    "UTC             :",
    now.isoformat()
)

print(
    "MODE            : PAPER ONLY"
)

print(
    "GLOBAL BUY GATE :",
    "OPEN"
    if result["global"][
        "buy_allowed"
    ]
    else "LOCKED"
)

print(
    "GLOBAL REASONS  :",
    (
        ", ".join(
            result["global"][
                "reasons"
            ]
        )
        if result["global"][
            "reasons"
        ]
        else "-"
    )
)

print(
    "DATA AGE HOURS  :",
    result["global"][
        "data_age_hours"
    ]
)

print()

print(
    f"{'STRATEGY':<12}"
    f"{'BUY':>9}"
    f"{'SELL':>9}"
    f"{'CASH':>13}"
    f"{'EQUITY':>13}"
    f"{'PEAK':>13}"
    f"{'DD':>10}"
    f"{'POS':>7}"
)

print("-" * 104)


for strategy in STRATEGIES:

    r = result[
        "strategies"
    ][strategy]

    print(
        f"{strategy:<12}"
        f"{('OPEN' if r['buy_allowed'] else 'LOCKED'):>9}"
        f"{('OPEN' if r['sell_allowed'] else 'LOCKED'):>9}"
        f"{D(r['cash_try']):>13.2f}"
        f"{D(r['equity_try']):>13.2f}"
        f"{D(r['peak_equity_try']):>13.2f}"
        f"{D(r['drawdown_percent']):>9.2f}%"
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
print("=" * 104)
print("RISK PROTECTION")
print("=" * 104)

print(
    "Data freshness       : ACTIVE"
)

print(
    "21 / 63 integrity    : ACTIVE"
)

print(
    "Position cap         : ACTIVE"
)

print(
    "Exposure cap         : ACTIVE"
)

print(
    "Realized loss gate   : ACTIVE"
)

print(
    "Live equity          : ACTIVE"
)

print(
    "Peak equity tracking : ACTIVE"
)

print(
    "15% DD BUY kill      : ACTIVE"
)

print(
    "SELL reduction path  : OPEN"
)

print()
print(
    "PEAK FILE            :",
    PEAKS.name
)

print(
    "STATUS FILE          :",
    STATUS.name
)

print(
    "TRADING STATE CHANGED: NO"
)

print(
    "RUNNER CHANGED       : NO"
)

print(
    "REAL ORDERS          : NO"
)

print()
