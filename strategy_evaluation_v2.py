import csv
import json
import time
import os
import requests

from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

ROOT = Path.cwd()

STATE = ROOT / "multistrategy_live_state_v3.json"

OUT_JSON = ROOT / "strategy_evaluation_v2.json"
OUT_CSV  = ROOT / "strategy_evaluation_v2.csv"

BOOK_API = (
    "https://api.binance.me/"
    "api/v3/ticker/bookTicker"
)

D = Decimal

ZERO = D("0")
ONE = D("1")

INITIAL = D("10000")
SLIP = D("0.001")
FEE = D("0.001")

STRATEGIES = (
    "SMA20_50",
    "EMA12_26",
    "RSI14",
)


def dec(x):
    return D(str(x))


def money(x):
    return x.quantize(
        D("0.01")
    )


def pct(x):
    return x.quantize(
        D("0.01")
    )


def get_json(url):
    delays = (1, 2, 4, 8)
    last = None

    for attempt in range(5):

        try:
            r = requests.get(
                url,
                timeout=20,
                headers={
                    "User-Agent":
                        "PortfolioAI-Evaluation-V2/1.0"
                },
            )

            r.raise_for_status()

            return r.json()

        except Exception as exc:
            last = exc

            print(
                "API RETRY",
                attempt + 1,
                ":",
                type(exc).__name__,
                str(exc),
            )

            if attempt < 4:
                time.sleep(
                    delays[attempt]
                )

    raise RuntimeError(
        f"bookTicker failed: {last}"
    )


def atomic_json(path, data):

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )

        f.flush()
        os.fsync(f.fileno())

    os.replace(
        tmp,
        path,
    )


def atomic_csv(path, rows):

    if not rows:
        raise RuntimeError(
            "No evaluation rows"
        )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    fields = list(
        rows[0].keys()
    )

    with tmp.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(rows)

        f.flush()
        os.fsync(f.fileno())

    os.replace(
        tmp,
        path,
    )


# ------------------------------------------------------------
# Load state
# ------------------------------------------------------------

if not STATE.exists():
    raise RuntimeError(
        "V3 state missing"
    )

state = json.loads(
    STATE.read_text(
        encoding="utf-8-sig"
    )
)

accounts = state["strategies"]
universe = state["universe"]

print("")
print("STATE      : PASS")
print(
    "UNIVERSE   :",
    len(universe),
)

if len(universe) != 21:
    raise RuntimeError(
        "Expected 21 symbols"
    )


# ------------------------------------------------------------
# ONE common book snapshot
# ------------------------------------------------------------

snapshot_at = (
    datetime.now(timezone.utc)
    .isoformat()
)

raw = get_json(
    BOOK_API
)

wanted = set(universe)

books = {}

for row in raw:

    symbol = row.get(
        "symbol"
    )

    if symbol not in wanted:
        continue

    bid = dec(
        row["bidPrice"]
    )

    ask = dec(
        row["askPrice"]
    )

    if bid <= ZERO:
        raise RuntimeError(
            f"{symbol}: bid <= 0"
        )

    if ask <= ZERO:
        raise RuntimeError(
            f"{symbol}: ask <= 0"
        )

    if ask < bid:
        raise RuntimeError(
            f"{symbol}: crossed book"
        )

    books[symbol] = {
        "bid": bid,
        "ask": ask,
    }


missing = (
    wanted
    - set(books)
)

if missing:
    raise RuntimeError(
        "Missing books: "
        + ",".join(
            sorted(missing)
        )
    )


print(
    "BOOK       :",
    len(books),
    "/ 21 PASS",
)

print(
    "SNAPSHOT   :",
    snapshot_at,
)


# ------------------------------------------------------------
# Evaluate accounts
# ------------------------------------------------------------

rows = []

print("")
print("=" * 72)
print("LIVE PAPER VALUATION")
print("=" * 72)


