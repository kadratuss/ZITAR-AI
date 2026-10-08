import csv
import json
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

ROOT = Path.cwd()

STATE_V3   = ROOT / "multistrategy_live_state_v3.json"
TRADES_V1  = ROOT / "multistrategy_live_trades_v1.csv"
TRADES_V3  = ROOT / "multistrategy_live_trades_v3.csv"
SIGNALS_V1 = ROOT / "multistrategy_live_signals_v1.csv"
SIGNALS_V3 = ROOT / "multistrategy_live_signals_v3.csv"
RUNS_V1    = ROOT / "multistrategy_live_runs_v1.csv"
RUNS_V3    = ROOT / "multistrategy_live_runs_v3.csv"

OUTPUT_JSON = ROOT / "strategy_evaluation_v1.json"
OUTPUT_CSV  = ROOT / "strategy_evaluation_v1.csv"

STRATEGIES = (
    "SMA20_50",
    "EMA12_26",
    "RSI14",
)

D = Decimal
ZERO = D("0")
INITIAL = D("10000")


def dec(value, default="0"):
    try:
        if value is None or value == "":
            return D(default)
        return D(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return D(default)


def read_csv(path):
    if not path.exists():
        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        return list(csv.DictReader(f))


def atomic_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")

    with tmp.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )
        f.flush()

    tmp.replace(path)


def atomic_csv(path, rows, fields):
    tmp = path.with_suffix(path.suffix + ".tmp")

    with tmp.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        w = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        w.writeheader()
        w.writerows(rows)
        f.flush()

    tmp.replace(path)


