import json
import requests
import time
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 28
D = Decimal

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "forward_test_manifest_v1.json"
API = "https://api.binance.me/api/v1/klines"

def fetch(symbol, limit=250):
    last = None
    for n in range(3):
        try:
            r = requests.get(
                API,
                params={"symbol": symbol, "interval": "1h", "limit": limit},
                timeout=15
            )
            r.raise_for_status()
            data = r.json()
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

            # Yalniz tamamen kapanmis mumlar
            return [
                x for x in data
                if int(x[6]) + 1 <= now_ms
            ]
        except Exception as e:
            last = e
            if n < 2:
                time.sleep(2)
    raise RuntimeError(last)

def sma(values, n):
    return sum(values[-n:]) / D(n)

def ema_series(values, n):
    alpha = D(2) / D(n + 1)
    out = [values[0]]
    for x in values[1:]:
        out.append(alpha * x + (D(1) - alpha) * out[-1])
    return out

def rsi(values, n=14):
    if len(values) < n + 1:
        return None

    gains = D(0)
    losses = D(0)

    for i in range(len(values) - n, len(values)):
        ch = values[i] - values[i-1]
        if ch > 0:
            gains += ch
        elif ch < 0:
            losses -= ch

    avg_gain = gains / D(n)
    avg_loss = losses / D(n)

    if avg_loss == 0:
        return D(100)

    rs = avg_gain / avg_loss
    return D(100) - (D(100) / (D(1) + rs))

def sma_signal(closes):
    if len(closes) < 51:
        return "NONE"

    p20 = sum(closes[-21:-1]) / D(20)
    p50 = sum(closes[-51:-1]) / D(50)

    c20 = sum(closes[-20:]) / D(20)
    c50 = sum(closes[-50:]) / D(50)

    if p20 <= p50 and c20 > c50:
        return "BUY"
    if p20 >= p50 and c20 < c50:
        return "SELL"
    return "NONE"

def ema_signal(closes):
    if len(closes) < 60:
        return "NONE"

    prev = closes[:-1]

    e12_prev = ema_series(prev, 12)[-1]
    e26_prev = ema_series(prev, 26)[-1]

    e12_now = ema_series(closes, 12)[-1]
    e26_now = ema_series(closes, 26)[-1]

    if e12_prev <= e26_prev and e12_now > e26_now:
        return "BUY"
    if e12_prev >= e26_prev and e12_now < e26_now:
        return "SELL"
    return "NONE"

def rsi_signal(closes):
    if len(closes) < 17:
        return "NONE", None

    prev_rsi = rsi(closes[:-1], 14)
    now_rsi = rsi(closes, 14)

    # Mean-reversion:
    # oversold bolgeden yukari cikis -> BUY
    # overbought bolgeden asagi inis -> SELL
    if prev_rsi is not None and now_rsi is not None:
        if prev_rsi <= D(30) and now_rsi > D(30):
            return "BUY", now_rsi
        if prev_rsi >= D(70) and now_rsi < D(70):
            return "SELL", now_rsi

    return "NONE", now_rsi

if not MANIFEST.exists():
    raise SystemExit("Manifest bulunamadi.")

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
symbols = manifest["universe"]

print("")
print("=" * 76)
print("PORTFOLIOAI STRATEGY ENGINE V1")
print("UTC:", datetime.now(timezone.utc).isoformat())
print("=" * 76)
print("")
print("SMA20/50  : trend crossover")
print("EMA12/26  : hizli trend crossover")
print("RSI14     : mean-reversion 30/70")
print("Sembol    :", len(symbols))
print("Gercek emir: YOK")
print("")

summary = {
    "SMA": {"BUY": [], "SELL": []},
    "EMA": {"BUY": [], "SELL": []},
    "RSI": {"BUY": [], "SELL": []},
}

errors = []

for symbol in symbols:
    try:
        candles = fetch(symbol)
        closes = [D(str(x[4])) for x in candles]

        if len(closes) < 60:
            raise RuntimeError(f"Yetersiz veri: {len(closes)}")

        s1 = sma_signal(closes)
        s2 = ema_signal(closes)
        s3, rsi_now = rsi_signal(closes)

        if s1 != "NONE":
            summary["SMA"][s1].append(symbol)

        if s2 != "NONE":
            summary["EMA"][s2].append(symbol)

        if s3 != "NONE":
            summary["RSI"][s3].append(symbol)

        rsi_text = f"{rsi_now:.2f}" if rsi_now is not None else "-"

        print(
            f"{symbol:<12} "
            f"SMA={s1:<4} "
            f"EMA={s2:<4} "
            f"RSI={s3:<4} "
            f"RSI14={rsi_text}"
        )

    except Exception as e:
        errors.append((symbol, str(e)))
        print(f"{symbol:<12} HATA={e}")

print("")
print("=" * 76)
print("OZET")
print("=" * 76)

for name in ("SMA", "EMA", "RSI"):
    print(
        f"{name:<4} "
        f"BUY={len(summary[name]['BUY']):2d} "
        f"SELL={len(summary[name]['SELL']):2d} "
        f"BUY_LIST={','.join(summary[name]['BUY']) or '-'} "
        f"SELL_LIST={','.join(summary[name]['SELL']) or '-'}"
    )

print("")
print("Hata:", len(errors))
print("GERCEK EMIR GONDERILMEDI.")

if errors:
    raise SystemExit(1)