for strategy in STRATEGIES:

    account = accounts[
        strategy
    ]

    cash = dec(
        account["cash_try"]
    )

    realized = dec(
        account[
            "realized_pnl_try"
        ]
    )

    positions = account.get(
        "positions",
        {}
    )

    invested_cost = ZERO

    liquidation_value = ZERO

    unrealized = ZERO

    position_details = []


    for symbol, pos in positions.items():

        qty = dec(
            pos["quantity"]
        )

        cost = dec(
            pos.get(
                "total_cost_try",
                pos.get(
                    "cost_try",
                    "0",
                ),
            )
        )

        if symbol not in books:
            raise RuntimeError(
                f"No book for open position {symbol}"
            )

        bid = books[
            symbol
        ]["bid"]

        ask = books[
            symbol
        ]["ask"]

        # Conservative modeled liquidation:
        # SELL at best bid,
        # then same 0.1% modeled slip,
        # then 0.1% fee.

        modeled_exit = (
            bid
            * (ONE - SLIP)
        )

        gross = (
            qty
            * modeled_exit
        )

        exit_fee = (
            gross
            * FEE
        )

        net_liquidation = (
            gross
            - exit_fee
        )

        pos_unrealized = (
            net_liquidation
            - cost
        )

        invested_cost += cost

        liquidation_value += (
            net_liquidation
        )

        unrealized += (
            pos_unrealized
        )


        spread = (
            ask - bid
        )

        mid = (
            ask + bid
        ) / D("2")

        if mid > ZERO:
            spread_pct = (
                spread
                / mid
                * D("100")
            )
        else:
            spread_pct = ZERO


        position_details.append({
            "symbol":
                symbol,

            "quantity":
                str(qty),

            "cost_try":
                str(cost),

            "best_bid":
                str(bid),

            "best_ask":
                str(ask),

            "spread_pct":
                str(
                    spread_pct.quantize(
                        D("0.0001")
                    )
                ),

            "modeled_exit_price":
                str(modeled_exit),

            "estimated_exit_fee_try":
                str(exit_fee),

            "net_liquidation_try":
                str(net_liquidation),

            "unrealized_pnl_try":
                str(pos_unrealized),
        })


    equity = (
        cash
        + liquidation_value
    )

    total_pnl = (
        equity
        - INITIAL
    )

    return_pct = (
        total_pnl
        / INITIAL
        * D("100")
    )


    # V3 peak starts at transition baseline.
    # If peaks file exists, use it.
    # Otherwise do NOT invent historical peaks.

    peak_file = (
        ROOT
        / "multistrategy_live_peaks_v3.json"
    )

    peak_equity = INITIAL
    peak_source = (
        "INITIAL_CAPITAL_FALLBACK"
    )


    if peak_file.exists():

        try:

            peak_data = json.loads(
                peak_file.read_text(
                    encoding="utf-8-sig"
                )
            )

            candidate = None

            if strategy in peak_data:

                if isinstance(
                    peak_data[strategy],
                    dict
                ):

                    candidate = (
                        peak_data[strategy]
                        .get(
                            "peak_equity_try"
                        )
                    )

                else:
                    candidate = (
                        peak_data[strategy]
                    )

            if candidate is not None:

                candidate = dec(
                    candidate
                )

                if candidate > ZERO:
                    peak_equity = (
                        candidate
                    )

                    peak_source = (
                        "V3_PEAK_FILE"
                    )

        except Exception as exc:

            print(
                "PEAK WARNING:",
                strategy,
                str(exc),
            )


    # Current equity can establish a new
    # observational peak for evaluation,
    # but evaluation DOES NOT write it
    # back to live risk state.

    observed_peak = max(
        peak_equity,
        equity,
    )


    if observed_peak > ZERO:

        drawdown_pct = (
            (
                observed_peak
                - equity
            )
            / observed_peak
            * D("100")
        )

    else:
        drawdown_pct = ZERO


    invested_pct = (
        invested_cost
        / INITIAL
        * D("100")
    )


    row = {
        "strategy":
            strategy,

        "snapshot_at_utc":
            snapshot_at,

        "cash_try":
            str(money(cash)),

        "open_positions":
            len(positions),

        "invested_cost_try":
            str(
                money(
                    invested_cost
                )
            ),

        "capital_utilization_pct":
            str(
                pct(
                    invested_pct
                )
            ),

        "liquidation_value_try":
            str(
                money(
                    liquidation_value
                )
            ),

        "realized_pnl_try":
            str(
                money(
                    realized
                )
            ),

        "unrealized_pnl_try":
            str(
                money(
                    unrealized
                )
            ),

        "equity_try":
            str(
                money(
                    equity
                )
            ),

        "total_pnl_try":
            str(
                money(
                    total_pnl
                )
            ),

        "return_pct":
            str(
                pct(
                    return_pct
                )
            ),

        "risk_peak_equity_try":
            str(
                money(
                    peak_equity
                )
            ),

        "observed_peak_equity_try":
            str(
                money(
                    observed_peak
                )
            ),

        "drawdown_pct":
            str(
                pct(
                    drawdown_pct
                )
            ),

        "peak_source":
            peak_source,

        "valuation":
            "BEST_BID_MINUS_SLIP_MINUS_FEE",

        "position_details":
            position_details,
    }

    rows.append(
        row
    )


    print("")
    print(strategy)

    print(
        "  CASH        :",
        money(cash),
        "TRY",
    )

    print(
        "  POSITIONS   :",
        len(positions),
    )

    print(
        "  INVESTED    :",
        money(invested_cost),
        "TRY",
    )

    print(
        "  LIQUIDATION :",
        money(liquidation_value),
        "TRY",
    )

    print(
        "  REALIZED    :",
        money(realized),
        "TRY",
    )

    print(
        "  UNREALIZED  :",
        money(unrealized),
        "TRY",
    )

    print(
        "  EQUITY      :",
        money(equity),
        "TRY",
    )

    print(
        "  TOTAL PNL   :",
        money(total_pnl),
        "TRY",
    )

    print(
        "  RETURN      :",
        pct(return_pct),
        "%",
    )

    print(
        "  DRAWDOWN    :",
        pct(drawdown_pct),
        "%",
    )


    for p in position_details:

        print(
            "   ->",
            p["symbol"],
            "| BID",
            p["best_bid"],
            "| ASK",
            p["best_ask"],
            "| SPREAD",
            p["spread_pct"],
            "%",
            "| UPNL",
            money(
                dec(
                    p[
                        "unrealized_pnl_try"
                    ]
                )
            ),
            "TRY",
        )


