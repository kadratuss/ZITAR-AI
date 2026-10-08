import csv
import copy
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, getcontext, ROUND_DOWN
from pathlib import Path

import requests

getcontext().prec = 28
D = Decimal

ROOT = Path(__file__).resolve().parent

STATE = ROOT / "multistrategy_live_state_v3.json"
SIGNALS = ROOT / "multistrategy_live_signals_v3.csv"
TRADES = ROOT / "multistrategy_live_trades_v3.csv"
RUNS = ROOT / "multistrategy_live_runs_v3.csv"
PEAKS = ROOT / "multistrategy_live_peaks_v3.json"
JOURNAL_DIR = ROOT / "multistrategy_live_journal_v3"

V1_TRADES = ROOT / "multistrategy_live_trades_v1.csv"

KLINE_API = "https://api.binance.me/api/v1/klines"
BOOK_API = "https://api.binance.me/api/v3/ticker/bookTicker"

HOUR = 3_600_000
QTY_STEP = D("0.00000001")

STRATEGIES = (
    "SMA20_50",
    "EMA12_26",
    "RSI14",
)

SIGNAL_FIELDS = [
    "signal_id",
    "observed_at_utc",
    "candle_open_utc",
    "candle_close_utc",
    "symbol",
    "strategy",
    "signal",
    "close_price",
    "indicator_1",
    "indicator_2",
    "protocol",
    "status",
]

TRADE_FIELDS = [
    "trade_id",
    "executed_at_utc",
    "signal_candle_close_utc",
    "strategy",
    "symbol",
    "side",
    "observed_bid",
    "observed_ask",
    "reference_price",
    "modeled_fill_price",
    "quantity",
    "gross_try",
    "fee_try",
    "cash_after_try",
    "realized_pnl_try",
    "protocol",
    "status",
]

RUN_FIELDS = [
    "commit_id",
    "run_utc",
    "candle_close_utc",
    "symbols",
    "signal_rows",
    "paper_trades",
    "blocked_buys",
    "status",
]


def utcnow():
    return datetime.now(timezone.utc)


def iso(ms):
    return datetime.fromtimestamp(
        ms / 1000,
        tz=timezone.utc,
    ).isoformat()


def atomic_json(path, obj):
    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            obj,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    os.replace(tmp, path)


def read_json(path):
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def get_json(url, params=None):
    last = None
    delays = (1, 2, 4, 8)

    for attempt in range(5):
        try:
            r = requests.get(
                url,
                params=params,
                timeout=20,
                headers={
                    "User-Agent": "PortfolioAI-Paper-V3/1.0"
                },
            )
            r.raise_for_status()
            return r.json()

        except Exception as exc:
            last = exc

            if attempt < 4:
                time.sleep(delays[attempt])

    raise RuntimeError(
        f"HTTP/API failed after 5 attempts: {last}"
    )


def ema(values, n):
    a = D(2) / D(n + 1)
    e = values[0]

    for x in values[1:]:
        e = a * x + (D(1) - a) * e

    return e


def rsi(values, n=14):
    gains = D(0)
    losses = D(0)

    for i in range(
        len(values) - n,
        len(values),
    ):
        change = values[i] - values[i - 1]

        if change > 0:
            gains += change

        elif change < 0:
            losses -= change

    avg_gain = gains / D(n)
    avg_loss = losses / D(n)

    if avg_loss == 0:
        return D(100)

    rs = avg_gain / avg_loss

    return (
        D(100)
        - D(100) / (D(1) + rs)
    )


def calc_signals(closes):
    p20 = sum(closes[-21:-1]) / D(20)
    p50 = sum(closes[-51:-1]) / D(50)

    c20 = sum(closes[-20:]) / D(20)
    c50 = sum(closes[-50:]) / D(50)

    sma = "NONE"

    if p20 <= p50 and c20 > c50:
        sma = "BUY"

    elif p20 >= p50 and c20 < c50:
        sma = "SELL"

    prev = closes[:-1]

    pe12 = ema(prev, 12)
    pe26 = ema(prev, 26)

    ce12 = ema(closes, 12)
    ce26 = ema(closes, 26)

    em = "NONE"

    if pe12 <= pe26 and ce12 > ce26:
        em = "BUY"

    elif pe12 >= pe26 and ce12 < ce26:
        em = "SELL"

    prsi = rsi(closes[:-1], 14)
    crsi = rsi(closes, 14)

    rs = "NONE"

    if prsi <= D(30) and crsi > D(30):
        rs = "BUY"

    elif prsi >= D(70) and crsi < D(70):
        rs = "SELL"

    return {
        "SMA20_50": (
            sma,
            c20,
            c50,
        ),
        "EMA12_26": (
            em,
            ce12,
            ce26,
        ),
        "RSI14": (
            rs,
            crsi,
            D(30) if rs == "BUY" else D(70),
        ),
    }


