from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal as D
from collections import defaultdict
import csv
import sqlite3

ROOT = Path(__file__).resolve().parent
DB = ROOT / "long_history.db"
HOUR = 3_600_000
NOW = int(datetime.now(timezone.utc).timestamp() * 1000)
START_CASH = D("10000")
BUDGET = D("1000")
FEE = D("0.001")
SLIP = D("0.001")
MAX_OPEN = 10

def utc(ms):
    return datetime.fromtimestamp(
        ms / 1000, timezone.utc
    ).strftime("%Y-%m-%d %H:%M")

def load(db, symbol):
    chain = []
    for t, end, op, hi, lo, cl in db.execute("""
        SELECT open_time_ms, close_time_ms, open_price,
               high_price, low_price, close_price
        FROM historical_candles
        WHERE symbol=? AND interval='1h'
        ORDER BY open_time_ms
    """, (symbol,)):
        try:
            t, end = int(t), int(end)
            op, hi, lo, cl = [D(str(x)) for x in (op, hi, lo, cl)]
            valid = (
                t % HOUR == 0
                and end == t + HOUR - 1
                and end < NOW
                and all(x.is_finite() and x > 0 for x in (op, hi, lo, cl))
                and hi >= max(op, cl)
                and lo <= min(op, cl)
            )
            if not valid:
                chain = []
                continue
            if chain and t != chain[-1][0] + HOUR:
                chain = []
            chain.append((t, op, cl))
        except (ValueError, TypeError, ArithmeticError):
            chain = []
    return chain

def signal(rows, i):
    if i < 50:
        return None
    c = [row[2] for row in rows[i-50:i+1]]
    p20, p50 = sum(c[-21:-1])/20, sum(c[:-1])/50
    n20, n50 = sum(c[-20:])/20, sum(c[-50:])/50
    if p20 <= p50 and n20 > n50:
        return "BUY"
    if p20 >= p50 and n20 < n50:
        return "SELL"
    return None

def save_csv(path, headers, records):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(records)

