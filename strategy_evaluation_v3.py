import csv
import json
import os
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

ROOT = Path.cwd()

STATE = ROOT / "multistrategy_live_state_v3.json"
EVAL2 = ROOT / "strategy_evaluation_v2.json"

SIG1 = ROOT / "multistrategy_live_signals_v1.csv"
SIG3 = ROOT / "multistrategy_live_signals_v3.csv"

TRD1 = ROOT / "multistrategy_live_trades_v1.csv"
TRD3 = ROOT / "multistrategy_live_trades_v3.csv"

RUN1 = ROOT / "multistrategy_live_runs_v1.csv"
RUN3 = ROOT / "multistrategy_live_runs_v3.csv"

OUT_JSON = ROOT / "strategy_evaluation_v3.json"
OUT_CSV = ROOT / "strategy_evaluation_v3.csv"

D = Decimal

STRATEGIES = (
    "SMA20_50",
    "EMA12_26",
    "RSI14",
)

# Historical benchmark.
# Frozen research result; NOT prospective evidence.
HISTORICAL = {
    "SMA20_50": {
        "net_pnl_try": "7773.97",
        "return_pct": "77.74",
        "max_drawdown_pct": "12.23",
        "buy_trades": 93,
        "sell_trades": 86,
        "open_positions_end": 7,
    },
    "EMA12_26": {
        "net_pnl_try": "9133.18",
        "return_pct": "91.33",
        "max_drawdown_pct": "11.08",
        "buy_trades": 140,
        "sell_trades": 132,
        "open_positions_end": 8,
    },
    "RSI14": {
        "net_pnl_try": "407.59",
        "return_pct": "4.08",
        "max_drawdown_pct": "9.49",
        "buy_trades": 106,
        "sell_trades": 98,
        "open_positions_end": 8,
    },
}


def read_csv(path):
    if not path.exists():
        return []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        return list(csv.DictReader(f))


def load_json(path):
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def dec(x):
    return D(str(x))


def signal_time(row):
    for key in (
        "signal_candle_close_utc",
        "candle_close_utc",
        "target_candle_close_utc",
    ):
        value = str(
            row.get(key, "")
        ).strip()

        if value:
            return value

    return ""


def signal_key(row):
    sid = str(
        row.get("signal_id", "")
    ).strip()

    if sid:
        return ("ID", sid)

    return (
        "LEGACY",
        signal_time(row),
        str(row.get("strategy", "")),
        str(row.get("symbol", "")),
        str(row.get("signal", "")),
    )


def trade_key(row):
    tid = str(
        row.get("trade_id", "")
    ).strip()

    if tid:
        return ("ID", tid)

    return (
        "LEGACY",
        str(row.get("executed_at_utc", "")),
        str(row.get("signal_candle_close_utc", "")),
        str(row.get("strategy", "")),
        str(row.get("symbol", "")),
        str(row.get("side", "")),
        str(row.get("quantity", "")),
        str(row.get("modeled_fill_price", "")),
    )


def merge(groups, key_fn):
    out = []
    seen = set()

    for rows in groups:
        for row in rows:
            key = key_fn(row)

            if key in seen:
                continue

            seen.add(key)
            out.append(row)

    return out


def atomic_json(path, obj):
    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            obj,
            f,
            indent=2,
            ensure_ascii=False
        )
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, path)


def atomic_csv(path, rows):
    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    fields = list(
        rows[0].keys()
    )

    with tmp.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields
        )

        writer.writeheader()
        writer.writerows(rows)

        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp, path)


if not STATE.exists():
    raise RuntimeError("V3 state missing")

if not EVAL2.exists():
    raise RuntimeError(
        "Evaluation V2 missing"
    )


state = load_json(STATE)
eval2 = load_json(EVAL2)

signals = merge(
    [
        read_csv(SIG1),
        read_csv(SIG3),
    ],
    signal_key
)

trades = merge(
    [
        read_csv(TRD1),
        read_csv(TRD3),
    ],
    trade_key
)

runs_v1 = read_csv(RUN1)
runs_v3 = read_csv(RUN3)

eval2_map = {
    row["strategy"]: row
    for row in eval2["strategies"]
}


print("")
print("============================================================")
print("STRATEGY EVALUATION V3")
print("HISTORICAL vs PROSPECTIVE")
print("============================================================")

print("")
print("Prospective signals :", len(signals))
print("Prospective trades  :", len(trades))
print("V1 runs             :", len(runs_v1))
print("V3 runs             :", len(runs_v3))


rows = []


