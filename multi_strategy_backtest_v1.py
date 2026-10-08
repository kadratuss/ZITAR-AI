import sqlite3
from decimal import Decimal, getcontext
from pathlib import Path
from datetime import datetime, timezone

getcontext().prec = 28
D = Decimal

ROOT = Path(__file__).resolve().parent
DB = ROOT / "long_history.db"

INITIAL = D("10000")
BUDGET = D("1000")
FEE = D("0.001")
SLIP = D("0.001")
MAX_POS = 10
HOUR = 3600000

# Ayni sabit historical pencere
START = int(datetime(
    2026, 8, 26, 20, 0, tzinfo=timezone.utc
).timestamp() * 1000)

END = int(datetime(
    2026, 9, 22, 19, 0, tzinfo=timezone.utc
).timestamp() * 1000)

SYMBOLS = [
    "AVAXTRY","BTCTRY","COTITRY","DOGETRY","ENATRY",
    "ETHTRY","FORMTRY","GTRY","MINATRY","MUBARAKTRY",
    "NEARTRY","ONETRY","PENGUTRY","PEPETRY","PHATRY",
    "SAGATRY","SOLTRY","TRUMPTRY","TSTTRY","USDTTRY",
    "XRPTRY"
]

def load_all():
    con = sqlite3.connect(DB)
    data = {}

    for symbol in SYMBOLS:
        rows = con.execute("""
            SELECT open_time_ms, open_price, close_price
            FROM historical_candles
            WHERE symbol=?
              AND interval='1h'
              AND open_time_ms >= ?
              AND open_time_ms <= ?
            ORDER BY open_time_ms
        """, (symbol, START - 60 * HOUR, END)).fetchall()

        data[symbol] = [
            (int(t), D(str(o)), D(str(c)))
            for t,o,c in rows
        ]

    con.close()
    return data

def sma(values, n):
    return sum(values[-n:]) / D(n)

def ema(values, n):
    a = D(2) / D(n + 1)
    e = values[0]
    for x in values[1:]:
        e = a*x + (D(1)-a)*e
    return e

def rsi(values, n=14):
    if len(values) < n+1:
        return None

    gain = D(0)
    loss = D(0)

    for i in range(len(values)-n, len(values)):
        d = values[i] - values[i-1]
        if d > 0:
            gain += d
        elif d < 0:
            loss -= d

    gain /= D(n)
    loss /= D(n)

    if loss == 0:
        return D(100)

    rs = gain/loss
    return D(100) - D(100)/(D(1)+rs)

def sig_sma(c):
    if len(c) < 51:
        return "NONE"

    p20 = sum(c[-21:-1])/D(20)
    p50 = sum(c[-51:-1])/D(50)
    n20 = sum(c[-20:])/D(20)
    n50 = sum(c[-50:])/D(50)

    if p20 <= p50 and n20 > n50:
        return "BUY"
    if p20 >= p50 and n20 < n50:
        return "SELL"
    return "NONE"

def sig_ema(c):
    if len(c) < 60:
        return "NONE"

    p = c[:-1]

    p12 = ema(p,12)
    p26 = ema(p,26)
    n12 = ema(c,12)
    n26 = ema(c,26)

    if p12 <= p26 and n12 > n26:
        return "BUY"
    if p12 >= p26 and n12 < n26:
        return "SELL"
    return "NONE"

def sig_rsi(c):
    if len(c) < 17:
        return "NONE"

    p = rsi(c[:-1],14)
    n = rsi(c,14)

    if p <= D(30) and n > D(30):
        return "BUY"
    if p >= D(70) and n < D(70):
        return "SELL"
    return "NONE"

STRATS = {
    "SMA20/50": sig_sma,
    "EMA12/26": sig_ema,
    "RSI14": sig_rsi
}

data = load_all()

maps = {}
for symbol, rows in data.items():
    maps[symbol] = {t:(o,c) for t,o,c in rows}

def history(symbol, t):
    rows = data[symbol]
    return [c for ts,o,c in rows if ts <= t]

