import csv
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "forward_test_manifest_v1.json"
SOURCE = ROOT / "portfolio_backtest_v1.py"
OUT = ROOT / "forward_signals_v2.csv"

API = "https://api.binance.me/api/v1/klines"
HOUR = 3_600_000

FIELDS = [
    "source_sha256",
    "freeze_utc",
    "observed_at_utc",
    "candle_open_utc",
    "candle_close_utc",
    "symbol",
    "signal",
    "close_price",
    "sma20",
    "sma50",
    "source",
    "status",
]

def iso_ms(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def fetch_klines(symbol, limit=60):
    last_error = None

    for attempt in range(3):
        try:
            r = requests.get(
                API,
                params={
                    "symbol": symbol,
                    "interval": "1h",
                    "limit": limit,
                },
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()

            if not isinstance(data, list):
                raise RuntimeError(f"Beklenmeyen API cevabi: {data}")

            return data

        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(2)

    raise RuntimeError(f"{symbol} API hatasi: {last_error}")

def signal_from_closes(closes):
    # portfolio_backtest_v1.py ile ayni SMA20/50 crossover mantigi.
    if len(closes) < 51:
        raise RuntimeError("SMA icin en az 51 kapanis gerekli")

    prev20 = sum(closes[-21:-1]) / Decimal(20)
    prev50 = sum(closes[-51:-1]) / Decimal(50)

    curr20 = sum(closes[-20:]) / Decimal(20)
    curr50 = sum(closes[-50:]) / Decimal(50)

    if prev20 <= prev50 and curr20 > curr50:
        action = "BUY"
    elif prev20 >= prev50 and curr20 < curr50:
        action = "SELL"
    else:
        action = "NONE"

    return action, curr20, curr50

if not MANIFEST.exists():
    raise SystemExit("Manifest bulunamadi.")

if not SOURCE.exists():
    raise SystemExit("Dondurulmus kaynak dosya bulunamadi.")

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

expected_hash = manifest.get("source_sha256")
actual_hash = sha256(SOURCE)

if expected_hash != actual_hash:
    raise SystemExit(
        "DURDURULDU: portfolio_backtest_v1.py SHA256 manifest ile ayni degil."
    )

symbols = manifest.get("universe")
if not symbols:
    raise SystemExit("Manifest universe bos.")

freeze_text = manifest.get("frozen_at_utc")
if not freeze_text:
    raise SystemExit("Manifest freeze zamani yok.")

freeze_dt = datetime.fromisoformat(freeze_text.replace("Z", "+00:00"))
freeze_ms = int(freeze_dt.timestamp() * 1000)

now = datetime.now(timezone.utc)
now_ms = int(now.timestamp() * 1000)

# En son TAM kapanmis 1h mum.
target_open = (now_ms // HOUR - 1) * HOUR
target_close = target_open + HOUR

if target_open < freeze_ms:
    raise SystemExit("Freeze sonrasinda tam forward mum henuz yok.")

# Ayni saat tekrar calisirsa duplicate yazma.
existing = set()

if OUT.exists():
    with OUT.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing.add((row["candle_open_utc"], row["symbol"]))

rows_to_write = []
errors = []

print("")
print("=== FORWARD OBSERVER V2 ===")
print("Kaynak     : Binance TR API")
print("Hedef mum  :", iso_ms(target_open), "->", iso_ms(target_close))
print("Sembol     :", len(symbols))
print("")

for symbol in symbols:
    key = (iso_ms(target_open), symbol)

    if key in existing:
        print(f"{symbol:<12} ZATEN KAYITLI")
        continue

    try:
        raw = fetch_klines(symbol, 60)

        closed = []

        for k in raw:
            open_ms = int(k[0])
            close_ms = int(k[6]) + 1

            # Sadece tamamen kapanmis mumlar.
            if close_ms <= now_ms:
                closed.append(k)

        target_index = None

        for i, k in enumerate(closed):
            if int(k[0]) == target_open:
                target_index = i
                break

        if target_index is None:
            raise RuntimeError("Hedef 1h mum Binance TR cevabinda yok")

        history = closed[:target_index + 1]

        if len(history) < 51:
            raise RuntimeError(
                f"Yetersiz 1h gecmis: {len(history)} mum"
            )

        last51 = history[-51:]
        closes = [Decimal(str(k[4])) for k in last51]

        action, sma20, sma50 = signal_from_closes(closes)
        close_price = Decimal(str(last51[-1][4]))

        row = {
            "source_sha256": actual_hash,
            "freeze_utc": freeze_text,
            "observed_at_utc": datetime.now(timezone.utc).isoformat(),
            "candle_open_utc": iso_ms(target_open),
            "candle_close_utc": iso_ms(target_close),
            "symbol": symbol,
            "signal": action,
            "close_price": str(close_price),
            "sma20": str(sma20),
            "sma50": str(sma50),
            "source": "BINANCE_TR_API",
            "status": "SIGNAL_ONLY_NO_FILL",
        }

        rows_to_write.append(row)

        print(
            f"{symbol:<12} {action:<4} "
            f"close={close_price}"
        )

    except Exception as e:
        errors.append((symbol, str(e)))
        print(f"{symbol:<12} HATA: {e}")

if rows_to_write:
    new_file = not OUT.exists()

    with OUT.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)

        if new_file:
            writer.writeheader()

        writer.writerows(rows_to_write)

print("")
print("Yeni kayit :", len(rows_to_write))
print("Hata       :", len(errors))
print("CSV        :", OUT)

if errors:
    print("")
    print("HATALAR:")
    for symbol, error in errors:
        print(symbol, "->", error)
    sys.exit(1)

print("")
print("OK - SADECE SINYAL KAYDI. EMIR YOK. PAPER PORTFOY YOK.")