def main():
    if not DB.is_file():
        raise FileNotFoundError(DB)

    with sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True) as db:
        symbols = [r[0] for r in db.execute("""
            SELECT DISTINCT symbol FROM historical_candles
            WHERE interval='1h' ORDER BY symbol
        """)]
        loaded = {s: load(db, s) for s in symbols}

    eligible = {
        s: rows for s, rows in loaded.items()
        if len(rows) >= 1000
    }
    if not eligible:
        raise RuntimeError("Yeterli kesintisiz veri yok.")

    start = max(
        rows[int(len(rows) * 0.70)][0]
        for rows in eligible.values()
    )
    end = min(rows[-1][0] for rows in eligible.values())
    times = list(range(start, end + HOUR, HOUR))
    indexes = {
        s: {r[0]: i for i, r in enumerate(rows)}
        for s, rows in eligible.items()
    }
    selected = {
        s: rows for s, rows in eligible.items()
        if indexes[s].get(start, -1) >= 50
        and all(t in indexes[s] for t in times)
    }
    if len(times) < 52 or not selected:
        raise RuntimeError("Ortak test penceresi yetersiz.")

    cash = START_CASH
    positions = {}
    trades = []
    equity_rows = []
    realized = defaultdict(lambda: D("0"))
    peak = START_CASH
    max_dd = D("0")
    skipped_capacity = skipped_cash = 0

    for k in range(len(times) - 1):
        t, next_t = times[k], times[k+1]
        sells, buys = [], []

        for s, rows in selected.items():
            action = signal(rows, indexes[s][t])
            if action == "SELL" and s in positions:
                sells.append(s)
            elif action == "BUY" and s not in positions:
                buys.append(s)

        for s in sorted(sells):
            op = selected[s][indexes[s][next_t]][1]
            qty, entry_cost = positions.pop(s)
            execution = op * (1 - SLIP)
            gross = qty * execution
            fee = gross * FEE
            proceeds = gross - fee
            pnl = proceeds - entry_cost
            cash += proceeds
            realized[s] += pnl
            trades.append([
                utc(next_t), s, "SELL", utc(t),
                str(op), str(execution), str(qty),
                str(gross), str(fee), str(proceeds),
                str(pnl), str(cash)
            ])

        for s in sorted(buys):
            if len(positions) >= MAX_OPEN:
                skipped_capacity += 1
                continue
            if cash < BUDGET:
                skipped_cash += 1
                continue
            op = selected[s][indexes[s][next_t]][1]
            execution = op * (1 + SLIP)
            gross = BUDGET / (1 + FEE)
            fee = gross * FEE
            qty = gross / execution
            cash -= BUDGET
            positions[s] = (qty, BUDGET)
            trades.append([
                utc(next_t), s, "BUY", utc(t),
                str(op), str(execution), str(qty),
                str(gross), str(fee), str(BUDGET),
                "0", str(cash)
            ])

        open_value = D("0")
        for s, (qty, _) in positions.items():
            cl = selected[s][indexes[s][next_t]][2]
            open_value += qty * cl * (1 - SLIP) * (1 - FEE)

        equity = cash + open_value
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)
        equity_rows.append([
            utc(next_t), str(cash), str(open_value),
            str(equity), len(positions), str(max_dd)
        ])

    # Bagimsiz yeniden oynatma: yukaridaki pozisyon
    # sozlugunu kullanmadan, sadece islem satirlarindan.
    replay_cash = START_CASH
    replay_positions = {}
    replay_realized = D("0")
    for row in trades:
        _, symbol, side, _, _, execution, qty, gross, fee, amount, pnl, _ = row
        qty, gross, fee = D(qty), D(gross), D(fee)
        if side == "BUY":
            assert symbol not in replay_positions
            assert gross + fee == D(amount)
            replay_cash -= gross + fee
            replay_positions[symbol] = (qty, gross + fee)
        else:
            assert symbol in replay_positions
            held_qty, cost = replay_positions.pop(symbol)
            assert held_qty == qty
            assert qty * D(execution) == gross
            assert gross - fee == D(amount)
            assert D(amount) - cost == D(pnl)
            replay_cash += gross - fee
            replay_realized += D(pnl)
        assert replay_cash >= 0
        assert len(replay_positions) <= MAX_OPEN

    replay_open = D("0")
    replay_unrealized = D("0")
    for s, (qty, cost) in replay_positions.items():
        last_close = selected[s][indexes[s][times[-1]]][2]
        proceeds = qty * last_close * (1 - SLIP) * (1 - FEE)
        replay_open += proceeds
        replay_unrealized += proceeds - cost

    replay_equity = replay_cash + replay_open
    ledger_equity = D(equity_rows[-1][3])
    reconciled = (
        replay_cash == cash
        and set(replay_positions) == set(positions)
        and replay_equity == ledger_equity
        and replay_equity - START_CASH
            == replay_realized + replay_unrealized
    )

    trade_path = ROOT / "portfolio_trades_audit.csv"
    equity_path = ROOT / "portfolio_equity_audit.csv"
    summary_path = ROOT / "portfolio_symbol_audit.csv"

    save_csv(trade_path, [
        "execution_utc", "symbol", "side", "signal_candle_utc",
        "candle_open", "execution_price", "quantity",
        "gross_try", "fee_try", "cash_flow_try",
        "realized_pnl_try", "cash_after_try"
    ], trades)

    save_csv(equity_path, [
        "candle_utc", "cash_try", "open_value_try",
        "equity_try", "open_positions", "max_drawdown_pct"
    ], equity_rows)

    symbol_rows = []
    for s in sorted(selected):
        opened = D("0")
        if s in replay_positions:
            qty, cost = replay_positions[s]
            cl = selected[s][indexes[s][times[-1]]][2]
            opened = qty * cl * (1 - SLIP) * (1 - FEE) - cost
        symbol_rows.append([
            s, str(realized[s]), str(opened),
            str(realized[s] + opened)
        ])

    save_csv(summary_path, [
        "symbol", "realized_pnl_try", "open_pnl_try", "total_pnl_try"
    ], symbol_rows)

    print("PORTFOLIOAI | ISLEM GUNLUGU VE BAGIMSIZ KONTROL")
    print(f"Ortak donem UTC: {utc(times[0])} .. {utc(times[-1])}")
    print(f"Parite: {len(selected)} | Mum: {len(times)}")
    print(f"Alis: {sum(r[2]=='BUY' for r in trades)}")
    print(f"Satis: {sum(r[2]=='SELL' for r in trades)}")
    print(f"Acik pozisyon: {len(replay_positions)}")
    print(f"Nakit: {replay_cash:.2f} TRY")
    print(f"Acik pozisyon degeri: {replay_open:.2f} TRY")
    print(f"Kapanmis PnL: {replay_realized:+.2f} TRY")
    print(f"Acik PnL: {replay_unrealized:+.2f} TRY")
    print(f"Toplam ozsermaye: {replay_equity:.2f} TRY")
    print(f"Net: {replay_equity - START_CASH:+.2f} TRY")
    print(f"Maksimum dusus: %{max_dd:.2f}")
    print(f"Limit nedeniyle atlanan: {skipped_capacity}")
    print(f"Nakit nedeniyle atlanan: {skipped_cash}")
    print("BAGIMSIZ MUHASEBE: " + ("TUTTU" if reconciled else "HATA"))
    print("CSV: " + trade_path.name)
    print("CSV: " + equity_path.name)
    print("CSV: " + summary_path.name)
    print("Veritabanlarina yazilmadi; emir gonderilmedi.")
    if not reconciled:
        raise RuntimeError("Muhasebe tutmadi; raporu kullanma.")

if __name__ == "__main__":
    main()
