from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal as D
import sqlite3

ROOT = Path(__file__).resolve().parent
DB = ROOT / "long_history.db"
HOUR = 3_600_000
NOW = int(datetime.now(timezone.utc).timestamp() * 1000)

INITIAL = D("10000")
ORDER_BUDGET = D("1000")
MAX_POSITIONS = 10
FEE = D("0.001")
SLIP = D("0.001")
MIN_HISTORY = 1000

def stamp(ms):
    return datetime.fromtimestamp(
        ms / 1000, timezone.utc
    ).strftime("%Y-%m-%d %H:%M")

def load(db, symbol):
    raw = db.execute("""
        SELECT open_time_ms, close_time_ms,
               open_price, high_price, low_price, close_price
        FROM historical_candles
        WHERE symbol=? AND interval='1h'
        ORDER BY open_time_ms
    """, (symbol,))

    chain = []
    for t, end, op, hi, lo, cl in raw:
        try:
            t, end = int(t), int(end)
            op, hi, lo, cl = [D(str(v)) for v in (op, hi, lo, cl)]
            valid = (
                t % HOUR == 0
                and end == t + HOUR - 1
                and end < NOW
                and all(v.is_finite() and v > 0
                        for v in (op, hi, lo, cl))
                and hi >= max(op, cl)
                and lo <= min(op, cl)
            )
            if not valid:
                chain = []
                continue
            if chain and t != chain[-1][0] + HOUR:
                chain = []
            chain.append((t, op, cl))
        except (TypeError, ValueError, ArithmeticError):
            chain = []
    return chain

def signal(rows, i):
    # i kapanisinda bilinen 51 kapanis.
    # Onceki SMA: i-1; simdiki SMA: i.
    if i < 50:
        return None
    closes = [r[2] for r in rows[i-50:i+1]]
    p20 = sum(closes[-21:-1]) / D(20)
    p50 = sum(closes[:-1]) / D(50)
    c20 = sum(closes[-20:]) / D(20)
    c50 = sum(closes[-50:]) / D(50)
    if p20 <= p50 and c20 > c50:
        return "BUY"
    if p20 >= p50 and c20 < c50:
        return "SELL"
    return None

