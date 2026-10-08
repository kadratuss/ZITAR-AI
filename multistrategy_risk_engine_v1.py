import csv
import json
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 28
D = Decimal

ROOT = Path(__file__).resolve().parent

STATE = ROOT / "multistrategy_live_state_v1.json"
RUNS = ROOT / "multistrategy_live_runs_v1.csv"

RISK_CONFIG = ROOT / "multistrategy_risk_config_v1.json"
RISK_STATUS = ROOT / "multistrategy_risk_status_v1.json"

STRATEGIES = [
    "SMA20_50",
    "EMA12_26",
    "RSI14"
]

DEFAULT_CONFIG = {
    "version": 1,

    "paper_only": True,

    "max_positions_per_strategy": 10,

    "max_invested_fraction": "1.00",

    "daily_realized_loss_limit_fraction": "0.05",

    "equity_drawdown_kill_fraction": "0.15",

    "max_data_age_hours": 2,

    "require_last_run_ok": True,

    "require_21_symbols": True,

    "require_63_signal_rows": True,

    "sell_allowed_when_buy_locked": True,

    "notes": [
        "Initial PAPER risk policy.",
        "Limits are experimental, not validated for real-money trading.",
        "BUY may be locked by risk checks.",
        "SELL remains allowed because it reduces spot exposure."
    ]
}


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


if not STATE.exists():
    raise SystemExit(
        "State bulunamadi."
    )

state = json.loads(
    STATE.read_text(encoding="utf-8")
)

# Config ilk kez olusturulur.
# Varsa ASLA otomatik overwrite edilmez.
if not RISK_CONFIG.exists():

    RISK_CONFIG.write_text(
        json.dumps(
            DEFAULT_CONFIG,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

config = json.loads(
    RISK_CONFIG.read_text(
        encoding="utf-8"
    )
)

runs = read_csv(RUNS)

now = datetime.now(timezone.utc)

global_reasons = []

# -------------------------------------------------------
# GLOBAL DATA HEALTH
# -------------------------------------------------------

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

        candle_close = parse_iso(
            last_run["candle_close_utc"]
        )

        data_age_hours = D(
            str(
                (
                    now - candle_close
                ).total_seconds() / 3600
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


# -------------------------------------------------------
# STRATEGY RISK
# -------------------------------------------------------

result = {
    "generated_at_utc":
        now.isoformat(),

    "paper_only":
        config["paper_only"],

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

        "last_candle_close_utc":
            (
                last_run.get(
                    "candle_close_utc"
                )
                if last_run
                else None
            )
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
        account[
            "realized_pnl_try"
        ]
    )

    positions = account[
        "positions"
    ]

    reasons = list(
        global_reasons
    )

    # -----------------------------------------
    # Position limit
    # -----------------------------------------

    if len(positions) >= int(
        config[
            "max_positions_per_strategy"
        ]
    ):

        reasons.append(
            "MAX_POSITIONS"
        )

    # -----------------------------------------
    # Exposure approximation based on cost.
    # No live price needed for BUY gate.
    # -----------------------------------------

    invested_cost = D(0)

    for p in positions.values():

        invested_cost += D(
            p["total_cost_try"]
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

    # -----------------------------------------
    # Daily realized loss gate.
    #
    # v1 state currently has cumulative realized PnL.
    # Until day-specific ledger calculation is added,
    # use cumulative realized loss conservatively.
    # -----------------------------------------

    realized_loss_limit = (
        initial
        * D(
            config[
                "daily_realized_loss_limit_fraction"
            ]
        )
    )

    if realized <= -realized_loss_limit:

        reasons.append(
            "REALIZED_LOSS_LIMIT"
        )

    # -----------------------------------------
    # Equity DD:
    #
    # We cannot correctly evaluate live equity DD
    # from state alone without current market prices
    # and peak-equity history.
    #
    # Therefore DO NOT fake this check.
    # It stays PENDING in Risk Engine v1.
    # -----------------------------------------

    buy_allowed = (
        len(reasons) == 0
    )

    sell_allowed = True

    result[
        "strategies"
    ][strategy] = {

        "buy_allowed":
            buy_allowed,

        "sell_allowed":
            sell_allowed,

        "reasons":
            reasons,

        "cash_try":
            str(cash),

        "positions":
            len(positions),

        "invested_cost_try":
            str(invested_cost),

        "max_invested_try":
            str(max_invested),

        "realized_pnl_try":
            str(realized),

        "realized_loss_limit_try":
            str(
                realized_loss_limit
            ),

        "equity_drawdown_check":
            "PENDING_V2"
    }


# -------------------------------------------------------
# WRITE STATUS ONLY
#
# This does NOT modify trading state.
# -------------------------------------------------------

RISK_STATUS.write_text(
    json.dumps(
        result,
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)


# -------------------------------------------------------
# DISPLAY
# -------------------------------------------------------

print()
print("=" * 92)
print("PORTFOLIOAI RISK ENGINE V1")
print("=" * 92)

print(
    "UTC              :",
    now.isoformat()
)

print(
    "Mode             :",
    "PAPER ONLY"
)

print(
    "Last candle      :",
    result["global"][
        "last_candle_close_utc"
    ]
)

print(
    "Data age hours   :",
    result["global"][
        "data_age_hours"
    ]
)

print(
    "Global BUY gate  :",
    "OPEN"
    if result["global"][
        "buy_allowed"
    ]
    else "LOCKED"
)

print(
    "Global reasons   :",
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

print()
print("-" * 92)

print(
    f"{'STRATEGY':<12}"
    f"{'BUY':>10}"
    f"{'SELL':>10}"
    f"{'CASH':>14}"
    f"{'INVESTED':>14}"
    f"{'POSITIONS':>12}"
    f"{'REALIZED':>14}"
)

print("-" * 92)

for strategy in STRATEGIES:

    r = result[
        "strategies"
    ][strategy]

    print(
        f"{strategy:<12}"
        f"{('OPEN' if r['buy_allowed'] else 'LOCKED'):>10}"
        f"{('OPEN' if r['sell_allowed'] else 'LOCKED'):>10}"
        f"{D(r['cash_try']):>14.2f}"
        f"{D(r['invested_cost_try']):>14.2f}"
        f"{r['positions']:>12}"
        f"{D(r['realized_pnl_try']):>14.2f}"
    )

    if r["reasons"]:

        print(
            " " * 4,
            "REASON:",
            ", ".join(
                r["reasons"]
            )
        )

print()
print("=" * 92)
print("RISK FEATURES")
print("=" * 92)

print(
    "Data freshness       : ACTIVE"
)

print(
    "21 symbol integrity  : ACTIVE"
)

print(
    "63 signal integrity  : ACTIVE"
)

print(
    "Position limit       : ACTIVE"
)

print(
    "Exposure limit       : ACTIVE"
)

print(
    "Realized loss gate   : ACTIVE"
)

print(
    "Equity DD kill       : PENDING V2"
)

print(
    "SELL risk reduction  : ALWAYS ALLOWED"
)

print()
print(
    "RISK STATUS FILE     :",
    RISK_STATUS.name
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