# ------------------------------------------------------------
# Output
# ------------------------------------------------------------

report = {
    "version":
        "strategy_evaluation_v2",

    "generated_at_utc":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "mode":
        "PROSPECTIVE_PAPER_ANALYSIS",

    "real_money":
        False,

    "market_snapshot_at_utc":
        snapshot_at,

    "valuation_method": {
        "long_position_reference":
            "BEST_BID",

        "modeled_exit_slippage":
            str(SLIP),

        "modeled_exit_fee":
            str(FEE),

        "formula":
            (
                "qty * bid * "
                "(1-slip) * "
                "(1-fee)"
            ),
    },

    "important_note":
        (
            "Drawdown is measured only against "
            "the available V3 peak baseline/current "
            "observation. It is not reconstructed "
            "from unobserved V1 intrahour equity."
        ),

    "strategies":
        rows,
}


atomic_json(
    OUT_JSON,
    report,
)


flat_rows = []

for row in rows:

    flat = dict(row)

    flat["position_details"] = (
        json.dumps(
            flat[
                "position_details"
            ],
            ensure_ascii=False,
        )
    )

    flat_rows.append(
        flat
    )


atomic_csv(
    OUT_CSV,
    flat_rows,
)


print("")
print("=" * 72)
print("STRATEGY EVALUATION V2 : PASS")
print("COMMON BOOK SNAPSHOT   : PASS")
print("LIVE STATE WRITE       : NO")
print("LIVE TRADE WRITE       : NO")
print("REAL ORDER             : NO")
print("=" * 72)