def fetch_history(symbol, target_open, now_ms):
    data = get_json(
        KLINE_API,
        {
            "symbol": symbol,
            "interval": "1h",
            "limit": 120,
        },
    )

    closed = [
        x for x in data
        if int(x[6]) + 1 <= now_ms
    ]

    idx = None

    for i, k in enumerate(closed):
        if int(k[0]) == target_open:
            idx = i
            break

    if idx is None:
        raise RuntimeError(
            "Hedef kapanmis mum bulunamadi"
        )

    history = closed[:idx + 1]

    if len(history) < 60:
        raise RuntimeError(
            f"Yetersiz history: {len(history)}"
        )

    return history


def fetch_book_snapshot(universe):
    data = get_json(BOOK_API)

    if not isinstance(data, list):
        raise RuntimeError(
            "bookTicker list donmedi"
        )

    wanted = set(universe)
    result = {}

    for row in data:
        symbol = row.get("symbol")

        if symbol not in wanted:
            continue

        bid = D(str(row["bidPrice"]))
        ask = D(str(row["askPrice"]))

        if bid <= 0 or ask <= 0:
            raise RuntimeError(
                f"Gecersiz book price: {symbol}"
            )

        if ask < bid:
            raise RuntimeError(
                f"Crossed book: {symbol}"
            )

        result[symbol] = {
            "bid": bid,
            "ask": ask,
        }

    missing = wanted - set(result)

    if missing:
        raise RuntimeError(
            "bookTicker eksik: "
            + ",".join(sorted(missing))
        )

    return result


def existing_ids(path, field):
    if not path.exists():
        return set()

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        return {
            row.get(field, "")
            for row in csv.DictReader(f)
            if row.get(field)
        }


def append_unique(path, fields, rows, id_field):
    if not rows:
        return

    ids = existing_ids(path, id_field)

    new_rows = [
        row for row in rows
        if row[id_field] not in ids
    ]

    if not new_rows:
        return

    new_file = (
        not path.exists()
        or path.stat().st_size == 0
    )

    with path.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as f:
        w = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        if new_file:
            w.writeheader()

        for row in new_rows:
            w.writerow(row)

        f.flush()
        os.fsync(f.fileno())


def daily_realized(path, strategy, day):
    if not path.exists():
        return D(0)

    total = D(0)

    with path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        for row in csv.DictReader(f):

            if row.get("strategy") != strategy:
                continue

            if row.get("side") != "SELL":
                continue

            value = row.get("realized_pnl_try")

            if value in ("", None):
                continue

            try:
                t = datetime.fromisoformat(
                    row["executed_at_utc"].replace(
                        "Z",
                        "+00:00",
                    )
                )

            except Exception:
                continue

            if t.astimezone(
                timezone.utc
            ).date() == day:
                total += D(value)

    return total


def load_peaks():
    if not PEAKS.exists():
        return {
            "strategies": {
                s: {
                    "peak_equity_try": "10000"
                }
                for s in STRATEGIES
            }
        }

    return read_json(PEAKS)


def liquidation_equity(
    account,
    books,
    fee,
    slip,
):
    cash = D(account["cash_try"])
    value = D(0)

    for symbol, pos in account[
        "positions"
    ].items():

        qty = D(pos["quantity"])

        bid = books[symbol]["bid"]

        fill = bid * (D(1) - slip)

        value += (
            qty
            * fill
            * (D(1) - fee)
        )

    return cash + value


