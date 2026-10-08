from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal as D
import importlib.util
import sqlite3

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "portfolio_backtest_v1.py"
REPORT = ROOT / "portfolio_period_stress_report_v1.txt"

if REPORT.exists():
    raise SystemExit("Rapor zaten var; uzerine yazilmadi.")

spec = importlib.util.spec_from_file_location("backtest_original", SOURCE)
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)

def ms(s):
    return int(datetime.strptime(
        s, "%Y-%m-%d %H:%M"
    ).replace(tzinfo=timezone.utc).timestamp() * 1000)

def stamp(t):
    return datetime.fromtimestamp(
        t / 1000, timezone.utc
    ).strftime("%Y-%m-%d %H:%M")

HOUR = original.HOUR
START = ms("2026-08-26 20:00")
END = ms("2026-09-22 19:00")
TIMES = list(range(START, END + HOUR, HOUR))
if len(TIMES) != 648:
    raise SystemExit("Beklenmeyen test donemi.")

with sqlite3.connect(
    original.DB.as_uri() + "?mode=ro", uri=True
) as db:
    symbols = [
        r[0] for r in db.execute("""
            SELECT DISTINCT symbol FROM historical_candles
            WHERE interval='1h' ORDER BY symbol
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
if len(baseline) != 21:
    raise SystemExit(
        f"21 yerine {len(baseline)} parite bulundu. "
        "Arsiv degismis olabilir; test durduruldu."
    )

PERIODS = [
    ("Ilk yari", TIMES[:324]),
    ("Ikinci yari", TIMES[324:]),
    ("Tam donem", TIMES),
]
UNIVERSES = [
    ("21 parite", set()),
    ("GTRY + PHATRY haric", {"GTRY", "PHATRY"}),
    ("Dort parite haric", {
        "GTRY", "PHATRY", "ONETRY", "MUBARAKTRY"
    }),
]
SLIPS = [D("0.001"), D("0.003"), D("0.005")]

def run(times, excluded, slip):
    active = {
        s: baseline[s] for s in sorted(baseline)
        if s not in excluded
    }
    cash = original.INITIAL
    positions = {}
    closed = []
    buys = sells = 0
    peak = original.INITIAL
    max_dd = D("0")
    equity = original.INITIAL
    skipped_capacity = skipped_cash = 0

    for k in range(len(times) - 1):
        t, next_t = times[k], times[k + 1]
        sell_orders = []
        buy_orders = []

        for symbol, rows in active.items():
            action = original.signal(rows, indexed[symbol][t])
            if action == "SELL" and symbol in positions:
                sell_orders.append(symbol)
            elif action == "BUY" and symbol not in positions:
                buy_orders.append(symbol)

        for symbol in sorted(sell_orders):
            op = active[symbol][indexed[symbol][next_t]][1]
            qty, cost = positions.pop(symbol)
            proceeds = (
                qty * op * (D("1") - slip)
                * (D("1") - original.FEE)
            )
            cash += proceeds
            closed.append(proceeds - cost)
            sells += 1

        for symbol in sorted(buy_orders):
            if symbol in positions:
                continue
            if len(positions) >= original.MAX_POSITIONS:
                skipped_capacity += 1
                continue
            if cash < original.ORDER_BUDGET:
                skipped_cash += 1
                continue
            op = active[symbol][indexed[symbol][next_t]][1]
            price = op * (D("1") + slip)
            qty = (
                original.ORDER_BUDGET
                / (D("1") + original.FEE)
                / price
            )
            cash -= original.ORDER_BUDGET
            positions[symbol] = (qty, original.ORDER_BUDGET)
            buys += 1

        equity = cash
        for symbol, (qty, _) in positions.items():
            close = active[symbol][indexed[symbol][next_t]][2]
            equity += (
                qty * close * (D("1") - slip)
                * (D("1") - original.FEE)
            )
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100)

    realized = sum(closed, D("0"))
    unrealized = (
        equity - cash
        - sum(cost for _, cost in positions.values())
    )
    net = equity - original.INITIAL
    if abs(net - realized - unrealized) > D("0.01"):
        raise ArithmeticError("Muhasebe tutarsizligi.")
    return (
        net, net / original.INITIAL * 100,
        max_dd, buys, sells, len(positions),
        realized, unrealized, skipped_capacity, skipped_cash
    )

lines = [
    "PORTFOLIOAI | DONEM VE KAYMA STRES TESTI V1",
    "Iki yari birbirinden BAGIMSIZ 10000 TRY ile baslar.",
    "Ikinci yari sinyali icin onceki tarihsel mumlar",
    "yalnizca SMA isinmasinda kullanilir; pozisyon tasinmaz.",
    "Tum sonuclar geriye donuk simulasyondur.",
    "Komisyon her yon %0.1; kayma her yon belirtilen oranda.",
    "",
]

for period_name, times in PERIODS:
    lines.append(
        f"===== {period_name}: "
        f"{stamp(times[0])} .. {stamp(times[-1])} "
        f"({len(times)} mum) ====="
    )
    for universe_name, excluded in UNIVERSES:
        for slip in SLIPS:
            r = run(times, excluded, slip)
            line = (
                f"{universe_name:<24} "
                f"kayma=%{slip * 100:<5} "
                f"net={r[0]:+10.2f} TRY "
                f"getiri=%{r[1]:+7.2f} "
                f"maxDD=%{r[2]:6.2f} "
                f"alis={r[3]:3} satis={r[4]:3} "
                f"acik={r[5]}"
            )
            lines.append(line)
            print(line, flush=True)
    lines.append("")

lines += [
    "NOT: Yari getirileri toplanarak tam donem getirisi bulunmaz;",
    "her yari sifir pozisyon ve yeni bakiye ile baslatildi.",
    "Sabit kayma, gercek spread ve emir defteri yerine gecmez.",
    "Parite evreni gecmise bakilarak olusturulmus olabilir.",
    "Gercek emir yok; veritabanina yazma yok.",
]
REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"\nRapor: {REPORT.name}")
