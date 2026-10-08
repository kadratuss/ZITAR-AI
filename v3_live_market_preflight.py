import json
import time
import requests
from pathlib import Path
from decimal import Decimal

D = Decimal
ROOT = Path.cwd()

state = json.loads(
    (ROOT / "multistrategy_live_state_v3.json")
    .read_text(encoding="utf-8-sig")
)

universe = state["universe"]

KLINE = "https://api.binance.me/api/v1/klines"
BOOK  = "https://api.binance.me/api/v3/ticker/bookTicker"

HOUR = 3_600_000

now_ms = int(time.time() * 1000)
target_open = (now_ms // HOUR - 1) * HOUR
target_close = target_open + HOUR


def ema(values, n):
    a = D(2) / D(n + 1)
    e = values[0]

    for x in values[1:]:
        e = a * x + (D(1) - a) * e

    return e


def rsi(values, n=14):
    gains = D(0)
    losses = D(0)

    for i in range(len(values) - n, len(values)):
        ch = values[i] - values[i - 1]

        if ch > 0:
            gains += ch
        elif ch < 0:
            losses -= ch

    ag = gains / D(n)
    al = losses / D(n)

    if al == 0:
        return D(100)

    rs = ag / al

    return D(100) - D(100) / (D(1) + rs)


def signals(closes):
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

    pr = rsi(closes[:-1])
    cr = rsi(closes)

    rr = "NONE"

    if pr <= D(30) and cr > D(30):
        rr = "BUY"
    elif pr >= D(70) and cr < D(70):
        rr = "SELL"

    return sma, em, rr


print("TARGET OPEN MS :", target_open)
print("TARGET CLOSE MS:", target_close)
print("")

all_signals = []
errors = []

for symbol in universe:

    try:
        r = requests.get(
            KLINE,
            params={
                "symbol": symbol,
                "interval": "1h",
                "limit": 120,
            },
            timeout=15,
        )

        r.raise_for_status()
        data = r.json()

        closed = [
            x for x in data
            if int(x[6]) + 1 <= now_ms
        ]

        target = [
            i for i, x in enumerate(closed)
            if int(x[0]) == target_open
        ]

        if not target:
            raise RuntimeError("target candle missing")

        history = closed[:target[0] + 1]

        if len(history) < 60:
            raise RuntimeError("history < 60")

        closes = [
            D(str(x[4]))
            for x in history
        ]

        s = signals(closes)

        all_signals.extend([
            (symbol, "SMA20_50", s[0]),
            (symbol, "EMA12_26", s[1]),
            (symbol, "RSI14", s[2]),
        ])

        print(
            "KLINE PASS:",
            symbol,
            "|",
            s[0],
            s[1],
            s[2],
        )

    except Exception as e:
        errors.append((symbol, str(e)))


if errors:
    print("")
    print("KLINE ERRORS:")

    for e in errors:
        print(e)

    raise SystemExit(1)


if len(all_signals) != 63:
    raise RuntimeError(
        f"Expected 63 signals, got {len(all_signals)}"
    )


print("")
print("KLINE SYMBOLS : 21/21 PASS")
print("SIGNAL ROWS   : 63/63 PASS")


r = requests.get(
    BOOK,
    timeout=15,
)

r.raise_for_status()

raw = r.json()

wanted = set(universe)
books = {}

for x in raw:

    symbol = x.get("symbol")

    if symbol not in wanted:
        continue

    bid = D(str(x["bidPrice"]))
    ask = D(str(x["askPrice"]))

    if bid <= 0 or ask <= 0:
        raise RuntimeError(
            f"Invalid book: {symbol}"
        )

    if ask < bid:
        raise RuntimeError(
            f"Crossed book: {symbol}"
        )

    books[symbol] = (bid, ask)


missing = wanted - set(books)

if missing:
    raise RuntimeError(
        "Missing book symbols: "
        + ",".join(sorted(missing))
    )


print("BOOK SNAPSHOT  : 21/21 PASS")

print("")
print("=== NON-NONE SIGNALS ===")

non_none = [
    x for x in all_signals
    if x[2] != "NONE"
]

if non_none:
    for symbol, strategy, sig in non_none:
        print(
            strategy,
            symbol,
            sig,
        )
else:
    print("NONE")


print("")
print("=" * 72)
print("V3 LIVE MARKET PREFLIGHT : PASS")
print("NO STATE WRITE")
print("NO PAPER TRADE")
print("NO REAL ORDER")
print("=" * 72)
