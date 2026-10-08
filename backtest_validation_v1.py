from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

DB = Path(__file__).resolve().parent / "long_history.db"
NOW = int(datetime.now(timezone.utc).timestamp() * 1000)
HOUR = 3_600_000
D = Decimal
START = D("10000")
BUDGET = D("1000")
FEE = D("0.001")
SLIP = D("0.001")  # Her yon icin varsayimsal %0.1

def candles(db, symbol):
    raw = db.execute("""
        SELECT open_time_ms, close_time_ms, open_price,
               high_price, low_price, close_price
        FROM historical_candles
        WHERE symbol=? AND interval='1h'
        ORDER BY open_time_ms
    """, (symbol,))
    rows = []
    for t, end, op, hi, lo, cl in raw:
        try:
            t, end = int(t), int(end)
            op, hi, lo, cl = map(lambda x: D(str(x)), (op, hi, lo, cl))
            if not (
                t % HOUR == 0 and end == t + HOUR - 1
                and end < NOW
                and all(x.is_finite() and x > 0 for x in (op, hi, lo, cl))
                and hi >= max(op, cl) and lo <= min(op, cl)
            ):
                continue
            if rows and t != rows[-1][0] + HOUR:
                rows = []
            rows.append((t, op, cl))
        except (TypeError, ValueError, ArithmeticError):
            continue
    return rows

def simulate(rows, first, last, slippage):
    cash, qty, peak = START, D("0"), START
    maxdd = D("0")
    buys = sells = 0

    # first: test bolumunun ilk mumu. Onceki 50 mum
    # sadece gostergeleri isitmak icin kullanilir.
    for i in range(first, last - 1):
        prev = [r[2] for r in rows[i-50:i]]
        curr = [r[2] for r in rows[i-49:i+1]]
        if len(prev) != 50 or len(curr) != 50:
            continue

        p20, p50 = sum(prev[-20:])/20, sum(prev)/50
        c20, c50 = sum(curr[-20:])/20, sum(curr)/50
        next_open = rows[i+1][1]

        if qty == 0 and p20 <= p50 and c20 > c50:
            spend = min(BUDGET, cash)
            if spend > 0:
                buy_price = next_open * (1 + slippage)
                qty = spend / (1 + FEE) / buy_price
                cash -= spend
                buys += 1

        elif qty > 0 and p20 >= p50 and c20 < c50:
            sell_price = next_open * (1 - slippage)
            cash += qty * sell_price * (1 - FEE)
            qty = D("0")
            sells += 1

        # Bu degerleme sadece kapanmis mumla yapilir.
        equity = cash + qty * rows[i+1][2] * (1 - slippage) * (1 - FEE)
        peak = max(peak, equity)
        maxdd = max(maxdd, (peak - equity) / peak * 100)

    final = cash + qty * rows[last-1][2] * (1 - slippage) * (1 - FEE)
    return (final / START - 1) * 100, maxdd, buys, sells, qty > 0

def buy_hold(rows, first, last):
    # Ayni test penceresinde 1000 TL'lik tek alim;
    # SMA stratejisinin islem butcesiyle ayni.
    entry = rows[first][1] * (1 + SLIP)
    exit_price = rows[last-1][2] * (1 - SLIP)
    qty = BUDGET / (1 + FEE) / entry
    final = START - BUDGET + qty * exit_price * (1 - FEE)
    return (final / START - 1) * 100

def main():
    print("PORTFOLIOAI | AYRI DONEM + MALIYET TESTI")
    print("Son %30 test | SMA20/50 | sonraki mum acilisi")
    print("Her yon: %0.1 komisyon + varsayimsal %0.1 kayma")
    print("Al-tut: ayni donemde tek 1000 TRY alim")
    print("Sonuclar ayri sanal hesaplar; emir gonderilmez.\n")

    with sqlite3.connect(DB.as_uri()+"?mode=ro", uri=True) as db:
        symbols = [r[0] for r in db.execute("""
            SELECT DISTINCT symbol FROM historical_candles
            WHERE interval='1h' ORDER BY symbol
        """)]
        tested = 0
        for symbol in symbols:
            rows = candles(db, symbol)
            n = len(rows)
            split = int(n * D("0.70"))
            if n < 200 or split < 50 or n - split < 52:
                print(f"{symbol:<15} ATLANDI | kesintisiz mum={n}")
                continue

            # Testin ilk sinyali split mumunun kapanisinda;
            # onceki 50 mum sadece gostergeler icindir.
            net, dd, buys, sells, opened = simulate(rows, split, n, SLIP)
            baseline = buy_hold(rows, split + 1, n)
            start = datetime.fromtimestamp(
                rows[split][0]/1000, timezone.utc
            ).strftime("%Y-%m-%d")
            end = datetime.fromtimestamp(
                rows[-1][0]/1000, timezone.utc
            ).strftime("%Y-%m-%d")
            tested += 1
            print(
                f"{symbol:<15} {start}..{end} | "
                f"SMA={net:+7.2f}% | "
                f"al-tut={baseline:+7.2f}% | "
                f"maxDD={dd:5.2f}% | "
                f"alis={buys:2} satis={sells:2} "
                f"acik={'E' if opened else 'H'}"
            )

    print(f"\nOZET | Test edilen: {tested}/{len(symbols)}")
    print("Kayma varsayimdir; gercek spread ve likidite olculmedi.")
    print("Veritabanina yazilmadi; paper/gercek emir verilmedi.")

if __name__ == "__main__":
    main()
