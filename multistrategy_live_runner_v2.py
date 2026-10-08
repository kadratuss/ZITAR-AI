import csv
import json
import time
from datetime import datetime, timezone
from decimal import Decimal, getcontext, ROUND_DOWN
from pathlib import Path

import requests

getcontext().prec = 28
D = Decimal

ROOT = Path(__file__).resolve().parent

STATE   = ROOT / "multistrategy_live_state_v1.json"
SIGNALS = ROOT / "multistrategy_live_signals_v1.csv"
TRADES  = ROOT / "multistrategy_live_trades_v1.csv"
RUNLOG  = ROOT / "multistrategy_live_runs_v1.csv"

KLINE_API = "https://api.binance.me/api/v1/klines"
TICKER_API = "https://api.binance.me/api/v3/ticker/price"

HOUR = 3_600_000
QTY_STEP = D("0.00000001")

if not STATE.exists():
    raise SystemExit("State bulunamadi.")

state = json.loads(STATE.read_text(encoding="utf-8"))

FEE = D(state["rules"]["fee_rate"])
SLIP = D(state["rules"]["slippage_rate"])
BUDGET = D(state["rules"]["order_budget_try"])
MAX_POS = int(state["rules"]["max_positions_per_strategy"])

# ------------------------------------------------------------
# V2 RISK ENFORCEMENT
# ------------------------------------------------------------

RISK_CONFIG_FILE = ROOT / "multistrategy_risk_config_v1.json"
RISK_AUDIT = ROOT / "multistrategy_risk_decisions_v2.csv"

if not RISK_CONFIG_FILE.exists():
    raise SystemExit("Risk config bulunamadi - FAIL CLOSED.")

risk_config = json.loads(
    RISK_CONFIG_FILE.read_text(encoding="utf-8")
)

DAILY_LOSS_FRAC = D(
    risk_config["daily_realized_loss_limit_fraction"]
)

MAX_INVESTED_FRAC = D(
    risk_config["max_invested_fraction"]
)

DD_KILL_FRAC = D(
    risk_config["equity_drawdown_kill_fraction"]
)

RISK_PEAKS = ROOT / "multistrategy_risk_peaks_v3.json"

risk_audit_fields = [
    "evaluated_at_utc",
    "candle_close_utc",
    "strategy",
    "symbol",
    "side",
    "decision",
    "reasons",
    "equity_try",
    "peak_equity_try",
    "drawdown_percent",
    "daily_realized_pnl_try",
    "positions",
    "invested_cost_try",
    "status"
]

freeze = datetime.fromisoformat(
    state["created_at_utc"].replace("Z", "+00:00")
)
freeze_ms = int(freeze.timestamp() * 1000)

now = datetime.now(timezone.utc)
now_ms = int(now.timestamp() * 1000)

