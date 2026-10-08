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
BUDGET = D("1000")
FEE = D("0.001")
MAX_POSITIONS = 10
MIN_HISTORY = 1000
SLIPPAGES = [D("0.001"), D("0.003"), D("0.005")]

def utc(ms):
    return datetime.fromtimestamp(
        ms / 1000, timezone.utc
    ).strftime("%Y-%m-%d %H:%M")

def load(db, symbol):
    result = []
    raw = db.execute("""
        SELECT open_time_ms, close_time_ms,
               open_price, high_price, low_price, close_price
        FROM historical_candles
        WHERE symbol=? AND interval='1h'
        ORDER BY open_time_ms
    """, (symbol,))

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
                result = []
                continue
            if result and t != result[-1][0] + HOUR:
                result = []
            result.append((t, op, cl))
        except (ValueError, TypeError, ArithmeticError):
            result = []
    return result

def signal(rows, i):
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

def prepare():
    with sqlite3.connect(
        DB.as_uri() + "?mode=ro", uri=True, timeout=10
    ) as db:
        symbols = [
            row[0] for row in db.execute("""
                SELECT DISTINCT symbol
                FROM historical_candles
                WHERE interval='1h'
                ORDER BY symbol
            """)
        ]
        loaded = {s: load(db, s) for s in symbols}

    eligible = {
        s: rows for s, rows in loaded.items()
        if len(rows) >= MIN_HISTORY
    }
    if not eligible:
        raise RuntimeError("Yeterli kesintisiz saatlik veri yok.")

    start = max(
        rows[int(len(rows) * 0.70)][0]
        for rows in eligible.values()
    )
    end = min(rows[-1][0] for rows in eligible.values())
    times = list(range(start, end + HOUR, HOUR))
    indexed = {
        s: {row[0]: i for i, row in enumerate(rows)}
        for s, rows in eligible.items()
    }
    selected = {
        s: rows for s, rows in eligible.items()
        if all(t in indexed[s] for t in times)
        and indexed[s][start] >= 50
    }
    if len(times) < 52 or not selected:
        raise RuntimeError("Ortak test penceresi yetersiz.")

    excluded = sorted(set(symbols) - set(selected))
    return selected, indexed, times, excluded

def simulate(selected, indexed, times, slip):
    cash = INITIAL
    positions = {}  # symbol -> (quantity, entry_cost)
    realized = defaultdict(lambda: D("0"))
    closed_count = defaultdict(int)
    open_pnl = {}
    closed_pnls = []
    buys = sells = 0
    capacity_skips = cash_skips = 0
    peak = INITIAL
    max_dd = D("0")
    max_open = 0

    for k in range(len(times) - 1):
        t, next_t = times[k], times[k+1]
        sell_orders, buy_orders = [], []

        for symbol, rows in selected.items():
            action = signal(rows, indexed[symbol][t])
            if action == "SELL" and symbol in positions:
                sell_orders.append(symbol)
            elif action == "BUY" and symbol not in positions:
                buy_orders.append(symbol)

        for symbol in sorted(sell_orders):
            op = selected[symbol][indexed[symbol][next_t]][1]
            qty, cost = positions.pop(symbol)
            proceeds = qty * op * (1 - slip) * (1 - FEE)
            pnl = proceeds - cost
            cash += proceeds
            realized[symbol] += pnl
            closed_pnls.append(pnl)
            closed_count[symbol] += 1
            sells += 1

        for symbol in sorted(buy_orders):
            if symbol in positions:
                continue
            if len(positions) >= MAX_POSITIONS:
                capacity_skips += 1
                continue
            if cash < BUDGET:
                cash_skips += 1
                continue

            op = selected[symbol][indexed[symbol][next_t]][1]
            buy_price = op * (1 + slip)
            qty = BUDGET / (1 + FEE) / buy_price
            cash -= BUDGET
            positions[symbol] = (qty, BUDGET)
            buys += 1

        max_open = max(max_open, len(positions))

        equity = cash
        for symbol, (qty, _) in positions.items():
            close = selected[symbol][indexed[symbol][next_t]][2]
            equity += qty * close * (1 - slip) * (1 - FEE)

        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)

    final_equity = cash
    open_value = D("0")
    for symbol, (qty, cost) in positions.items():
        last_close = selected[symbol][indexed[symbol][times[-1]]][2]
        estimated_proceeds = (
            qty * last_close * (1 - slip) * (1 - FEE)
        )
        open_value += estimated_proceeds
        open_pnl[symbol] = estimated_proceeds - cost
        final_equity += estimated_proceeds

    realized_total = sum(realized.values(), D("0"))
    unrealized_total = sum(open_pnl.values(), D("0"))
    net = final_equity - INITIAL

    # Muhasebe denkligi: nakit + acik pozisyon degeri
    # = baslangic + kapanmis PnL + acik PnL.
    reconciled = (
        abs(net - realized_total - unrealized_total)
        <= D("0.00000001")
    )

    return {
        "cash": cash,
        "open_value": open_value,
        "equity": final_equity,
        "net": net,
        "net_pct": net / INITIAL * 100,
        "realized": realized_total,
        "unrealized": unrealized_total,
        "realized_by_symbol": realized,
        "open_by_symbol": open_pnl,
        "closed_count": closed_count,
        "buys": buys,
        "sells": sells,
        "open_count": len(positions),
        "max_open": max_open,
        "max_dd": max_dd,
        "capacity_skips": capacity_skips,
        "cash_skips": cash_skips,
        "wins": sum(p > 0 for p in closed_pnls),
        "closed": len(closed_pnls),
        "reconciled": reconciled,
    }

