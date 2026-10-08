from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal as D
import csv
import hashlib
import importlib.util
import json
import sqlite3

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "forward_test_manifest_v1.json"
SOURCE = ROOT / "portfolio_backtest_v1.py"
DB = ROOT / "long_history.db"
LOG = ROOT / "forward_signals_v1.csv"
HOUR = 3_600_000

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def stamp(ms):
    return datetime.fromtimestamp(
        ms / 1000, timezone.utc
    ).isoformat()

if not MANIFEST.is_file() or not SOURCE.is_file() or not DB.is_file():
    raise SystemExit("Manifest, backtest kodu veya arsiv eksik.")

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
if sha256(SOURCE) != manifest["source_sha256"]:
    raise SystemExit(
        "Backtest kodunun SHA256 degeri degismis. "
        "Dondurulmus deney korunuyor; gozlem yapilmadi."
    )

spec = importlib.util.spec_from_file_location("frozen_strategy", SOURCE)
strategy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strategy)

now = datetime.now(timezone.utc)
now_ms = int(now.timestamp() * 1000)
freeze_ms = int(
    datetime.fromisoformat(
        manifest["frozen_at_utc"]
    ).timestamp() * 1000
)

# Yalnizca tamamen kapanmis son saatlik mum.
# Mumun acilis zamani + 1 saat <= simdiki zaman.
target = (now_ms // HOUR - 1) * HOUR
closed_at = target + HOUR

if closed_at <= freeze_ms:
    raise SystemExit("Dondurma sonrasinda kapanmis yeni mum henuz yok.")

# Eski mumlari sonradan yakalayip ileriye donuk kayit gibi
# gostermemek icin kapanistan en fazla 10 dakika sonra gozlem.
delay = now_ms - closed_at
if delay > 10 * 60 * 1000:
    raise SystemExit(
        "Son mumun kapanisinin uzerinden 10 dakikadan fazla "
        "gecmis. Gecikmis sinyal kaydedilmedi. "
        "Bir sonraki saat kapanisindan sonraki ilk 10 "
        "dakikada tekrar calistir."
    )

universe = manifest["universe"]
observations = []

with sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True) as db:
    for symbol in universe:
        rows = strategy.load(db, symbol)
        index = {r[0]: i for i, r in enumerate(rows)}

        if target not in index:
            raise SystemExit(
                f"{symbol}: {stamp(target)} mumu arsivde yok. "
                "Hicbir sinyal kaydedilmedi. "
                "Veri guncelleyicisinin bu mumu almasini bekle."
            )

        i = index[target]
        if i < 50:
            raise SystemExit(f"{symbol}: SMA icin gecmis yetersiz.")

        # Son 51 mumun kesintisiz oldugunu da kontrol et.
        window = rows[i-50:i+1]
        if len(window) != 51 or any(
            window[j][0] - window[j-1][0] != HOUR
            for j in range(1, len(window))
        ):
            raise SystemExit(
                f"{symbol}: SMA penceresinde bosluk var. "
                "Hicbir sinyal kaydedilmedi."
            )

        action = strategy.signal(rows, i) or "NONE"
        observations.append([
            manifest["source_sha256"],
            manifest["frozen_at_utc"],
            stamp(target),
            stamp(closed_at),
            now.isoformat(),
            symbol,
            action,
            str(rows[i][2]),
            "SIGNAL_ONLY_NO_FILL"
        ])

header = [
    "strategy_sha256", "frozen_at_utc",
    "candle_open_utc", "candle_closed_utc",
    "observed_at_utc", "symbol", "signal",
    "candle_close_price", "status"
]

# Tekrarlanan calistirmada ayni saati yeniden yazma.
existing = set()
if LOG.exists():
    with LOG.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != header:
            raise SystemExit("Mevcut sinyal gunlugunun sutunlari farkli.")
        existing = {
            (r["candle_open_utc"], r["symbol"])
            for r in reader
        }

new_rows = [
    row for row in observations
    if (row[2], row[5]) not in existing
]

if not new_rows:
    print("Bu saatin 21 paritesi daha once kaydedilmis; tekrar yazilmadi.")
else:
    # Dosya ilk kez olusturuluyorsa uzerine yazmadan olustur.
    if not LOG.exists():
        with LOG.open("x", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(header)
    with LOG.open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(new_rows)

print("PORTFOLIOAI | ILERIYE DONUK SINYAL GOZLEMI V1")
print("Mum kapanisi UTC:", stamp(closed_at))
print("Gozlem UTC:", now.isoformat())
print("Yeni kayit:", len(new_rows))
print("BUY:", sum(r[6] == "BUY" for r in new_rows))
print("SELL:", sum(r[6] == "SELL" for r in new_rows))
for r in new_rows:
    if r[6] != "NONE":
        print(f"  {r[5]}: {r[6]} | kapanis={r[7]}")
print("Gunluk:", LOG.name)
print("Emir veya gerceklesme kaydi YOK; veritabanina yazilmadi.")