def run(name, fn):

    cash = INITIAL
    positions = {}

    peak = INITIAL
    maxdd = D(0)

    buys = 0
    sells = 0

    times = list(range(START, END + 1, HOUR))

    for t in times:

        signals = {}

        # Sinyal t mumunun kapanisinda.
        for symbol in SYMBOLS:
            h = history(symbol,t)

            if not h:
                continue

            signals[symbol] = fn(h)

        # Islem bir sonraki mum OPEN.
        nxt = t + HOUR

        # SELL FIRST
        for symbol in sorted(SYMBOLS):

            if signals.get(symbol) != "SELL":
                continue

            if symbol not in positions:
                continue

            if nxt not in maps[symbol]:
                continue

            market_open = maps[symbol][nxt][0]
            fill = market_open * (D(1)-SLIP)

            qty = positions[symbol]["qty"]
            gross = qty * fill
            fee = gross * FEE

            cash += gross-fee

            del positions[symbol]
            sells += 1

        # BUY
        for symbol in sorted(SYMBOLS):

            if signals.get(symbol) != "BUY":
                continue

            if symbol in positions:
                continue

            if len(positions) >= MAX_POS:
                continue

            if cash < BUDGET:
                continue

            if nxt not in maps[symbol]:
                continue

            market_open = maps[symbol][nxt][0]
            fill = market_open * (D(1)+SLIP)

            qty = BUDGET / ((D(1)+FEE)*fill)

            gross = qty*fill
            fee = gross*FEE
            cost = gross+fee

            cash -= cost

            positions[symbol] = {
                "qty":qty
            }

            buys += 1

        # Mark-to-market
        equity = cash

        for symbol,p in positions.items():

            if nxt in maps[symbol]:
                close = maps[symbol][nxt][1]
            elif t in maps[symbol]:
                close = maps[symbol][t][1]
            else:
                continue

            # Estimated exit costs included
            value = (
                p["qty"]
                * close
                * (D(1)-SLIP)
                * (D(1)-FEE)
            )

            equity += value

        if equity > peak:
            peak = equity

        if peak > 0:
            dd = (peak-equity)/peak

            if dd > maxdd:
                maxdd = dd

    # Final valuation
    equity = cash

    for symbol,p in positions.items():

        valid = [
            c for ts,o,c in data[symbol]
            if ts <= END
        ]

        if not valid:
            continue

        close = valid[-1]

        equity += (
            p["qty"]
            * close
            * (D(1)-SLIP)
            * (D(1)-FEE)
        )

    net = equity-INITIAL
    pct = net/INITIAL*D(100)

    return {
        "name":name,
        "equity":equity,
        "net":net,
        "pct":pct,
        "dd":maxdd*D(100),
        "buys":buys,
        "sells":sells,
        "open":len(positions)
    }

print()
print("="*88)
print("PORTFOLIOAI MULTI STRATEGY BACKTEST V1")
print("COMMON PORTFOLIO / SAME COST MODEL")
print("="*88)
print()
print("Period :", datetime.fromtimestamp(
    START/1000,timezone.utc
).isoformat(), "->",
datetime.fromtimestamp(END/1000,timezone.utc).isoformat())
print("Capital:", INITIAL, "TRY")
print("Budget :", BUDGET, "TRY")
print("Fee    :", FEE)
print("Slip   :", SLIP)
print("MaxPos :", MAX_POS)
print()

results=[]

for name,fn in STRATS.items():
    print("Testing:",name)
    results.append(run(name,fn))

print()
print("="*88)
print("RESULTS")
print("="*88)

print(
    f"{'STRATEGY':<12}"
    f"{'EQUITY':>14}"
    f"{'NET':>14}"
    f"{'RETURN':>11}"
    f"{'MAXDD':>11}"
    f"{'BUY':>7}"
    f"{'SELL':>7}"
    f"{'OPEN':>7}"
)

for r in results:
    print(
        f"{r['name']:<12}"
        f"{r['equity']:>14.2f}"
        f"{r['net']:>14.2f}"
        f"{r['pct']:>10.2f}%"
        f"{r['dd']:>10.2f}%"
        f"{r['buys']:>7}"
        f"{r['sells']:>7}"
        f"{r['open']:>7}"
    )

print()
print("NOTE: HISTORICAL RESEARCH ONLY.")
print("NO REAL ORDERS.")
