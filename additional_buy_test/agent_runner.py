import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

import agent_lock
import agent_memory
import agent_portfolio


BASE_DIR = Path(__file__).resolve().parent
STATE_DB = BASE_DIR / "agent_runner_state.db"

BASE_URL = "https://api.binance.me"
SYMBOL = "BTCTRY"
INTERVAL = "1m"
POLL_SECONDS = 10
BUY_AMOUNT_TRY = Decimal("1000.00")
EXTRA_BUY_AMOUNT_TRY = Decimal("200.00")
EXTRA_BUY_DROP = Decimal("0.01")
MAX_EXTRA_BUYS = 3
MAX_EXTRA_SPEND_TRY = Decimal("500.00")

STRATEGY = "EMA_9_21_REGIME"
STRATEGY_VERSION = "0.2"


def now():
    return datetime.now(timezone.utc)


def init_state():
    with sqlite3.connect(STATE_DB) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS candle_runs (
                candle_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                signal TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            )
        """)


def get_run(candle_id):
    with sqlite3.connect(STATE_DB) as db:
        return db.execute(
            "SELECT status, signal FROM candle_runs WHERE candle_id = ?",
            (candle_id,),
        ).fetchone()


def reserve_run(candle_id, signal):
    with sqlite3.connect(STATE_DB) as db:
        db.execute(
            """
            INSERT INTO candle_runs
            (candle_id, status, signal, details, created_at)
            VALUES (?, 'PENDING', ?, NULL, ?)
            """,
            (candle_id, signal, now().isoformat()),
        )


def finish_run(candle_id, details):
    with sqlite3.connect(STATE_DB) as db:
        cursor = db.execute(
            """
            UPDATE candle_runs
            SET status = 'DONE', details = ?
            WHERE candle_id = ? AND status = 'PENDING'
            """,
            (str(details), candle_id),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                f"Tur tamamlanamadi: candle_id={candle_id}"
            )


def check_pending_runs():
    with sqlite3.connect(STATE_DB) as db:
        pending = db.execute(
            """
            SELECT candle_id, signal
            FROM candle_runs
            WHERE status = 'PENDING'
            ORDER BY candle_id
            """
        ).fetchall()

    if pending:
        raise RuntimeError(
            "Tamamlanmamis ajan turu var: "
            + str(pending)
            + ". Tekrar islem riskine karsi ajan durduruldu."
        )


def fetch_closed_candles():
    response = requests.get(
        BASE_URL + "/api/v3/klines",
        params={
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "limit": 100,
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, list):
        raise ValueError("Beklenmeyen mum verisi")

    now_ms = int(now().timestamp() * 1000)
    candles = []

    for item in data:
        if not isinstance(item, list) or len(item) < 7:
            raise ValueError("Eksik mum verisi")

        open_ms = int(item[0])
        close_ms = int(item[6])
        close_price = Decimal(str(item[4]))

        if close_price <= 0:
            raise ValueError("Gecersiz fiyat")

        # Devam eden mumu kullanma.
        if close_ms < now_ms:
            candles.append({
                "open_ms": open_ms,
                "close_ms": close_ms,
                "close": close_price,
            })

    if len(candles) < 30:
        raise ValueError("EMA icin yeterli kapanmis mum yok")

    # Son kapanmis mum 3 dakikadan eskiyse islem yapma.
    age_seconds = (
        now_ms - candles[-1]["close_ms"]
    ) / 1000

    if age_seconds > 180:
        raise ValueError("Piyasa verisi eski; islem yapilmadi")

    return candles


def ema(values, period):
    result = sum(values[:period]) / Decimal(period)
    multiplier = Decimal(2) / Decimal(period + 1)

    for value in values[period:]:
        result = (value - result) * multiplier + result

    return result



def extra_buy_decision(position, recent_trades, price, fast, slow):
    """Ek alis karari; belirsiz islem gecmisinde alis yapma."""
    if position is None or fast <= slow:
        return False, "Ek alis EMA kosulu saglanmadi"

    cycle = []
    for trade in recent_trades:
        if trade["symbol"] != SYMBOL:
            continue
        if trade["side"] == "SELL":
            break
        cycle.append(trade)

    cycle.reverse()
    if not cycle or cycle[0]["side"] != "BUY":
        return False, "Acik pozisyonun ilk alisi bulunamadi"

    if any(trade["side"] != "BUY" for trade in cycle):
        return False, "Pozisyon islem gecmisi belirsiz"

    last_price = Decimal(str(cycle[-1]["price"]))
    if last_price <= 0:
        return False, "Son alis fiyati gecersiz"

    if price > last_price * (Decimal("1") - EXTRA_BUY_DROP):
        return False, "Fiyat son alistan yuzde 1 dusmedi"

    extra_buys = cycle[1:]
    if len(extra_buys) >= MAX_EXTRA_BUYS:
        return False, "Ek alis adet siniri doldu"

    spent = sum(
        (
            Decimal(str(trade["gross"])) + Decimal(str(trade["fee"]))
            for trade in extra_buys
        ),
        Decimal("0"),
    )
    if spent + EXTRA_BUY_AMOUNT_TRY > MAX_EXTRA_SPEND_TRY:
        return False, "Ek alis butcesi doldu"

    return True, "Son alistan yuzde 1 dusus ve EMA kosulu saglandi"

def run_once():
    # Belirsiz tur varsa yeni islem yapma.
    check_pending_runs()

    candles = fetch_closed_candles()
    latest = candles[-1]
    candle_id = latest["close_ms"]

    if get_run(candle_id) is not None:
        return

    prices = [candle["close"] for candle in candles]
    fast = ema(prices, 9)
    slow = ema(prices, 21)
    price = latest["close"]

    portfolio = agent_portfolio.get_portfolio()
    position = next(
        (
            item for item in portfolio["positions"]
            if item["symbol"] == SYMBOL
        ),
        None,
    )

    if position is not None and fast < slow:
        signal = "SELL"
        reason = "EMA9 EMA21 altinda; pozisyon var"
    elif position is None and fast > slow:
        signal = "BUY"
        reason = "EMA9 EMA21 uzerinde; pozisyon yok"
    elif position is not None:
        eligible, reason = extra_buy_decision(
            position, portfolio["recent_trades"], price, fast, slow
        )
        signal = "EXTRA_BUY" if eligible else "HOLD"
    else:
        signal = "HOLD"
        reason = "Yeni islem kosulu yok"

    indicators = {
        "candle_close_ms": candle_id,
        "interval": INTERVAL,
        "price": str(price),
        "ema9": str(fast),
        "ema21": str(slow),
        "reason": reason,
        "position_open": position is not None,
    }

    # Islemden once mumu ayir.
    # Kesinti olursa ayni mum yeniden islenmesin.
    reserve_run(candle_id, signal)

    agent_memory.save_observation(SYMBOL, price)
    agent_memory.save_analysis(
        SYMBOL,
        STRATEGY,
        indicators,
        signal,
        strategy_version=STRATEGY_VERSION,
    )

    print(
        f"{now().isoformat()} | {SYMBOL} | {signal} | "
        f"Fiyat: {price} | EMA9: {fast:.2f} | "
        f"EMA21: {slow:.2f}",
        flush=True,
    )
    print("Neden:", reason, flush=True)

    result = {"signal": signal}

    if signal == "BUY":
        result = agent_portfolio.buy(
            SYMBOL,
            BUY_AMOUNT_TRY,
            price,
            candle_id,
        )
        print("SANAL ALIS:", result, flush=True)

    elif signal == "EXTRA_BUY":
        result = agent_portfolio.buy(
            SYMBOL,
            EXTRA_BUY_AMOUNT_TRY,
            price,
            candle_id,
        )
        print("SANAL EK ALIS:", result, flush=True)

    elif signal == "SELL":
        result = agent_portfolio.sell(
            SYMBOL,
            position["quantity"],
            price,
            candle_id,
        )
        print("SANAL SATIS:", result, flush=True)

        agent_memory.save_experience(
            trade_id=result["trade_id"],
            symbol=SYMBOL,
            strategy=STRATEGY,
            market_context=indicators,
            realized_pnl=result["realized_pnl"],
            strategy_version=STRATEGY_VERSION,
        )

    finish_run(candle_id, result)


def main():
    lock = agent_lock.AgentLock()

    try:
        lock.acquire()
    except agent_lock.AgentAlreadyRunning as error:
        print(error, flush=True)
        return

    try:
        agent_portfolio.init_database()
        agent_memory.init_database()
        init_state()

        # Baslamadan once eski belirsiz turleri kontrol et.
        check_pending_runs()

        print("PortfolioAI - Otomatik SANAL Ajan")
        print("Parite:", SYMBOL)
        print("Mum:", INTERVAL)
        print("Kontrol araligi:", POLL_SECONDS, "saniye")
        print("Sanal alim tutari:", BUY_AMOUNT_TRY, "TRY")
        print("Gercek borsa emri: YOK")
        print("Durdurmak icin: Ctrl+C")
        print("--------------------------------", flush=True)

        while True:
            try:
                run_once()
            except KeyboardInterrupt:
                print("\nAjan durduruldu.", flush=True)
                break
            except Exception as error:
                print(
                    "Ajan hatasi:",
                    type(error).__name__,
                    str(error),
                    flush=True,
                )

                # Belirsiz bir islem varsa otomatik devam etme.
                try:
                    check_pending_runs()
                except RuntimeError as pending_error:
                    print(pending_error, flush=True)
                    print(
                        "Ajan durduruldu. Kayitlar kontrol edilmeli.",
                        flush=True,
                    )
                    break

            try:
                time.sleep(POLL_SECONDS)
            except KeyboardInterrupt:
                print("\nAjan durduruldu.", flush=True)
                break
    finally:
        lock.release()


if __name__ == "__main__":
    main()