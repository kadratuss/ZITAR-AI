import csv
import json
import time
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path

import requests

getcontext().prec = 28

ROOT = Path(__file__).resolve().parent
SIGNALS = ROOT / "forward_signals_v2.csv"
STATE   = ROOT / "forward_paper_state_v1.json"
TRADES  = ROOT / "forward_paper_trades_v1.csv"

API = "https://api.binance.me/api/v1/klines"
HOUR = 3_600_000

D = Decimal
QTY_STEP = D("0.00000001")

def dt_ms(text):
    return int(
        datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000
    )

def iso_ms(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()

def dec(x):
    return D(str(x))

def fetch_execution_candle(symbol, open_ms):
    last_error = None

    for attempt in range(3):
        try:
            r = requests.get(
                API,
                params={
                    "symbol": symbol,
                    "interval": "1h",
                    "startTime": open_ms,
                    "limit": 2,
                },
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()

            for k in data:
                if int(k[0]) == open_ms:
                    return dec(k[1])

            raise RuntimeError("Execution mumu bulunamadi")

        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(2)

    raise RuntimeError(f"{symbol}: {last_error}")

def append_trade(row):
    with TRADES.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writerow(row)

if not STATE.exists():
    raise SystemExit("forward_paper_state_v1.json bulunamadi.")

if not SIGNALS.exists():
    raise SystemExit("forward_signals_v2.csv bulunamadi.")

state = json.loads(STATE.read_text(encoding="utf-8"))

cash = dec(state["cash_try"])
budget = dec(state["order_budget_try"])
fee_rate = dec(state["fee_rate"])
slip = dec(state["slippage_rate"])
max_positions = int(state["max_positions"])
positions = state["positions"]

start_after = dt_ms(state["execution_start_after_candle_close_utc"])

processed = set(state.get("processed_signal_candles", []))

with SIGNALS.open("r", newline="", encoding="utf-8") as f:
    all_signals = list(csv.DictReader(f))

# Yalnizca paper freeze sinirindan SONRA kapanan sinyal mumlari.
eligible = [
    r for r in all_signals
    if dt_ms(r["candle_close_utc"]) > start_after
]

groups = {}

for r in eligible:
    key = r["candle_close_utc"]
    groups.setdefault(key, []).append(r)

now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

executed_count = 0

print("")
print("=== FORWARD PAPER EXECUTOR V1 ===")
print("Nakit       :", cash)
print("Pozisyon    :", len(positions))
print("Yeni gruplar:", len(groups))
print("")

for close_iso in sorted(groups.keys(), key=dt_ms):

    if close_iso in processed:
        continue

    signal_close_ms = dt_ms(close_iso)

    # Backtest kurali:
    # sinyal mumunun kapanisi = sonraki execution mumunun acilisi.
    execution_open_ms = signal_close_ms

    # Execution mumunun OPEN'i borsada olusmus olmali.
    if now_ms < execution_open_ms + 60_000:
        print(close_iso, "-> execution open icin henuz erken")
        continue

    rows = groups[close_iso]

    sells = sorted(
        [r for r in rows if r["signal"] == "SELL"],
        key=lambda x: x["symbol"]
    )

    buys = sorted(
        [r for r in rows if r["signal"] == "BUY"],
        key=lambda x: x["symbol"]
    )

    print("Sinyal kapanisi:", close_iso)
    print("SELL:", [r["symbol"] for r in sells])
    print("BUY :", [r["symbol"] for r in buys])

    group_failed = False

    # --------------------------------------------------
    # SELL FIRST
    # --------------------------------------------------
    for r in sells:
        symbol = r["symbol"]

        if symbol not in positions:
            print(symbol, "SELL -> pozisyon yok, islem yok")
            continue

        try:
            market_open = fetch_execution_candle(
                symbol, execution_open_ms
            )
        except Exception as e:
            print("HATA:", e)
            group_failed = True
            break

        fill = market_open * (D("1") - slip)

        qty = dec(positions[symbol]["quantity"])

        gross = qty * fill
        fee = gross * fee_rate
        received = gross - fee

        entry_cost = dec(positions[symbol]["total_cost_try"])
        pnl = received - entry_cost

        cash += received

        row = {
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "signal_candle_open_utc": r["candle_open_utc"],
            "signal_candle_close_utc": r["candle_close_utc"],
            "execution_candle_open_utc": iso_ms(execution_open_ms),
            "symbol": symbol,
            "side": "SELL",
            "signal": "SELL",
            "market_open_price": str(market_open),
            "modeled_fill_price": str(fill),
            "quantity": str(qty),
            "gross_try": str(gross),
            "fee_try": str(fee),
            "cash_after_try": str(cash),
            "realized_pnl_try": str(pnl),
            "status": "FORWARD_PAPER_MODELED_FILL",
        }

        append_trade(row)

        del positions[symbol]

        state["realized_pnl_try"] = str(
            dec(state["realized_pnl_try"]) + pnl
        )

        state["trade_count"] = int(state["trade_count"]) + 1
        executed_count += 1

        print(
            symbol,
            "SELL",
            "open=", market_open,
            "fill=", fill,
            "PnL=", pnl
        )

    if group_failed:
        break

    # --------------------------------------------------
    # BUY AFTER SELLS
    # --------------------------------------------------
    for r in buys:
        symbol = r["symbol"]

        if symbol in positions:
            print(symbol, "BUY -> zaten pozisyon var")
            continue

        if len(positions) >= max_positions:
            print(symbol, "BUY -> kapasite dolu")
            continue

        if cash < budget:
            print(symbol, "BUY -> nakit yetersiz")
            continue

        try:
            market_open = fetch_execution_candle(
                symbol, execution_open_ms
            )
        except Exception as e:
            print("HATA:", e)
            group_failed = True
            break

        fill = market_open * (D("1") + slip)

        # 1000 TRY toplam butce:
        # qty * fill + fee = budget
        qty = (
            budget /
            ((D("1") + fee_rate) * fill)
        ).quantize(QTY_STEP)

        gross = qty * fill
        fee = gross * fee_rate
        total_cost = gross + fee

        if total_cost > cash:
            print(symbol, "BUY -> hesaplanan maliyet nakdi asti")
            continue

        cash -= total_cost

        positions[symbol] = {
            "quantity": str(qty),
            "entry_market_open_price": str(market_open),
            "entry_fill_price": str(fill),
            "total_cost_try": str(total_cost),
            "signal_candle_close_utc": r["candle_close_utc"],
            "execution_candle_open_utc": iso_ms(execution_open_ms),
        }

        row = {
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
            "signal_candle_open_utc": r["candle_open_utc"],
            "signal_candle_close_utc": r["candle_close_utc"],
            "execution_candle_open_utc": iso_ms(execution_open_ms),
            "symbol": symbol,
            "side": "BUY",
            "signal": "BUY",
            "market_open_price": str(market_open),
            "modeled_fill_price": str(fill),
            "quantity": str(qty),
            "gross_try": str(gross),
            "fee_try": str(fee),
            "cash_after_try": str(cash),
            "realized_pnl_try": "",
            "status": "FORWARD_PAPER_MODELED_FILL",
        }

        append_trade(row)

        state["trade_count"] = int(state["trade_count"]) + 1
        executed_count += 1

        print(
            symbol,
            "BUY",
            "open=", market_open,
            "fill=", fill,
            "qty=", qty,
            "cost=", total_cost
        )

    if group_failed:
        break

    # Grup ancak tamamen basarili olduktan sonra processed.
    processed.add(close_iso)

state["cash_try"] = str(cash)
state["positions"] = positions
state["processed_signal_candles"] = sorted(processed, key=dt_ms)
state["last_executor_run_utc"] = datetime.now(timezone.utc).isoformat()

STATE.write_text(
    json.dumps(state, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print("")
print("=== DURUM ===")
print("Yeni paper islem :", executed_count)
print("Nakit            :", cash)
print("Acik pozisyon    :", len(positions))
print("Gerceklesen PnL  :", state["realized_pnl_try"])
print("Toplam trade     :", state["trade_count"])

if positions:
    print("Pozisyonlar      :", ", ".join(sorted(positions)))
else:
    print("Pozisyonlar      : YOK")

print("")
print("GERCEK EMIR GONDERILMEDI.")
