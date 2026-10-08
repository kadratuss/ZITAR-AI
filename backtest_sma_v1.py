from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import sqlite3

ROOT = Path(__file__).resolve().parent
DB = ROOT / "long_history.db"

HOUR_MS = 3_600_000
INITIAL_CASH = Decimal("10000")
TRADE_BUDGET = Decimal("1000")
FEE = Decimal("0.001")
ZERO = Decimal("0")
NOW_MS = int(datetime.now(timezone.utc).timestamp() * 1000)


def read_candles(db, symbol):
    raw = db.execute(
        """
        SELECT open_time_ms, close_time_ms, open_price,
               high_price, low_price, close_price
        FROM historical_candles
        WHERE symbol=? AND interval='1h'
        ORDER BY open_time_ms
        """,
        (symbol,),
    )

    rows = []
    rejected = 0

    for record in raw:
        try:
            opened, closed = int(record[0]), int(record[1])
            op, hi, lo, cl = (
                Decimal(str(value)) for value in record[2:]
            )
            valid = (
                opened % HOUR_MS == 0
                and closed == opened + HOUR_MS - 1
                and closed < NOW_MS
                and all(
                    value.is_finite() and value > ZERO
                    for value in (op, hi, lo, cl)
                )
                and hi >= max(op, cl)
                and lo <= min(op, cl)
            )
            if not valid:
                rejected += 1
                continue
            rows.append((opened, op, cl))
        except (ValueError, TypeError, InvalidOperation):
            rejected += 1

    return rows, rejected


def last_contiguous_segment(rows):
    if not rows:
        return []

    segment = [rows[0]]
    for row in rows[1:]:
        if row[0] == segment[-1][0] + HOUR_MS:
            segment.append(row)
        else:
            segment = [row]
    return segment


def run_backtest(rows):
    cash = INITIAL_CASH
    quantity = ZERO
    entry_cost = ZERO
    completed = []
    equity_curve = [INITIAL_CASH]
    peak = INITIAL_CASH
    max_drawdown = ZERO
    buy_count = 0

    # i mumunun kapanisinda hesaplanan sinyal,
    # yalnizca i+1 mumunun acilisinda uygulanir.
    for i in range(50, len(rows) - 1):
        closes = [row[2] for row in rows[i - 50:i + 1]]

        prev20 = sum(closes[-21:-1]) / Decimal(20)
        prev50 = sum(closes[-51:-1]) / Decimal(50)
        now20 = sum(closes[-20:]) / Decimal(20)
        now50 = sum(closes[-50:]) / Decimal(50)

        cross_up = prev20 <= prev50 and now20 > now50
        cross_down = prev20 >= prev50 and now20 < now50

        next_open = rows[i + 1][1]

        if quantity == ZERO and cross_up:
            # Butce, alis komisyonunu da kapsar.
            budget = min(TRADE_BUDGET, cash)
            if budget > ZERO:
                gross = budget / (Decimal(1) + FEE)
                fee = gross * FEE
                quantity = gross / next_open
                entry_cost = gross + fee
                cash -= entry_cost
                buy_count += 1

        elif quantity > ZERO and cross_down:
            gross = quantity * next_open
            proceeds = gross * (Decimal(1) - FEE)
            cash += proceeds
            completed.append(proceeds - entry_cost)
            quantity = ZERO
            entry_cost = ZERO

        # Gunluk/saatlik ara degerleme: eldeki pozisyonun
        # o ana kadar kapanmis son mum fiyatini kullanir.
        equity = cash + quantity * rows[i + 1][2] * (
            Decimal(1) - FEE
        )
        equity_curve.append(equity)

        if equity > peak:
            peak = equity
        drawdown = (peak - equity) / peak * Decimal(100)
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    # Son mum kapanisinda acik pozisyonu varsayimsal
    # satis komisyonu dusulmus piyasa degeriyle goster.
    final_equity = cash
    if quantity > ZERO:
        final_equity += (
            quantity * rows[-1][2] * (Decimal(1) - FEE)
        )

    net_pnl = final_equity - INITIAL_CASH
    net_pct = net_pnl / INITIAL_CASH * Decimal(100)
    wins = sum(pnl > ZERO for pnl in completed)
    win_rate = (
        Decimal(wins) / Decimal(len(completed)) * Decimal(100)
        if completed else None
    )

    return {
        "buys": buy_count,
        "closed": len(completed),
        "open": quantity > ZERO,
        "net_pnl": net_pnl,
        "net_pct": net_pct,
        "drawdown": max_drawdown,
        "win_rate": win_rate,
    }


def main():
    if not DB.is_file():
        raise FileNotFoundError(DB)

    print("PORTFOLIOAI | SMA20/50 GECMIS VERI TESTI V1")
    print("Piyasa: TRY spot | Zaman: 1h | Baslangic: 10000 TRY")
    print("Islem butcesi: 1000 TRY | Komisyon: alis %0.1 + satis %0.1")
    print("Sinyal: mum kapanisi | Uygulama: sonraki mum acilisi")
    print("Salt-okunur; gercek veya paper emir GONDERMEZ.\n")

    with sqlite3.connect(
        DB.as_uri() + "?mode=ro", uri=True, timeout=10
    ) as db:
        symbols = [
            row[0] for row in db.execute(
                """
                SELECT DISTINCT symbol
                FROM historical_candles
                WHERE interval='1h'
                ORDER BY symbol
                """
            )
        ]

        tested = 0
        skipped = 0

        for symbol in symbols:
            rows, rejected = read_candles(db, symbol)
            chain = last_contiguous_segment(rows)

            if len(chain) < 52:
                skipped += 1
                print(
                    f"{symbol:<15} ATLANDI | "
                    f"kesintisiz mum={len(chain)} | "
                    f"gecersiz mum={rejected}"
                )
                continue

            result = run_backtest(chain)
            tested += 1

            win_text = (
                f"{result['win_rate']:.1f}%"
                if result["win_rate"] is not None else "-"
            )
            print(
                f"{symbol:<15} "
                f"mum={len(chain):>4} | "
                f"alis={result['buys']:>2} | "
                f"kapanan={result['closed']:>2} | "
                f"acik={'EVET' if result['open'] else 'HAYIR':<5} | "
                f"net={result['net_pnl']:+8.2f} TRY "
                f"({result['net_pct']:+6.2f}%) | "
                f"maxDD={result['drawdown']:5.2f}% | "
                f"kazanma={win_text}"
            )

        print("\n===== OZET =====")
        print(f"Arsivdeki parite: {len(symbols)}")
        print(f"Test edilen: {tested}")
        print(f"Yetersiz veri nedeniyle atlanan: {skipped}")
        print("Her parite ayri 10000 TRY sanal bakiyeyle test edildi.")
        print("Sonuclar birlestirilmis portfoy getirisi degildir.")
        print("Spread, kayma ve emir defteri etkisi henuz dahil degil.")
        print("Veritabanlarina yazilmadi; ajan calistirilmadi.")


if __name__ == "__main__":
    main()
