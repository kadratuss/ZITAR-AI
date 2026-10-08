import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STATE = ROOT / "multistrategy_live_state_v1.json"
SIGNALS = ROOT / "multistrategy_live_signals_v1.csv"
TRADES = ROOT / "multistrategy_live_trades_v1.csv"

if STATE.exists():
    raise SystemExit(
        "DURDURULDU: multistrategy_live_state_v1.json zaten var. "
        "Mevcut deney sifirlanmadi."
    )

now = datetime.now(timezone.utc)

strategies = {
    "SMA20_50": {
        "cash_try": "10000",
        "initial_cash_try": "10000",
        "positions": {},
        "realized_pnl_try": "0",
        "trade_count": 0
    },
    "EMA12_26": {
        "cash_try": "10000",
        "initial_cash_try": "10000",
        "positions": {},
        "realized_pnl_try": "0",
        "trade_count": 0
    },
    "RSI14": {
        "cash_try": "10000",
        "initial_cash_try": "10000",
        "positions": {},
        "realized_pnl_try": "0",
        "trade_count": 0
    }
}

state = {
    "experiment": "PortfolioAI MultiStrategy Live Paper v1",
    "created_at_utc": now.isoformat(),
    "status": "FROZEN_PROSPECTIVE",
    "forward_only": True,
    "retroactive_signals": False,
    "retroactive_fills": False,

    "universe": [
        "AVAXTRY","BTCTRY","COTITRY","DOGETRY","ENATRY",
        "ETHTRY","FORMTRY","GTRY","MINATRY","MUBARAKTRY",
        "NEARTRY","ONETRY","PENGUTRY","PEPETRY","PHATRY",
        "SAGATRY","SOLTRY","TRUMPTRY","TSTTRY","USDTTRY",
        "XRPTRY"
    ],

    "interval": "1h",

    "rules": {
        "signal_data": "Binance TR directly observed closed 1h candles",
        "execution": "next 1h candle OPEN",
        "fee_rate": "0.001",
        "slippage_rate": "0.001",
        "order_budget_try": "1000",
        "max_positions_per_strategy": 10,
        "sell_before_buy": True,
        "buy_priority": "alphabetical",
        "real_money": False
    },

    "strategy_definitions": {
        "SMA20_50": "SMA20/SMA50 crossover",
        "EMA12_26": "EMA12/EMA26 crossover",
        "RSI14": "BUY when RSI14 crosses upward through 30; SELL when it crosses downward through 70"
    },

    "strategies": strategies,
    "processed_candle_closes": []
}

STATE.write_text(
    json.dumps(state, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

signal_header = (
    "observed_at_utc,candle_open_utc,candle_close_utc,"
    "symbol,strategy,signal,close_price,indicator_1,"
    "indicator_2,status\n"
)

trade_header = (
    "executed_at_utc,signal_candle_close_utc,"
    "execution_candle_open_utc,strategy,symbol,side,"
    "market_open_price,modeled_fill_price,quantity,"
    "gross_try,fee_try,cash_after_try,realized_pnl_try,status\n"
)

SIGNALS.write_text(signal_header, encoding="utf-8")
TRADES.write_text(trade_header, encoding="utf-8")

print("")
print("=" * 72)
print("MULTISTRATEGY LIVE PAPER V1 - FROZEN")
print("=" * 72)
print("Freeze UTC       :", state["created_at_utc"])
print("Strategies       : SMA20/50 + EMA12/26 + RSI14")
print("Accounts         : 3 x 10000 TRY")
print("Order budget     : 1000 TRY")
print("Max positions    : 10 / strategy")
print("Fee              : 0.1%")
print("Modeled slippage : 0.1%")
print("Interval         : 1h")
print("Universe         : 21")
print("")
print("GECMIS SINYAL YOK.")
print("GERIYE DONUK FILL YOK.")
print("GERCEK PARA YOK.")
print("GERCEK EMIR YOK.")
print("")
print("Mevcut SMA forward deneyi : DOKUNULMADI")
print("Eski paper ajan           : DOKUNULMADI")
print("v6                        : DOKUNULMADI")