# Son tamamen kapanmis mum.
target_open = (now_ms // HOUR - 1) * HOUR
target_close = target_open + HOUR

def iso(ms):
    return datetime.fromtimestamp(
        ms / 1000, tz=timezone.utc
    ).isoformat()

# Mumun TAMAMI freeze sonrasinda olmali.
if target_open < freeze_ms:
    print("Ilk tamamen post-freeze 1h mum henuz kapanmadi.")
    print("Freeze :", state["created_at_utc"])
    print("Target :", iso(target_open), "->", iso(target_close))
    raise SystemExit(0)

close_key = iso(target_close)

if close_key in state.get("processed_candle_closes", []):
    print("Bu mum zaten islendi:", close_key)
    raise SystemExit(0)

def get_json(url, params):
    last = None

    for attempt in range(4):
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            if attempt < 3:
                time.sleep(2)

    raise RuntimeError(last)

def fetch_history(symbol):
    data = get_json(
        KLINE_API,
        {
            "symbol": symbol,
            "interval": "1h",
            "limit": 120
        }
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
        raise RuntimeError("Hedef kapanmis mum bulunamadi")

    history = closed[:idx + 1]

    if len(history) < 60:
        raise RuntimeError(
            f"Yetersiz history: {len(history)}"
        )

    return history

def current_price(symbol):
    data = get_json(
        TICKER_API,
        {"symbol": symbol}
    )
    return D(str(data["price"]))

def read_csv_rows(path):
    if not path.exists():
        return []

    with path.open(
        "r",
        newline="",
        encoding="utf-8"
    ) as f:
        return list(csv.DictReader(f))


def parse_dt(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def daily_realized_from_existing_trades(strategy):
    total = D(0)
    today = datetime.now(timezone.utc).date()

    for row in read_csv_rows(TRADES):

        if row.get("strategy") != strategy:
            continue

        if row.get("side", "").upper() != "SELL":
            continue

        value = row.get("executed_at_utc")

        if not value:
            continue

        try:
            t = parse_dt(value)
        except Exception:
            continue

        if t.astimezone(timezone.utc).date() != today:
            continue

        pnl = row.get("realized_pnl_try")

        if pnl not in (None, ""):
            total += D(str(pnl))

    return total


def load_peak(strategy, initial):
    if not RISK_PEAKS.exists():
        return initial

    try:
        data = json.loads(
            RISK_PEAKS.read_text(encoding="utf-8")
        )

        return D(
            data.get(
                "strategies",
                {}
            ).get(
                strategy,
                {}
            ).get(
                "peak_equity_try",
                str(initial)
            )
        )

    except Exception:
        # Risk metadata unreadable => fail closed later.
        return None


def evaluate_buy_risk(
    strategy,
    account,
    snapshot_prices,
    extra_realized=D(0)
):
    reasons = []

    initial = D(
        account.get(
            "initial_cash_try",
            "10000"
        )
    )

    cash = D(account["cash_try"])
    positions = account["positions"]

    invested = D(0)
    liquidation = D(0)

    for sym, p in positions.items():

        invested += D(
            p["total_cost_try"]
        )

        if sym not in snapshot_prices:
            reasons.append(
                "MISSING_RISK_PRICE"
            )
            continue

        qty = D(p["quantity"])

        liquidation += (
            qty
            * snapshot_prices[sym]
            * (D(1) - SLIP)
            * (D(1) - FEE)
        )

    equity = cash + liquidation

    peak = load_peak(
        strategy,
        initial
    )

    if peak is None:
        reasons.append(
            "PEAK_STATE_ERROR"
        )
        peak = initial

    peak = max(
        peak,
        initial,
        equity
    )

    if peak > 0:
        dd = (
            peak - equity
        ) / peak
    else:
        dd = D(0)

    if len(positions) >= MAX_POS:
        reasons.append(
            "MAX_POSITIONS"
        )

    max_invested = (
        initial
        * MAX_INVESTED_FRAC
    )

    if invested >= max_invested:
        reasons.append(
            "MAX_INVESTED_CAPITAL"
        )

    day_pnl = (
        daily_realized_from_existing_trades(
            strategy
        )
        + extra_realized
    )

    daily_limit = (
        initial
        * DAILY_LOSS_FRAC
    )

    if day_pnl <= -daily_limit:
        reasons.append(
            "DAILY_REALIZED_LOSS_LIMIT"
        )

    if dd >= DD_KILL_FRAC:
        reasons.append(
            "EQUITY_DRAWDOWN_KILL"
        )

    return {
        "allowed": len(reasons) == 0,
        "reasons": reasons,
        "equity": equity,
        "peak": peak,
        "dd": dd,
        "daily_pnl": day_pnl,
        "invested": invested
    }


def write_risk_audit(
    strategy,
    symbol,
    side,
    decision,
    risk
):
    new_file = not RISK_AUDIT.exists()

    with RISK_AUDIT.open(
        "a",
        newline="",
        encoding="utf-8"
    ) as f:

        w = csv.DictWriter(
            f,
            fieldnames=risk_audit_fields
        )

        if new_file:
            w.writeheader()

        w.writerow({
            "evaluated_at_utc":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "candle_close_utc":
                close_key,

            "strategy":
                strategy,

            "symbol":
                symbol,

            "side":
                side,

            "decision":
                decision,

            "reasons":
                "|".join(
                    risk["reasons"]
                ),

            "equity_try":
                str(risk["equity"]),

            "peak_equity_try":
                str(risk["peak"]),

            "drawdown_percent":
                str(
                    risk["dd"] * D(100)
                ),

            "daily_realized_pnl_try":
                str(risk["daily_pnl"]),

            "positions":
                "",

            "invested_cost_try":
                str(risk["invested"]),

            "status":
                "PAPER_RISK_V2"
        })


def ema(values, n):
    a = D(2) / D(n + 1)
    e = values[0]

    for x in values[1:]:
        e = a*x + (D(1)-a)*e

    return e

def rsi(values, n=14):
    gains = D(0)
    losses = D(0)

    for i in range(len(values)-n, len(values)):
        change = values[i] - values[i-1]

        if change > 0:
            gains += change
        elif change < 0:
            losses -= change

    avg_gain = gains / D(n)
    avg_loss = losses / D(n)

    if avg_loss == 0:
        return D(100)

    rs = avg_gain / avg_loss
    return D(100) - D(100)/(D(1)+rs)

def calc_signals(closes):

    # SMA20/50
    p20 = sum(closes[-21:-1]) / D(20)
    p50 = sum(closes[-51:-1]) / D(50)

    c20 = sum(closes[-20:]) / D(20)
    c50 = sum(closes[-50:]) / D(50)

    sma_sig = "NONE"

    if p20 <= p50 and c20 > c50:
        sma_sig = "BUY"
    elif p20 >= p50 and c20 < c50:
        sma_sig = "SELL"

    # EMA12/26
    prev = closes[:-1]

    pe12 = ema(prev, 12)
    pe26 = ema(prev, 26)

    ce12 = ema(closes, 12)
    ce26 = ema(closes, 26)

    ema_sig = "NONE"

    if pe12 <= pe26 and ce12 > ce26:
        ema_sig = "BUY"
    elif pe12 >= pe26 and ce12 < ce26:
        ema_sig = "SELL"

    # RSI14
    prsi = rsi(closes[:-1], 14)
    crsi = rsi(closes, 14)

    rsi_sig = "NONE"

    if prsi <= D(30) and crsi > D(30):
        rsi_sig = "BUY"
    elif prsi >= D(70) and crsi < D(70):
        rsi_sig = "SELL"

    return {
        "SMA20_50": (
            sma_sig,
            c20,
            c50
        ),
        "EMA12_26": (
            ema_sig,
            ce12,
            ce26
        ),
        "RSI14": (
            rsi_sig,
            crsi,
            D(30) if rsi_sig == "BUY"
            else D(70)
        )
    }

signal_fields = [
    "observed_at_utc",
    "candle_open_utc",
    "candle_close_utc",
    "symbol",
    "strategy",
    "signal",
    "close_price",
    "indicator_1",
    "indicator_2",
    "status"
]

trade_fields = [
    "executed_at_utc",
    "signal_candle_close_utc",
    "execution_candle_open_utc",
    "strategy",
    "symbol",
    "side",
    "market_open_price",
    "modeled_fill_price",
    "quantity",
    "gross_try",
    "fee_try",
    "cash_after_try",
    "realized_pnl_try",
    "status"
]

all_signals = []
errors = []

print("")
print("=" * 76)
print("MULTISTRATEGY LIVE PAPER V2 - RISK ENFORCED")
print("Observed UTC :", now.isoformat())
print("Candle       :", iso(target_open), "->", iso(target_close))
print("=" * 76)
print("")

# ------------------------------------------------------------
# 1. OBSERVE ALL DATA FIRST
# ------------------------------------------------------------

market = {}

for symbol in state["universe"]:

    try:
        hist = fetch_history(symbol)

        closes = [
            D(str(x[4]))
            for x in hist
        ]

        close_price = closes[-1]

        sigs = calc_signals(closes)

        market[symbol] = {
            "signals": sigs,
            "close": close_price
        }

        for strategy, values in sigs.items():

            action, ind1, ind2 = values

            all_signals.append({
                "observed_at_utc":
                    datetime.now(timezone.utc).isoformat(),

                "candle_open_utc":
                    iso(target_open),

                "candle_close_utc":
                    iso(target_close),

                "symbol": symbol,
                "strategy": strategy,
                "signal": action,
                "close_price": str(close_price),
                "indicator_1": str(ind1),
                "indicator_2": str(ind2),
                "status": "PROSPECTIVE_OBSERVED"
            })

        print(
            f"{symbol:<12} "
            f"SMA={sigs['SMA20_50'][0]:<4} "
            f"EMA={sigs['EMA12_26'][0]:<4} "
            f"RSI={sigs['RSI14'][0]:<4}"
        )

    except Exception as e:
        errors.append((symbol, str(e)))
        print(symbol, "HATA:", e)

# Atomik davranis:
# 21 sembol eksiksiz degilse hicbir sey isleme.
if errors or len(market) != len(state["universe"]):

    print("")
    print("DURDURULDU.")
    print("Eksik/hata bulunan piyasa verisi nedeniyle")
    print("bu saat icin sinyal veya paper fill yazilmadi.")

    for x in errors:
        print(x[0], "->", x[1])

    raise SystemExit(1)

# ------------------------------------------------------------
# 2. SAVE OBSERVED SIGNALS
# ------------------------------------------------------------

with SIGNALS.open("a", newline="", encoding="utf-8") as f:

    w = csv.DictWriter(
        f,
        fieldnames=signal_fields
    )

    for row in all_signals:
        w.writerow(row)

# ------------------------------------------------------------
# 3. PAPER EXECUTION
#
# Burada gecmis hourly OPEN kullanmiyoruz.
# Gercekte observer calistigi anda gorulen ticker fiyatini aliyoruz.
# Sonra ayni %0.1 modeled slip uygulanir.
# ------------------------------------------------------------

new_trades = []

# ------------------------------------------------------------
# V2 EXECUTION / RISK PRICE SNAPSHOT
#
# Every symbol that may be required for:
# - a BUY/SELL action
# - valuation of an existing position
# is fetched BEFORE portfolio mutation.
#
# If any required price fails => FAIL CLOSED.
# ------------------------------------------------------------

snapshot_symbols = set()

for strategy_name in (
    "SMA20_50",
    "EMA12_26",
    "RSI14"
):
    for sym in state["universe"]:

        action = market[sym][
            "signals"
        ][strategy_name][0]

        if action in (
            "BUY",
            "SELL"
        ):
            snapshot_symbols.add(sym)

    snapshot_symbols.update(
        state[
            "strategies"
        ][strategy_name][
            "positions"
        ].keys()
    )

execution_prices = {}
snapshot_errors = []

for sym in sorted(
    snapshot_symbols
):
    try:
        execution_prices[sym] = current_price(
            sym
        )
    except Exception as e:
        snapshot_errors.append(
            (sym, str(e))
        )

if snapshot_errors:

    print("")
    print(
        "V2 FAIL CLOSED: execution/risk "
        "price snapshot eksik."
    )

    for sym, err in snapshot_errors:
        print(sym, "->", err)

    # IMPORTANT:
    # V1 has already written signals above.
    # Do not execute or mark candle processed.
    # Retry remains possible, but may duplicate
    # signal rows. Full transactional commit is
    # deferred to V3 runner.
    raise SystemExit(1)


# Daily realized generated during THIS run,
# before trade CSV is committed.
session_realized = {
    "SMA20_50": D(0),
    "EMA12_26": D(0),
    "RSI14": D(0)
}


for strategy in (
    "SMA20_50",
    "EMA12_26",
    "RSI14"
):

    account = state["strategies"][strategy]

    cash = D(account["cash_try"])
    positions = account["positions"]

    # SELL FIRST
    sell_symbols = sorted([
        s for s in state["universe"]
        if market[s]["signals"][strategy][0] == "SELL"
    ])

    for symbol in sell_symbols:

        if symbol not in positions:
            continue

        observed = execution_prices[symbol]
        fill = observed * (D(1) - SLIP)

        qty = D(positions[symbol]["quantity"])

        gross = qty * fill
        fee = gross * FEE
        received = gross - fee

        cost = D(
            positions[symbol]["total_cost_try"]
        )

        pnl = received - cost
        cash += received

        session_realized[strategy] += pnl

        account["realized_pnl_try"] = str(
            D(account["realized_pnl_try"]) + pnl
        )

        account["trade_count"] += 1

        new_trades.append({
            "executed_at_utc":
                datetime.now(timezone.utc).isoformat(),
            "signal_candle_close_utc":
                iso(target_close),
            "execution_candle_open_utc":
                "",
            "strategy": strategy,
            "symbol": symbol,
            "side": "SELL",
            "market_open_price": str(observed),
            "modeled_fill_price": str(fill),
            "quantity": str(qty),
            "gross_try": str(gross),
            "fee_try": str(fee),
            "cash_after_try": str(cash),
            "realized_pnl_try": str(pnl),
            "status": "LIVE_OBSERVED_PRICE_MODELED_FILL"
        })

        del positions[symbol]

        print(
            strategy,
            symbol,
            "SELL",
            "observed=", observed,
            "fill=", fill,
            "pnl=", pnl
        )

    # BUY AFTER SELL
    buy_symbols = sorted([
        s for s in state["universe"]
        if market[s]["signals"][strategy][0] == "BUY"
    ])

    for symbol in buy_symbols:

        if symbol in positions:
            continue

        if len(positions) >= MAX_POS:
            print(
                strategy,
                symbol,
                "BUY SKIP: capacity"
            )
            continue

        if cash < BUDGET:
            print(
                strategy,
                symbol,
                "BUY SKIP: cash"
            )
            continue

        # ---------------------------------------------
        # V2 ENFORCED BUY RISK GATE
        # ---------------------------------------------

        # account cash must reflect SELLs already made
        # during this same strategy pass.
        account["cash_try"] = str(cash)
        account["positions"] = positions

        risk = evaluate_buy_risk(
            strategy,
            account,
            execution_prices,
            session_realized[strategy]
        )

        if not risk["allowed"]:

            write_risk_audit(
                strategy,
                symbol,
                "BUY",
                "BLOCK",
                risk
            )

            print(
                strategy,
                symbol,
                "BUY BLOCKED BY RISK:",
                ",".join(
                    risk["reasons"]
                )
            )

            continue

        write_risk_audit(
            strategy,
            symbol,
            "BUY",
            "ALLOW",
            risk
        )

        observed = execution_prices[symbol]
        fill = observed * (D(1) + SLIP)

        qty = (
            BUDGET /
            ((D(1) + FEE) * fill)
        ).quantize(
            QTY_STEP,
            rounding=ROUND_DOWN
        )

        gross = qty * fill
        fee = gross * FEE
        cost = gross + fee

        if cost > cash:
            continue

        cash -= cost

        positions[symbol] = {
            "quantity": str(qty),
            "observed_entry_price": str(observed),
            "modeled_entry_price": str(fill),
            "total_cost_try": str(cost),
            "signal_candle_close_utc":
                iso(target_close),
            "executed_at_utc":
                datetime.now(timezone.utc).isoformat()
        }

        account["trade_count"] += 1

        new_trades.append({
            "executed_at_utc":
                datetime.now(timezone.utc).isoformat(),
            "signal_candle_close_utc":
                iso(target_close),
            "execution_candle_open_utc":
                "",
            "strategy": strategy,
            "symbol": symbol,
            "side": "BUY",
            "market_open_price": str(observed),
            "modeled_fill_price": str(fill),
            "quantity": str(qty),
            "gross_try": str(gross),
            "fee_try": str(fee),
            "cash_after_try": str(cash),
            "realized_pnl_try": "",
            "status": "LIVE_OBSERVED_PRICE_MODELED_FILL"
        })

        print(
            strategy,
            symbol,
            "BUY",
            "observed=", observed,
            "fill=", fill,
            "cost=", cost
        )

    account["cash_try"] = str(cash)
    account["positions"] = positions

# ------------------------------------------------------------
# 4. SAVE TRADES
# ------------------------------------------------------------

if new_trades:

    with TRADES.open(
        "a",
        newline="",
        encoding="utf-8"
    ) as f:

        w = csv.DictWriter(
            f,
            fieldnames=trade_fields
        )

        for row in new_trades:
            w.writerow(row)

# Only now mark candle processed.
state["processed_candle_closes"].append(
    close_key
)

state["last_successful_run_utc"] = (
    datetime.now(timezone.utc).isoformat()
)

STATE.write_text(
    json.dumps(
        state,
        indent=2,
        ensure_ascii=False
    ),
    encoding="utf-8"
)

# ------------------------------------------------------------
# 5. RUN AUDIT LOG
# ------------------------------------------------------------

run_fields = [
    "run_utc",
    "candle_close_utc",
    "symbols",
    "signal_rows",
    "paper_trades",
    "status"
]

new_log = not RUNLOG.exists()

with RUNLOG.open(
    "a",
    newline="",
    encoding="utf-8"
) as f:

    w = csv.DictWriter(
        f,
        fieldnames=run_fields
    )

    if new_log:
        w.writeheader()

    w.writerow({
        "run_utc":
            datetime.now(timezone.utc).isoformat(),
        "candle_close_utc":
            close_key,
        "symbols":
            len(market),
        "signal_rows":
            len(all_signals),
        "paper_trades":
            len(new_trades),
        "status":
            "OK"
    })

print("")
print("=" * 76)
print("LIVE PAPER DURUM")
print("=" * 76)

for strategy in (
    "SMA20_50",
    "EMA12_26",
    "RSI14"
):

    a = state["strategies"][strategy]

    print(
        f"{strategy:<10} "
        f"cash={D(a['cash_try']):.2f} "
        f"positions={len(a['positions'])} "
        f"trades={a['trade_count']} "
        f"realized={D(a['realized_pnl_try']):.2f}"
    )

print("")
print("Signal rows :", len(all_signals))
print("New trades  :", len(new_trades))
print("Errors      :", len(errors))
print("")
print("GERCEK EMIR YOK.")
print("MULTISTRATEGY LIVE PAPER V2 RUN OK.")