def unique_rows(rows, keys):
    seen = set()
    result = []

    for row in rows:
        key = tuple(
            str(row.get(k, ""))
            for k in keys
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(row)

    return result


def get_trade_time(row):
    return (
        row.get("executed_at_utc")
        or row.get("execution_time_utc")
        or row.get("timestamp_utc")
        or ""
    )


def trade_identity(row):
    explicit = row.get("trade_id")

    if explicit:
        return ("ID", explicit)

    return (
        "LEGACY",
        get_trade_time(row),
        row.get("signal_candle_close_utc", ""),
        row.get("strategy", ""),
        row.get("symbol", ""),
        row.get("side", ""),
        row.get("quantity", ""),
        row.get("modeled_fill_price", ""),
    )


def merge_trades(*groups):
    seen = set()
    out = []

    for group in groups:
        for row in group:

            ident = trade_identity(row)

            if ident in seen:
                continue

            seen.add(ident)
            out.append(row)

    return out


def signal_identity(row):
    explicit = row.get("signal_id")

    if explicit:
        return ("ID", explicit)

    return (
        "LEGACY",
        row.get("signal_candle_close_utc", ""),
        row.get("strategy", ""),
        row.get("symbol", ""),
        row.get("signal", ""),
    )


def merge_signals(*groups):
    seen = set()
    out = []

    for group in groups:
        for row in group:

            ident = signal_identity(row)

            if ident in seen:
                continue

            seen.add(ident)
            out.append(row)

    return out


if not STATE_V3.exists():
    raise RuntimeError(
        "multistrategy_live_state_v3.json bulunamadi"
    )


state = json.loads(
    STATE_V3.read_text(
        encoding="utf-8-sig"
    )
)

accounts = state.get("strategies", {})

for name in STRATEGIES:
    if name not in accounts:
        raise RuntimeError(
            f"State strategy missing: {name}"
        )


v1_trades = read_csv(TRADES_V1)
v3_trades = read_csv(TRADES_V3)

v1_signals = read_csv(SIGNALS_V1)
v3_signals = read_csv(SIGNALS_V3)

v1_runs = read_csv(RUNS_V1)
v3_runs = read_csv(RUNS_V3)

trades = merge_trades(
    v1_trades,
    v3_trades,
)

signals = merge_signals(
    v1_signals,
    v3_signals,
)


print("")
print("=== SOURCE COUNTS ===")
print("V1 trades  :", len(v1_trades))
print("V3 trades  :", len(v3_trades))
print("ALL trades :", len(trades))
print("V1 signals :", len(v1_signals))
print("V3 signals :", len(v3_signals))
print("ALL signals:", len(signals))
print("V1 runs    :", len(v1_runs))
print("V3 runs    :", len(v3_runs))


results = []


for strategy in STRATEGIES:

    account = accounts[strategy]

    cash = dec(
        account.get("cash_try")
    )

    state_realized = dec(
        account.get("realized_pnl_try")
    )

    positions = account.get(
        "positions",
        {}
    )

    strategy_trades = [
        x for x in trades
        if x.get("strategy") == strategy
    ]

    strategy_signals = [
        x for x in signals
        if x.get("strategy") == strategy
    ]

    buys = [
        x for x in strategy_trades
        if x.get("side") == "BUY"
    ]

    sells = [
        x for x in strategy_trades
        if x.get("side") == "SELL"
    ]

    buy_signals = [
        x for x in strategy_signals
        if x.get("signal") == "BUY"
    ]

    sell_signals = [
        x for x in strategy_signals
        if x.get("signal") == "SELL"
    ]

    none_signals = [
        x for x in strategy_signals
        if x.get("signal") == "NONE"
    ]

    wins = 0
    losses = 0
    flat = 0

    closed_realized_from_ledger = ZERO

    for trade in sells:

        pnl = dec(
            trade.get("realized_pnl_try")
        )

        closed_realized_from_ledger += pnl

        if pnl > 0:
            wins += 1

        elif pnl < 0:
            losses += 1

        else:
            flat += 1


    closed_count = len(sells)

    if closed_count:
        win_rate = (
            D(wins)
            / D(closed_count)
            * D("100")
        )
    else:
        win_rate = ZERO


    fees = ZERO

    for trade in strategy_trades:
        fees += dec(
            trade.get("fee_try")
        )


    invested_cost = ZERO

    for symbol, pos in positions.items():

        invested_cost += dec(
            pos.get(
                "total_cost_try",
                pos.get(
                    "cost_try",
                    "0",
                ),
            )
        )


    # --------------------------------------------------------
    # Current state does not store a guaranteed fresh bid/ask.
    # Therefore unrealized PnL is NOT invented here.
    #
    # Until V3 has committed a valuation snapshot,
    # mark-to-market fields remain unavailable.
    # --------------------------------------------------------

    unrealized = None
    equity = None
    total_pnl = None
    total_return_pct = None

    capital_utilization_pct = (
        invested_cost
        / INITIAL
        * D("100")
    )


    first_trade = ""
    last_trade = ""

    if strategy_trades:

        times = sorted(
            x
            for x in (
                get_trade_time(r)
                for r in strategy_trades
            )
            if x
        )

        if times:
            first_trade = times[0]
            last_trade = times[-1]


    result = {
        "strategy": strategy,

        "cash_try": str(cash),

        "open_positions":
            len(positions),

        "invested_cost_try":
            str(invested_cost),

        "capital_utilization_pct":
            str(
                capital_utilization_pct.quantize(
                    D("0.01")
                )
            ),

        "state_realized_pnl_try":
            str(state_realized),

        "ledger_closed_realized_pnl_try":
            str(closed_realized_from_ledger),

        "unrealized_pnl_try":
            None,

        "equity_try":
            None,

        "total_pnl_try":
            None,

        "total_return_pct":
            None,

        "trade_rows":
            len(strategy_trades),

        "buy_trades":
            len(buys),

        "sell_trades":
            len(sells),

        "closed_trades":
            closed_count,

        "wins":
            wins,

        "losses":
            losses,

        "flat":
            flat,

        "win_rate_pct":
            str(
                win_rate.quantize(
                    D("0.01")
                )
            ),

        "fees_paid_try":
            str(fees),

        "signal_rows":
            len(strategy_signals),

        "buy_signals":
            len(buy_signals),

        "sell_signals":
            len(sell_signals),

        "none_signals":
            len(none_signals),

        "first_trade_utc":
            first_trade,

        "last_trade_utc":
            last_trade,

        "valuation_status":
            "WAITING_FOR_V3_MARKET_VALUATION",
    }

    results.append(result)


report = {
    "generated_at_utc":
        datetime.now(timezone.utc).isoformat(),

    "version":
        "strategy_evaluation_v1",

    "mode":
        "PROSPECTIVE_PAPER_ANALYSIS",

    "real_money":
        False,

    "sources": {
        "state":
            STATE_V3.name,

        "v1_trades":
            len(v1_trades),

        "v3_trades":
            len(v3_trades),

        "merged_trades":
            len(trades),

        "v1_signals":
            len(v1_signals),

        "v3_signals":
            len(v3_signals),

        "merged_signals":
            len(signals),

        "v1_runs":
            len(v1_runs),

        "v3_runs":
            len(v3_runs),
    },

    "valuation_note":
        (
            "No current market bid/ask is stored in the "
            "migrated state. V1 does not invent unrealized "
            "PnL or equity. These fields will be populated "
            "after a V3 valuation snapshot is available."
        ),

    "strategies":
        results,
}


atomic_json(
    OUTPUT_JSON,
    report,
)


fields = list(
    results[0].keys()
)

atomic_csv(
    OUTPUT_CSV,
    results,
    fields,
)


print("")
print("=" * 72)
print("STRATEGY EVALUATION")
print("=" * 72)

for r in results:

    print("")
    print(r["strategy"])

    print(
        "  CASH             :",
        r["cash_try"],
        "TRY",
    )

    print(
        "  OPEN POSITIONS   :",
        r["open_positions"],
    )

    print(
        "  INVESTED COST    :",
        r["invested_cost_try"],
        "TRY",
    )

    print(
        "  CAPITAL USED     :",
        r["capital_utilization_pct"],
        "%",
    )

    print(
        "  REALIZED PNL     :",
        r["state_realized_pnl_try"],
        "TRY",
    )

    print(
        "  TRADE ROWS       :",
        r["trade_rows"],
    )

    print(
        "  CLOSED TRADES    :",
        r["closed_trades"],
    )

    print(
        "  W / L / FLAT     :",
        r["wins"],
        "/",
        r["losses"],
        "/",
        r["flat"],
    )

    print(
        "  WIN RATE         :",
        r["win_rate_pct"],
        "%",
    )

    print(
        "  FEES             :",
        r["fees_paid_try"],
        "TRY",
    )

    print(
        "  SIGNALS B/S/N    :",
        r["buy_signals"],
        "/",
        r["sell_signals"],
        "/",
        r["none_signals"],
    )

    print(
        "  VALUATION        :",
        r["valuation_status"],
    )


print("")
print("=" * 72)
print("FILES")
print("=" * 72)
print(OUTPUT_JSON.name)
print(OUTPUT_CSV.name)

print("")
print("REAL ORDERS : NO")
print("STATE WRITE : NO")
print("V1/V3 LIVE FILES MODIFIED : NO")
print("")
print("STRATEGY EVALUATION V1 : PASS")