def risk_for_buy(
    strategy,
    account,
    books,
    peaks,
    fee,
    slip,
    budget,
    max_positions,
    max_invested_fraction,
    daily_loss_fraction,
    dd_fraction,
    staged_daily_realized,
):
    reasons = []

    positions = account["positions"]

    initial = D("10000")

    if len(positions) >= max_positions:
        reasons.append("MAX_POSITIONS")

    invested = sum(
        (
            D(p["total_cost_try"])
            for p in positions.values()
        ),
        D(0),
    )

    projected = invested + budget

    if projected > (
        initial * max_invested_fraction
    ):
        reasons.append(
            "MAX_INVESTED_CAPITAL"
        )

    equity = liquidation_equity(
        account,
        books,
        fee,
        slip,
    )

    previous_peak = D(
        peaks["strategies"][
            strategy
        ]["peak_equity_try"]
    )

    peak = max(
        initial,
        previous_peak,
        equity,
    )

    dd = (
        (peak - equity) / peak
        if peak > 0
        else D(0)
    )

    if dd >= dd_fraction:
        reasons.append(
            "EQUITY_DRAWDOWN_KILL"
        )

    today = utcnow().date()

    day_pnl = (
        daily_realized(
            V1_TRADES,
            strategy,
            today,
        )
        + daily_realized(
            TRADES,
            strategy,
            today,
        )
        + staged_daily_realized
    )

    if day_pnl <= -(
        initial * daily_loss_fraction
    ):
        reasons.append(
            "DAILY_REALIZED_LOSS_LIMIT"
        )

    return {
        "allowed": not reasons,
        "reasons": reasons,
        "equity": equity,
        "peak": peak,
        "dd": dd,
        "day_pnl": day_pnl,
        "invested": invested,
    }


def journal_path(close_key):
    safe = close_key.replace(
        ":",
        "-",
    )

    return JOURNAL_DIR / (
        f"{safe}.json"
    )


def commit_journal(path):
    j = read_json(path)

    if j["status"] == "COMMITTED":
        return

    j["status"] = "COMMITTING"
    atomic_json(path, j)

    append_unique(
        SIGNALS,
        SIGNAL_FIELDS,
        j["signals"],
        "signal_id",
    )

    append_unique(
        TRADES,
        TRADE_FIELDS,
        j["trades"],
        "trade_id",
    )

    append_unique(
        RUNS,
        RUN_FIELDS,
        [j["run"]],
        "commit_id",
    )

    atomic_json(
        STATE,
        j["new_state"],
    )

    atomic_json(
        PEAKS,
        j["new_peaks"],
    )

    j["status"] = "COMMITTED"
    j["committed_at_utc"] = (
        utcnow().isoformat()
    )

    atomic_json(path, j)


def recover_prepared():
    JOURNAL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    pending = []

    for p in sorted(
        JOURNAL_DIR.glob("*.json")
    ):
        try:
            j = read_json(p)

            if j.get("status") in (
                "PREPARED",
                "COMMITTING",
            ):
                pending.append(p)

        except Exception as exc:
            raise RuntimeError(
                f"Journal okunamadi: {p}: {exc}"
            )

    for p in pending:
        print(
            "RECOVERY COMMIT:",
            p.name,
        )
        commit_journal(p)


