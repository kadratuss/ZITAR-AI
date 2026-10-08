from pathlib import Path
from decimal import Decimal as D
from datetime import datetime, timezone
import importlib.util
import sqlite3

ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT / "portfolio_backtest_v1.py"
REPORT = ROOT / "portfolio_liquidity_scenarios_report_v1.txt"

if REPORT.exists():
    raise SystemExit("Rapor zaten var; uzerine yazilmadi.")
if not ORIGINAL.is_file():
    raise SystemExit("portfolio_backtest_v1.py bulunamadi.")

spec = importlib.util.spec_from_file_location("original_portfolio_backtest", ORIGINAL)
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)

HOUR = original.HOUR
INITIAL = original.INITIAL
BUDGET = original.ORDER_BUDGET
MAX_POSITIONS = original.MAX_POSITIONS
FEE = original.FEE
SLIP = original.SLIP

def ms(text):
    return int(datetime.strptime(
        text, "%Y-%m-%d %H:%M"
    ).replace(tzinfo=timezone.utc).timestamp() * 1000)

# Daha once API ile dogrulanan ortak donem; tum senaryolarda SABIT.
START = ms("2026-08-26 20:00")
END = ms("2026-09-22 19:00")
TIMES = list(range(START, END + HOUR, HOUR))

SCENARIOS = [
    ("Tum 21 parite", set()),
    ("GTRY haric", {"GTRY"}),
    ("PHATRY haric", {"PHATRY"}),
    ("GTRY ve PHATRY haric", {"GTRY", "PHATRY"}),
    ("ONETRY ve MUBARAKTRY haric", {"ONETRY", "MUBARAKTRY"}),
    ("Bu dort parite haric", {"GTRY", "PHATRY", "ONETRY", "MUBARAKTRY"}),
]

with sqlite3.connect(
    original.DB.as_uri() + "?mode=ro", uri=True
) as db:
    symbols = [
        r[0] for r in db.execute("""
            SELECT DISTINCT symbol
            FROM historical_candles
            WHERE interval='1h'
            ORDER BY symbol
        """)
    ]
    loaded = {s: original.load(db, s) for s in symbols}

eligible = {
    s: rows for s, rows in loaded.items()
    if len(rows) >= original.MIN_HISTORY
}
indexed = {
    s: {row[0]: i for i, row in enumerate(rows)}
    for s, rows in eligible.items()
}
baseline = {
    s: rows for s, rows in eligible.items()
    if all(t in indexed[s] for t in TIMES)
    and indexed[s][START] >= 50
}

if len(TIMES) != 648:
    raise SystemExit(f"Beklenmeyen saat sayisi: {len(TIMES)}")
if len(baseline) != 21:
    raise SystemExit(
        "Beklenen 21 parite yerine "
        f"{len(baseline)} bulundu: {', '.join(sorted(baseline))}. "
        "Test yapilmadi; arsiv degismis olabilir."
    )

def run(name, excluded):
    active = {
        s: baseline[s] for s in sorted(baseline)
        if s not in excluded
    }
    cash = INITIAL
    positions = {}
    closed_pnls = []
    buys = sells = 0
    skipped_capacity = skipped_cash = 0
    peak = INITIAL
    max_dd = D("0")
    equity = INITIAL

    for k in range(len(TIMES) - 1):
        t, next_t = TIMES[k], TIMES[k + 1]
        sell_orders = []
        buy_orders = []

        for symbol, rows in active.items():
            action = original.signal(rows, indexed[symbol][t])
            if action == "SELL" and symbol in positions:
                sell_orders.append(symbol)
            elif action == "BUY" and symbol not in positions:
                buy_orders.append(symbol)

        for symbol in sorted(sell_orders):
            rows = active[symbol]
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
                skipped_capacity += 1
                continue
            if cash < BUDGET:
                skipped_cash += 1
                continue
            rows = active[symbol]
            op = rows[indexed[symbol][next_t]][1]
            execution_price = op * (D("1") + SLIP)
            qty = BUDGET / (D("1") + FEE) / execution_price
            cash -= BUDGET
            positions[symbol] = (qty, BUDGET)
            buys += 1

        equity = cash
        for symbol, (qty, _) in positions.items():
            rows = active[symbol]
            close = rows[indexed[symbol][next_t]][2]
            equity += qty * close * (D("1") - SLIP) * (D("1") - FEE)

        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)

    net = equity - INITIAL
    realized = sum(closed_pnls, D("0"))
    unrealized = equity - cash - sum(
        cost for _, cost in positions.values()
    )
    # Tum acik pozisyonlarin maliyeti ve kapanan islemler
    # toplam nakit/ozsermaye ile uyusmali.
    reconciliation = net - realized - unrealized
    if abs(reconciliation) > D("0.01"):
        raise ArithmeticError(
            f"{name}: muhasebe tutarsizligi {reconciliation}"
        )

    return {
        "name": name,
        "count": len(active),
        "net": net,
        "pct": net / INITIAL * 100,
        "equity": equity,
        "cash": cash,
        "dd": max_dd,
        "buys": buys,
        "sells": sells,
        "open": len(positions),
        "realized": realized,
        "unrealized": unrealized,
        "capacity": skipped_capacity,
        "cash_skips": skipped_cash,
    }

results = [run(name, excluded) for name, excluded in SCENARIOS]
base = results[0]

lines = [
    "PORTFOLIOAI | SABIT DONEM PARITE DUYARLILIK TESTI V1",
    "UTC: 2026-08-26 20:00 .. 2026-09-22 19:00",
    f"Ortak saatlik mum: {len(TIMES)}",
    f"Baslangic: {INITIAL:.2f} TRY | Emir: {BUDGET:.2f} TRY",
    f"Pozisyon limiti: {MAX_POSITIONS}",
    f"Her yon komisyon: %{FEE * 100} | kayma: %{SLIP * 100}",
    "Sinyal ve emir kurallari: portfolio_backtest_v1.py",
    "",
]
for r in results:
    lines.extend([
        f"===== {r['name']} =====",
        f"Parite: {r['count']}",
        f"Net: {r['net']:+.2f} TRY ({r['pct']:+.2f}%)",
        f"Ilk senaryoya gore net fark: {r['net'] - base['net']:+.2f} TRY",
        f"Son ozsermaye: {r['equity']:.2f} TRY",
        f"Son nakit: {r['cash']:.2f} TRY",
        f"Maksimum dusus: %{r['dd']:.2f}",
        f"Alis: {r['buys']} | Satis: {r['sells']} | Acik: {r['open']}",
        f"Gerceklesmis K/Z: {r['realized']:+.2f} TRY",
        f"Acik pozisyon tahmini K/Z: {r['unrealized']:+.2f} TRY",
        f"Pozisyon limiti nedeniyle atlanan: {r['capacity']}",
        f"Nakit nedeniyle atlanan: {r['cash_skips']}",
        "Muhasebe: TUTTU",
        "",
    ])

lines += [
    "NOTLAR:",
    "Parite cikarmak, nakit ve pozisyon dagilimini da degistirir.",
    "Bu nedenle net fark, tek paritenin izole kar/zarari degildir.",
    "Gecmis hacim, acilis anindaki emir defterini kanitlamaz.",
    "Gecmise donuk parite secimi ve ileriye donuk performans belirsiz.",
    "Gercek emir yok; veritabanina yazma yok.",
]
REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
print(f"\nRapor: {REPORT.name}")