def main():
    print("PORTFOLIOAI | ORTAK BAKIYELI PORTFOY TESTI V1")
    print("1h SMA20/50 | son %30 | sonraki mum acilisi")
    print("10000 TRY ortak bakiye | en fazla 10 pozisyon")
    print("Her emir en fazla 1000 TRY | her yon %0.1 komisyon + %0.1 kayma")
    print("Salt-okunur: paper veya gercek emir GONDERMEZ.\n")

    if not DB.is_file():
        raise FileNotFoundError(DB)

    with sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True) as db:
        symbols = [
            r[0] for r in db.execute("""
                SELECT DISTINCT symbol FROM historical_candles
                WHERE interval='1h' ORDER BY symbol
            """)
        ]
        loaded = {s: load(db, s) for s in symbols}

    # Kisa gecmisli pariteler ortak test penceresini
    # yapay olarak daraltmasin.
    eligible = {
        s: rows for s, rows in loaded.items()
        if len(rows) >= MIN_HISTORY
    }
    excluded = sorted(set(symbols) - set(eligible))
    if not eligible:
        print("Test icin yeterli kesintisiz veri yok.")
        return

    # Her paritenin kendi son %30'unun baslangicindan
    # daha erken baslamayan ORTAK test penceresi.
    starts = [
        rows[int(len(rows) * 0.70)][0]
        for rows in eligible.values()
    ]
    test_start = max(starts)
    test_end = min(rows[-1][0] for rows in eligible.values())

    # Tum pariteler ayni saatlerde bulunmali.
    indexed = {
        s: {row[0]: i for i, row in enumerate(rows)}
        for s, rows in eligible.items()
    }
    times = list(range(test_start, test_end + HOUR, HOUR))
    valid_symbols = {
        s: rows for s, rows in eligible.items()
        if all(t in indexed[s] for t in times)
        and indexed[s][test_start] >= 50
    }
    excluded += sorted(set(eligible) - set(valid_symbols))
    if len(times) < 52 or not valid_symbols:
        print("Ortak test penceresi veya veri yetersiz.")
        return

    cash = INITIAL
    positions = {}  # symbol -> (quantity, total_entry_cost)
    closed_pnls = []
    buys = sells = 0
    rejected_capacity = rejected_cash = 0
    peak = INITIAL
    max_dd = D("0")
    equity_start = INITIAL
    equity_end = INITIAL

    # t mumunun kapanisinda sinyal hesaplanir.
    # Emir ancak t+1 mumunun acilisinda uygulanir.
    for k in range(len(times) - 1):
        t = times[k]
        next_t = times[k + 1]
        sell_orders = []
        buy_orders = []

        for symbol, rows in valid_symbols.items():
            i = indexed[symbol][t]
            action = signal(rows, i)
            if action == "SELL" and symbol in positions:
                sell_orders.append(symbol)
            elif action == "BUY" and symbol not in positions:
                buy_orders.append(symbol)

        # Ayni saatte satislar once; serbest kalan nakit
        # daha sonra alislarda kullanilabilir.
        for symbol in sorted(sell_orders):
            rows = valid_symbols[symbol]
            op = rows[indexed[symbol][next_t]][1]
            qty, cost = positions.pop(symbol)
            proceeds = qty * op * (D("1") - SLIP) * (D("1") - FEE)
            cash += proceeds
            closed_pnls.append(proceeds - cost)
            sells += 1

        for symbol in sorted(buy_orders):
            if symbol in positions:
                continue
            if len(positions) >= MAX_POSITIONS:
                rejected_capacity += 1
                continue
            if cash < ORDER_BUDGET:
                rejected_cash += 1
                continue

            rows = valid_symbols[symbol]
            op = rows[indexed[symbol][next_t]][1]
            execution_price = op * (D("1") + SLIP)
            qty = ORDER_BUDGET / (D("1") + FEE) / execution_price
            cash -= ORDER_BUDGET
            positions[symbol] = (qty, ORDER_BUDGET)
            buys += 1

        # Bir sonraki mum KAPANDIKTAN sonra degerleme.
        equity_end = cash
        for symbol, (qty, _) in positions.items():
            rows = valid_symbols[symbol]
            cl = rows[indexed[symbol][next_t]][2]
            equity_end += (
                qty * cl * (D("1") - SLIP) * (D("1") - FEE)
            )

        peak = max(peak, equity_end)
        max_dd = max(max_dd, (peak - equity_end) / peak * 100)

    net = equity_end - INITIAL
    net_pct = net / INITIAL * 100
    wins = sum(p > 0 for p in closed_pnls)
    win_rate = (
        D(wins) / D(len(closed_pnls)) * 100
        if closed_pnls else None
    )

    print(f"Ortak donem (UTC): {stamp(test_start)} .. {stamp(test_end)}")
    print(f"Test edilen parite: {len(valid_symbols)}")
    print(f"Disarida kalan: {', '.join(sorted(set(excluded))) or 'YOK'}")
    print(f"Ortak saatlik mum: {len(times)}")
    print(f"Baslangic bakiye: {INITIAL:.2f} TRY")
    print(f"Son nakit: {cash:.2f} TRY")
    print(f"Son toplam ozsermaye: {equity_end:.2f} TRY")
    print(f"Net sonuc: {net:+.2f} TRY ({net_pct:+.2f}%)")
    print(f"Maksimum dusus: %{max_dd:.2f}")
    print(f"Alis: {buys} | Satis: {sells} | Acik pozisyon: {len(positions)}")
    print(
        "Kapanan islemlerde kazanma orani: "
        + (f"%{win_rate:.1f}" if win_rate is not None else "HESAPLANAMADI")
    )
    print(
        f"Pozisyon limiti nedeniyle atlanan sinyal: {rejected_capacity}"
    )
    print(f"Nakit nedeniyle atlanan sinyal: {rejected_cash}")
    print("Acik pozisyonlar tahmini cikis maliyeti dusulerek degerlendirildi.")
    print("Gercek spread, derinlik ve emir gerceklesmesi olculmedi.")
    print("Pariteler bugunku arsiv listesinden: gecmise donuk secim yanliligi olabilir.")
    print("Veritabanlarina yazilmadi; ajan ve v6 degistirilmedi.")

if __name__ == "__main__":
    main()