def deterministic_id(*parts):
    raw = "|".join(
        str(x) for x in parts
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def main():
    if not STATE.exists():
        raise SystemExit(
            "V3 state bulunamadi."
        )

    recover_prepared()

    state = read_json(STATE)
    peaks = load_peaks()

    fee = D(
        state["rules"]["fee_rate"]
    )

    slip = D(
        state["rules"]["slippage_rate"]
    )

    budget = D(
        state["rules"]["order_budget_try"]
    )

    max_positions = int(
        state["rules"][
            "max_positions_per_strategy"
        ]
    )

    max_invested_fraction = D("1.00")
    daily_loss_fraction = D("0.05")
    dd_fraction = D("0.15")

    now = utcnow()
    now_ms = int(
        now.timestamp() * 1000
    )

    target_open = (
        now_ms // HOUR - 1
    ) * HOUR

    target_close = (
        target_open + HOUR
    )

    close_key = iso(target_close)

    if close_key in state.get(
        "processed_candle_closes",
        [],
    ):
        print(
            "Bu mum zaten islendi:",
            close_key,
        )
        return 0

    # No missed-hour backfill.
    # Only latest fully closed candle is observed.

    market = {}
    signal_rows = []
    errors = []

    for symbol in state["universe"]:
        try:
            hist = fetch_history(
                symbol,
                target_open,
                now_ms,
            )

            closes = [
                D(str(x[4]))
                for x in hist
            ]

            sigs = calc_signals(closes)

            market[symbol] = {
                "close": closes[-1],
                "signals": sigs,
            }

            for strategy, values in sigs.items():
                action, ind1, ind2 = values

                signal_id = deterministic_id(
                    close_key,
                    strategy,
                    symbol,
                    "SIGNAL",
                )

                signal_rows.append({
                    "signal_id": signal_id,
                    "observed_at_utc":
                        utcnow().isoformat(),
                    "candle_open_utc":
                        iso(target_open),
                    "candle_close_utc":
                        close_key,
                    "symbol": symbol,
                    "strategy": strategy,
                    "signal": action,
                    "close_price":
                        str(closes[-1]),
                    "indicator_1":
                        str(ind1),
                    "indicator_2":
                        str(ind2),
                    "protocol":
                        "V3_BOOK_ATOMIC",
                    "status":
                        "PROSPECTIVE_OBSERVED",
                })

        except Exception as exc:
            errors.append(
                (symbol, str(exc))
            )

    if errors:
        for symbol, error in errors:
            print(
                symbol,
                "HATA:",
                error,
            )

        raise SystemExit(1)

    if len(market) != 21:
        raise SystemExit(
            "21/21 market integrity FAIL"
        )

    if len(signal_rows) != 63:
        raise SystemExit(
            "63/63 signal integrity FAIL"
        )

    # One common runtime order-book snapshot.
    books = fetch_book_snapshot(
        state["universe"]
    )

    staged = copy.deepcopy(state)
    staged_peaks = copy.deepcopy(peaks)

    trades = []
    blocked_buys = 0

    staged_daily = {
        s: D(0)
        for s in STRATEGIES
    }

    # SELL FIRST
    for strategy in STRATEGIES:
        account = staged[
            "strategies"
        ][strategy]

        cash = D(
            account["cash_try"]
        )

        positions = account[
            "positions"
        ]

        sells = sorted(
            symbol
            for symbol in state["universe"]
            if (
                market[symbol][
                    "signals"
                ][strategy][0]
                == "SELL"
            )
        )

        for symbol in sells:
            if symbol not in positions:
                continue

            book = books[symbol]

            reference = book["bid"]

            fill = (
                reference
                * (D(1) - slip)
            )

            qty = D(
                positions[symbol][
                    "quantity"
                ]
            )

            gross = qty * fill
            trade_fee = gross * fee
            received = gross - trade_fee

            cost = D(
                positions[symbol][
                    "total_cost_try"
                ]
            )

            pnl = received - cost
            cash += received

            staged_daily[
                strategy
            ] += pnl

            account[
                "realized_pnl_try"
            ] = str(
                D(
                    account[
                        "realized_pnl_try"
                    ]
                ) + pnl
            )

            account["trade_count"] += 1

            trade_id = deterministic_id(
                close_key,
                strategy,
                symbol,
                "SELL",
            )

            trades.append({
                "trade_id": trade_id,
                "executed_at_utc":
                    utcnow().isoformat(),
                "signal_candle_close_utc":
                    close_key,
                "strategy": strategy,
                "symbol": symbol,
                "side": "SELL",
                "observed_bid":
                    str(book["bid"]),
                "observed_ask":
                    str(book["ask"]),
                "reference_price":
                    str(reference),
                "modeled_fill_price":
                    str(fill),
                "quantity": str(qty),
                "gross_try": str(gross),
                "fee_try": str(trade_fee),
                "cash_after_try":
                    str(cash),
                "realized_pnl_try":
                    str(pnl),
                "protocol":
                    "V3_BOOK_ATOMIC",
                "status":
                    "PAPER_MODELED_FILL",
            })

            del positions[symbol]

        account["cash_try"] = str(cash)

    # BUY AFTER ALL SELLS
    for strategy in STRATEGIES:
        account = staged[
            "strategies"
        ][strategy]

        cash = D(
            account["cash_try"]
        )

        positions = account[
            "positions"
        ]

        buys = sorted(
            symbol
            for symbol in state["universe"]
            if (
                market[symbol][
                    "signals"
                ][strategy][0]
                == "BUY"
            )
        )

        for symbol in buys:
            if symbol in positions:
                continue

            if cash < budget:
                blocked_buys += 1
                print(
                    strategy,
                    symbol,
                    "BUY BLOCK: CASH",
                )
                continue

            risk = risk_for_buy(
                strategy,
                account,
                books,
                staged_peaks,
                fee,
                slip,
                budget,
                max_positions,
                max_invested_fraction,
                daily_loss_fraction,
                dd_fraction,
                staged_daily[strategy],
            )

            # Persist newest peak in staged data.
            staged_peaks[
                "strategies"
            ][strategy][
                "peak_equity_try"
            ] = str(risk["peak"])

            if not risk["allowed"]:
                blocked_buys += 1

                print(
                    strategy,
                    symbol,
                    "BUY BLOCK:",
                    ",".join(
                        risk["reasons"]
                    ),
                )

                continue

            book = books[symbol]

            reference = book["ask"]

            fill = (
                reference
                * (D(1) + slip)
            )

            qty = (
                budget
                / (
                    (D(1) + fee)
                    * fill
                )
            ).quantize(
                QTY_STEP,
                rounding=ROUND_DOWN,
            )

            if qty <= 0:
                blocked_buys += 1
                continue

            gross = qty * fill
            trade_fee = gross * fee
            cost = gross + trade_fee

            if cost > cash:
                blocked_buys += 1
                continue

            cash -= cost

            executed = utcnow().isoformat()

            positions[symbol] = {
                "quantity": str(qty),
                "observed_entry_price":
                    str(reference),
                "observed_bid":
                    str(book["bid"]),
                "observed_ask":
                    str(book["ask"]),
                "modeled_entry_price":
                    str(fill),
                "total_cost_try":
                    str(cost),
                "signal_candle_close_utc":
                    close_key,
                "executed_at_utc":
                    executed,
                "protocol":
                    "V3_BOOK_ATOMIC",
            }

            account["trade_count"] += 1

            trade_id = deterministic_id(
                close_key,
                strategy,
                symbol,
                "BUY",
            )

            trades.append({
                "trade_id": trade_id,
                "executed_at_utc":
                    executed,
                "signal_candle_close_utc":
                    close_key,
                "strategy": strategy,
                "symbol": symbol,
                "side": "BUY",
                "observed_bid":
                    str(book["bid"]),
                "observed_ask":
                    str(book["ask"]),
                "reference_price":
                    str(reference),
                "modeled_fill_price":
                    str(fill),
                "quantity": str(qty),
                "gross_try":
                    str(gross),
                "fee_try":
                    str(trade_fee),
                "cash_after_try":
                    str(cash),
                "realized_pnl_try":
                    "",
                "protocol":
                    "V3_BOOK_ATOMIC",
                "status":
                    "PAPER_MODELED_FILL",
            })

            account["cash_try"] = str(cash)

    # Update peaks after final staged portfolio.
    for strategy in STRATEGIES:
        account = staged[
            "strategies"
        ][strategy]

        equity = liquidation_equity(
            account,
            books,
            fee,
            slip,
        )

        old_peak = D(
            staged_peaks[
                "strategies"
            ][strategy][
                "peak_equity_try"
            ]
        )

        staged_peaks[
            "strategies"
        ][strategy][
            "peak_equity_try"
        ] = str(
            max(
                D("10000"),
                old_peak,
                equity,
            )
        )

    staged.setdefault(
        "processed_candle_closes",
        [],
    ).append(close_key)

    staged[
        "last_successful_run_utc"
    ] = utcnow().isoformat()

    staged[
        "active_protocol"
    ] = "V3_BOOK_ATOMIC"

    commit_id = deterministic_id(
        close_key,
        "V3_BOOK_ATOMIC",
    )

    run_row = {
        "commit_id": commit_id,
        "run_utc":
            utcnow().isoformat(),
        "candle_close_utc":
            close_key,
        "symbols":
            len(market),
        "signal_rows":
            len(signal_rows),
        "paper_trades":
            len(trades),
        "blocked_buys":
            blocked_buys,
        "status":
            "OK",
    }

    journal = {
        "version": 3,
        "commit_id": commit_id,
        "status": "PREPARED",
        "prepared_at_utc":
            utcnow().isoformat(),
        "candle_open_utc":
            iso(target_open),
        "candle_close_utc":
            close_key,
        "signals": signal_rows,
        "trades": trades,
        "run": run_row,
        "new_state": staged,
        "new_peaks": staged_peaks,
    }

    JOURNAL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    jp = journal_path(close_key)

    if jp.exists():
        existing = read_json(jp)

        if existing.get(
            "commit_id"
        ) != commit_id:
            raise RuntimeError(
                "Journal commit ID conflict"
            )

        if existing.get(
            "status"
        ) == "COMMITTED":
            print(
                "Journal zaten COMMITTED."
            )
            return 0

    else:
        atomic_json(
            jp,
            journal,
        )

    # From here crash recovery is possible.
    commit_journal(jp)

    print("")
    print("=" * 72)
    print("MULTISTRATEGY LIVE PAPER V3")
    print("=" * 72)
    print("Candle       :", close_key)
    print("Symbols      :", len(market))
    print("Signal rows  :", len(signal_rows))
    print("Paper trades :", len(trades))
    print("Blocked buys :", blocked_buys)
    print("Journal      : COMMITTED")
    print("REAL ORDERS  : NO")
    print("V3 RUN OK")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())

    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(130)

    except Exception as exc:
        print(
            "V3 FATAL:",
            type(exc).__name__,
            str(exc),
        )
        sys.exit(1)