def main():
    print("PORTFOLIOAI | ORTAK PORTFOY DENETIMI V1")
    print("Salt-okunur | 1h SMA20/50 | ortak bakiye 10000 TRY")
    print("Komisyon: her yon %0.1")
    print("Kayma senaryolari: her yon %0.1 / %0.3 / %0.5")
    print("Sinyal kapanista; emir sonraki mum acilisinda.\n")

    selected, indexed, times, excluded = prepare()
    print(f"Ortak donem UTC: {utc(times[0])} .. {utc(times[-1])}")
    print(f"Parite: {len(selected)} | Saatlik mum: {len(times)}")
    print(f"Disarida kalan: {', '.join(excluded) or 'YOK'}")

    results = []
    for slip in SLIPPAGES:
        result = simulate(selected, indexed, times, slip)
        results.append(result)
        print(f"\n===== TEK YONLU KAYMA %{slip * 100:.1f} =====")
        print(f"Nakit: {result['cash']:.2f} TRY")
        print(f"Acik pozisyon tahmini degeri: {result['open_value']:.2f} TRY")
        print(f"Toplam ozsermaye: {result['equity']:.2f} TRY")
        print(f"Kapanmis islemler PnL: {result['realized']:+.2f} TRY")
        print(f"Acik pozisyonlar PnL: {result['unrealized']:+.2f} TRY")
        print(
            f"Toplam net: {result['net']:+.2f} TRY "
            f"({result['net_pct']:+.2f}%)"
        )
        print(f"Maksimum dusus: %{result['max_dd']:.2f}")
        print(
            f"Alis={result['buys']} | Satis={result['sells']} | "
            f"Acik={result['open_count']} | "
            f"Eszamanli azami acik={result['max_open']}"
        )
        print(
            f"Limit nedeniyle atlanan={result['capacity_skips']} | "
            f"Nakit nedeniyle atlanan={result['cash_skips']}"
        )
        print(
            "MUHASEBE KONTROLU: "
            + ("TUTTU" if result["reconciled"] else "HATA")
        )

    base = results[0]
    print("\n===== PARITE BAZINDA DENETIM | KAYMA %0.1 =====")
    print("Parite           Kapanmis PnL   Acik PnL   Toplam PnL   Kapanan")
    for symbol in sorted(selected):
        realized = base["realized_by_symbol"][symbol]
        opened = base["open_by_symbol"].get(symbol, D("0"))
        total = realized + opened
        count = base["closed_count"][symbol]
        print(
            f"{symbol:<15} {realized:>+12.2f} "
            f"{opened:>+10.2f} {total:>+12.2f} {count:>8}"
        )

    print("\n===== DENETIM OZETI =====")
    print(
        "Tum senaryolarda muhasebe denkligi: "
        + ("TUTTU" if all(r["reconciled"] for r in results)
           else "HATA - SONUCLARI KULLANMA")
    )
    print("Acik PnL gerceklesmis kazanc degildir.")
    print("Kayma varsayimsaldir; gercek spread ve likidite olculmedi.")
    print("Bugunku parite listesinden gecmise donuk secim yanliligi olabilir.")
    print("Veritabanlarina yazilmadi; ajan ve v6 degistirilmedi.")

if __name__ == "__main__":
    main()