for strategy in STRATEGIES:

    hist = HISTORICAL[strategy]
    live = eval2_map[strategy]

    srows = [
        x for x in signals
        if x.get("strategy") == strategy
    ]

    trows = [
        x for x in trades
        if x.get("strategy") == strategy
    ]

    buys = sum(
        1 for x in trows
        if x.get("side") == "BUY"
    )

    sells = sum(
        1 for x in trows
        if x.get("side") == "SELL"
    )

    buy_signals = sum(
        1 for x in srows
        if x.get("signal") == "BUY"
    )

    sell_signals = sum(
        1 for x in srows
        if x.get("signal") == "SELL"
    )

    none_signals = sum(
        1 for x in srows
        if x.get("signal") == "NONE"
    )

    prospective_return = dec(
        live["return_pct"]
    )

    historical_return = dec(
        hist["return_pct"]
    )

    return_gap = (
        prospective_return
        - historical_return
    )

    # This is descriptive only.
    # Do NOT use as a strategy score.
    row = {
        "strategy":
            strategy,

        "historical_test_type":
            "BACKTEST_SHARED_PORTFOLIO",

        "historical_period":
            "2026-08-26T20:00Z_to_2026-09-22T19:00Z",

        "historical_return_pct":
            hist["return_pct"],

        "historical_net_pnl_try":
            hist["net_pnl_try"],

        "historical_max_drawdown_pct":
            hist["max_drawdown_pct"],

        "historical_buy_trades":
            hist["buy_trades"],

        "historical_sell_trades":
            hist["sell_trades"],

        "prospective_test_type":
            "LIVE_MARKET_PAPER",

        "prospective_signal_rows":
            len(srows),

        "prospective_buy_signals":
            buy_signals,

        "prospective_sell_signals":
            sell_signals,

        "prospective_none_signals":
            none_signals,

        "prospective_trade_rows":
            len(trows),

        "prospective_buy_trades":
            buys,

        "prospective_sell_trades":
            sells,

        "prospective_open_positions":
            live["open_positions"],

        "prospective_cash_try":
            live["cash_try"],

        "prospective_equity_try":
            live["equity_try"],

        "prospective_realized_pnl_try":
            live["realized_pnl_try"],

        "prospective_unrealized_pnl_try":
            live["unrealized_pnl_try"],

        "prospective_total_pnl_try":
            live["total_pnl_try"],

        "prospective_return_pct":
            live["return_pct"],

        "prospective_drawdown_pct":
            live["drawdown_pct"],

        "historical_vs_prospective_return_gap_pct_points":
            str(
                return_gap.quantize(
                    D("0.01")
                )
            ),

        "evidence_status":
            (
                "EARLY_PROSPECTIVE_SAMPLE"
            ),

        "selection_status":
            "NO_STRATEGY_SELECTION",
    }

    rows.append(row)


    print("")
    print(strategy)

    print(
        "  HIST RETURN   :",
        hist["return_pct"],
        "%"
    )

    print(
        "  HIST MAX DD   :",
        hist["max_drawdown_pct"],
        "%"
    )

    print(
        "  LIVE SIGNALS  :",
        len(srows)
    )

    print(
        "  LIVE TRADES   :",
        len(trows)
    )

    print(
        "  LIVE EQUITY   :",
        live["equity_try"],
        "TRY"
    )

    print(
        "  LIVE PNL      :",
        live["total_pnl_try"],
        "TRY"
    )

    print(
        "  LIVE RETURN   :",
        live["return_pct"],
        "%"
    )

    print(
        "  LIVE DD       :",
        live["drawdown_pct"],
        "%"
    )

    print(
        "  STATUS        :",
        "EARLY_PROSPECTIVE_SAMPLE"
    )


report = {
    "version":
        "strategy_evaluation_v3",

    "generated_at_utc":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "mode":
        "RESEARCH_AND_PROSPECTIVE_PAPER",

    "real_money":
        False,

    "historical_warning":
        (
            "Historical backtest results are research evidence only. "
            "They include survivor-selection, liquidity, spread, "
            "execution and regime limitations previously identified."
        ),

    "prospective_warning":
        (
            "The prospective sample is currently very small. "
            "No strategy should be selected or capital reallocated "
            "from these early observations."
        ),

    "comparison_policy": {
        "rank_strategies":
            False,

        "auto_select_strategy":
            False,

        "auto_change_capital":
            False,

        "historical_and_forward_kept_separate":
            True,
    },

    "source_counts": {
        "signals":
            len(signals),

        "trades":
            len(trades),

        "v1_runs":
            len(runs_v1),

        "v3_runs":
            len(runs_v3),
    },

    "strategies":
        rows,
}


atomic_json(
    OUT_JSON,
    report
)

atomic_csv(
    OUT_CSV,
    rows
)


print("")
print("============================================================")
print("EVALUATION V3 : PASS")
print("HISTORICAL    : SEPARATE")
print("PROSPECTIVE   : SEPARATE")
print("AUTO SELECT   : NO")
print("LIVE WRITE    : NO")
print("REAL ORDERS   : NO")
print("============================================================")
