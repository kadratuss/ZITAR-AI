import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SIGNALS = ROOT / "forward_signals_v2.csv"
STATE   = ROOT / "forward_paper_state_v1.json"
TRADES  = ROOT / "forward_paper_trades_v1.csv"

INITIAL_CASH = Decimal("10000")
ORDER_BUDGET = Decimal("1000")
MAX_POSITIONS = 10
FEE = Decimal("0.001")
SLIP = Decimal("0.001")

if not SIGNALS.exists():
    raise SystemExit("forward_signals_v2.csv bulunamadi.")

if STATE.exists():
    raise SystemExit(
        "DURDURULDU: forward_paper_state_v1.json zaten var. "
        "Mevcut forward paper deneyi sifirlanmadi."
    )

with SIGNALS.open("r", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

if not rows:
    raise SystemExit("Forward signal CSV bos.")

# Mevcut sinyaller sadece gecmis gozlem olarak kalacak.
# Paper execution bunlardan SONRA gelecek yeni mumlardan baslayacak.
latest_close = max(r["candle_close_utc"] for r in rows)

state = {
    "experiment": "PortfolioAI forward paper execution v1",
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "status": "ACTIVE_FORWARD_ONLY",
    "signal_source": "forward_signals_v2.csv",
    "execution_start_after_candle_close_utc": latest_close,
    "initial_cash_try": str(INITIAL_CASH),
    "cash_try": str(INITIAL_CASH),
    "order_budget_try": str(ORDER_BUDGET),
    "max_positions": MAX_POSITIONS,
    "fee_rate": str(FEE),
    "slippage_rate": str(SLIP),
    "positions": {},
    "realized_pnl_try": "0",
    "trade_count": 0,
    "processed_signal_candles": [],
    "rules": {
        "signal": "Frozen SMA20/50 crossover from forward_signals_v2.csv",
        "execution": "Next 1h candle open",
        "buy_price_model": "next_open * (1 + 0.001 slippage)",
        "sell_price_model": "next_open * (1 - 0.001 slippage)",
        "fee": "0.1% each side",
        "order_budget": "1000 TRY including buy fee",
        "max_positions": 10,
        "sell_before_buy": True,
        "buy_priority": "alphabetical symbol order",
        "real_money": False,
        "retroactive_fills": False
    }
}

STATE.write_text(
    json.dumps(state, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

trade_fields = [
    "executed_at_utc",
    "signal_candle_open_utc",
    "signal_candle_close_utc",
    "execution_candle_open_utc",
    "symbol",
    "side",
    "signal",
    "market_open_price",
    "modeled_fill_price",
    "quantity",
    "gross_try",
    "fee_try",
    "cash_after_try",
    "realized_pnl_try",
    "status"
]

with TRADES.open("x", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=trade_fields)
    writer.writeheader()

print("")
print("=== FORWARD PAPER PORTFOY V1 DONDURULDU ===")
print("Baslangic nakit :", state["cash_try"], "TRY")
print("Emir butcesi    :", state["order_budget_try"], "TRY")
print("Max pozisyon    :", state["max_positions"])
print("Komisyon        :", state["fee_rate"])
print("Slippage        :", state["slippage_rate"])
print("Baslangic siniri:", state["execution_start_after_candle_close_utc"])
print("")
print("ONEMLI:")
print("Mevcut eski BUY/SELL sinyalleri geriye donuk doldurulmadi.")
print("Paper islemler sadece bundan sonra gelecek yeni forward sinyallerinden baslayacak.")
print("GERCEK EMIR YOK.")
print("ESKI PAPER AJANA DOKUNULMADI.")
print("V6'YA DOKUNULMADI.")
print("MEVCUT DB'LERE DOKUNULMADI.")
