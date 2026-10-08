import json
import time
import requests
from pathlib import Path
from decimal import Decimal

D = Decimal
ROOT = Path.cwd()

STATE = ROOT / "multistrategy_live_state_v3.json"

state = json.loads(
    STATE.read_text(encoding="utf-8-sig")
)

universe = state["universe"]

KLINE = "https://api.binance.me/api/v1/klines"
BOOK = "https://api.binance.me/api/v3/ticker/bookTicker"

HOUR = 3_600_000

now_ms = int(time.time() * 1000)
target_open = (now_ms // HOUR - 1) * HOUR
target_close = target_open + HOUR


def get_json(url, params=None):
    delays = (1, 2, 4, 8)
    last = None

    for attempt in range(5):
        try:
            r = requests.get(
                url,
                params=params,
                timeout=20,
                headers={
                    "User-Agent":
                        "PortfolioAI-Paper-V3-Preflight/1.0"
                },
            )

            r.raise_for_status()

            return r.json()

        except Exception as exc:
            last = exc

            print(
                "RETRY",
                attempt + 1,
                ":",
                type(exc).__name__,
                str(exc),
            )

            if attempt < 4:
                time.sleep(delays[attempt])

    raise RuntimeError(
        f"API failed after 5 attempts: {last}"
    )


def ema(values, n):
    alpha = D(2) / D(n + 1)
    result = values[0]

    for value in values[1:]:
        result = (
            alpha * value
            + (D(1) - alpha) * result
        )

    return result


def rsi(values, n=14):
    gains = D(0)
    losses = D(0)

    for i in range(
        len(values) - n,
        len(values),
    ):
        change = (
            values[i]
            - values[i - 1]
        )

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


def calc(closes):
    p20 = sum(closes[-21:-1]) / D(20)
    p50 = sum(closes[-51:-1]) / D(50)

    c20 = sum(closes[-20:]) / D(20)
    c50 = sum(closes[-50:]) / D(50)

    sma = "NONE"

    if p20 <= p50 and c20 > c50:
        sma = "BUY"

    elif p20 >= p50 and c20 < c50:
        sma = "SELL"

    previous = closes[:-1]

    pe12 = ema(previous, 12)
    pe26 = ema(previous, 26)

    ce12 = ema(closes, 12)
    ce26 = ema(closes, 26)

    em = "NONE"

    if pe12 <= pe26 and ce12 > ce26:
        em = "BUY"

    elif pe12 >= pe26 and ce12 < ce26:
        em = "SELL"

    previous_rsi = rsi(
        closes[:-1],
        14,
    )

    current_rsi = rsi(
        closes,
        14,
    )

    rs = "NONE"

    if (
        previous_rsi <= D(30)
        and current_rsi > D(30)
    ):
        rs = "BUY"

    elif (
        previous_rsi >= D(70)
        and current_rsi < D(70)
    ):
        rs = "SELL"

    return sma, em, rs


print("")
print("TARGET OPEN :", target_open)
print("TARGET CLOSE:", target_close)
print("")

rows = []

for symbol in universe:

    data = get_json(
        KLINE,
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

    index = None

    for i, candle in enumerate(closed):
        if int(candle[0]) == target_open:
            index = i
            break

    if index is None:
        raise RuntimeError(
            f"{symbol}: target candle missing"
        )

    history = closed[:index + 1]

    if len(history) < 60:
        raise RuntimeError(
            f"{symbol}: history < 60"
        )

    closes = [
        D(str(x[4]))
        for x in history
    ]

    result = calc(closes)

    rows.extend([
        (symbol, "SMA20_50", result[0]),
        (symbol, "EMA12_26", result[1]),
        (symbol, "RSI14", result[2]),
    ])

    print(
        "PASS",
        symbol,
        "|",
        result[0],
        result[1],
        result[2],
    )


if len(rows) != 63:
    raise RuntimeError(
        f"Signal count {len(rows)} != 63"
    )

print("")
print("KLINES       : 21/21 PASS")
print("SIGNAL ROWS  : 63/63 PASS")

# ------------------------------------------------------------
# Common book snapshot
# ------------------------------------------------------------

book_data = get_json(BOOK)

wanted = set(universe)
books = {}

for row in book_data:

    symbol = row.get("symbol")

    if symbol not in wanted:
        continue

    bid = D(str(row["bidPrice"]))
    ask = D(str(row["askPrice"]))

    if bid <= 0:
        raise RuntimeError(
            f"{symbol}: invalid bid"
        )

    if ask <= 0:
        raise RuntimeError(
            f"{symbol}: invalid ask"
        )

    if ask < bid:
        raise RuntimeError(
            f"{symbol}: ask < bid"
        )

    books[symbol] = (
        bid,
        ask,
    )


missing = wanted - set(books)

if missing:
    raise RuntimeError(
        "BOOK MISSING: "
        + ",".join(sorted(missing))
    )


print("BOOK SNAPSHOT: 21/21 PASS")

print("")
print("=== NON-NONE ===")

non_none = [
    x for x in rows
    if x[2] != "NONE"
]

if not non_none:
    print("NONE")

else:
    for symbol, strategy, signal in non_none:
        print(
            strategy,
            symbol,
            signal,
        )


print("")
print("=" * 72)
print("V3 LIVE READ-ONLY TEST : PASS")
print("21 SYMBOLS             : PASS")
print("63 SIGNALS             : PASS")
print("COMMON BOOK SNAPSHOT   : PASS")
print("STATE WRITE            : NO")
print("PAPER TRADE            : NO")
print("REAL ORDER             : NO")
print("=" * 72)
