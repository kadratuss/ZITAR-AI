from pathlib import Path
from decimal import Decimal as D, InvalidOperation
from datetime import datetime, timezone
from collections import defaultdict
import csv
import sqlite3

ROOT = Path(__file__).resolve().parent
DB = ROOT / "long_history.db"
TRADES = ROOT / "portfolio_trades_audit.csv"
EQUITY = ROOT / "portfolio_equity_audit.csv"
OUT = ROOT / "portfolio_forensic_report_v1.txt"

HOUR = 3_600_000
TOL = D("0.00000001")
SLIP = D("0.001")
FEE = D("0.001")
INITIAL = D("10000")

def fmt(value, digits=2):
    return f"{value:+,.{digits}f}"

def utc(ms):
    return datetime.fromtimestamp(
        ms / 1000, timezone.utc
    ).strftime("%Y-%m-%d %H:%M")

def ms_from_utc(text):
    return int(
        datetime.strptime(text, "%Y-%m-%d %H:%M")
        .replace(tzinfo=timezone.utc).timestamp() * 1000
    )

def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def number(value):
    x = D(str(value))
    if not x.is_finite():
        raise ValueError("Sonlu olmayan sayi")
    return x

def main():
    if OUT.exists():
        raise FileExistsError(
            f"Mevcut raporun uzerine yazilmadi: {OUT.name}"
        )
    if not DB.is_file():
        raise FileNotFoundError(DB)

    trades = read_csv(TRADES)
    equity = read_csv(EQUITY)
    if not trades or not equity:
        raise RuntimeError("Islem veya ozsermaye CSV'si bos.")

    lines = []
    def say(text=""):
        lines.append(str(text))

    say("PORTFOLIOAI | FIYAT VE ISLEM ADLI DENETIMI V1")
    say("Kaynak: yerel long_history.db ve onceki test CSV'leri")
    say("Bu rapor borsa API'siyle bagimsiz fiyat dogrulamasi yapmaz.")
    say("Tum saatler UTC. Komisyon ve kayma: her yon %0.1.")
    say()

    # Islem saatlerinin tam eslesmesi icin sadece gerekli
    # sembol/saat verisini oku; veritabanina yazma.
    with sqlite3.connect(
        DB.as_uri() + "?mode=ro", uri=True, timeout=10
    ) as db:
        rows = db.execute("""
            SELECT symbol, open_time_ms, close_time_ms,
                   open_price, high_price, low_price, close_price
            FROM historical_candles
            WHERE interval='1h'
            ORDER BY symbol, open_time_ms
        """).fetchall()

    candles = {}
    by_symbol = defaultdict(list)
    invalid = []
    duplicates = []
    for symbol, t, end, op, hi, lo, cl in rows:
        try:
            t, end = int(t), int(end)
            op, hi, lo, cl = map(number, (op, hi, lo, cl))
            if not (
                t % HOUR == 0 and end == t + HOUR - 1
                and min(op, hi, lo, cl) > 0
                and hi >= max(op, cl)
                and lo <= min(op, cl)
            ):
                invalid.append((symbol, t))
                continue
            key = (symbol, t)
            if key in candles:
                duplicates.append(key)
                continue
            candle = (t, op, hi, lo, cl)
            candles[key] = candle
            by_symbol[symbol].append(candle)
        except (ValueError, TypeError, InvalidOperation):
            invalid.append((symbol, t))

    say("=== ARSIV YAPISI ===")
    say(f"Okunan saatlik satir: {len(rows)}")
    say(f"Gecerli benzersiz mum: {len(candles)}")
    say(f"Gecersiz mum: {len(invalid)}")
    say(f"Tekrarlanan sembol/saat: {len(duplicates)}")
    for symbol, t in invalid[:5]:
        say(f"  GECERSIZ: {symbol} {t}")
    for symbol, t in duplicates[:5]:
        say(f"  TEKRAR: {symbol} {utc(t)}")
    say()

    # CSV'deki her islemi ilgili sonraki mum acilisi
    # ve beklenen kaymali fiyatla karsilastir.
    issues = []
    trade_details = []
    closed = []
    positions = {}
    cash = INITIAL
    realized_by_symbol = defaultdict(lambda: D("0"))

    for line_no, row in enumerate(trades, start=2):
        try:
            symbol = row["symbol"]
            side = row["side"]
            execution_ms = ms_from_utc(row["execution_utc"])
            signal_ms = ms_from_utc(row["signal_candle_utc"])
            price = number(row["execution_price"])
            qty = number(row["quantity"])
            gross = number(row["gross_try"])
            fee = number(row["fee_try"])
            amount = number(row["cash_flow_try"])
            reported_pnl = number(row["realized_pnl_try"])
            reported_cash = number(row["cash_after_try"])

            candle = candles.get((symbol, execution_ms))
            if candle is None:
                issues.append(
                    f"Satir {line_no}: {symbol} islem mumu arsivde yok"
                )
                continue

            _, op, hi, lo, cl = candle
            expected_price = op * (
                1 + SLIP if side == "BUY" else 1 - SLIP
            )

            if execution_ms != signal_ms + HOUR:
                issues.append(
                    f"Satir {line_no}: sinyal/islem arasi 1 saat degil"
                )
            if abs(price - expected_price) > TOL:
                issues.append(
                    f"Satir {line_no}: kaymali fiyat uyusmuyor "
                    f"{symbol} {utc(execution_ms)}"
                )
            if abs(qty * price - gross) > TOL:
                issues.append(
                    f"Satir {line_no}: miktar x fiyat uyusmuyor"
                )
            if abs(gross * FEE - fee) > TOL:
                issues.append(
                    f"Satir {line_no}: komisyon uyusmuyor"
                )

            # Mum disi gerceklesme, kayma varsayiminin
            # OHLC araliginin disina cikmasi demektir;
            # tek basina veri hatasi kaniti degildir.
            outside = price < lo or price > hi
            move_pct = (cl / op - 1) * 100
            range_pct = (hi / lo - 1) * 100
            detail = {
                "symbol": symbol, "side": side,
                "time": utc(execution_ms),
                "open": op, "high": hi, "low": lo,
                "close": cl, "price": price,
                "outside": outside,
                "move_pct": move_pct,
                "range_pct": range_pct,
            }
            trade_details.append(detail)

            if side == "BUY":
                if symbol in positions:
                    issues.append(
                        f"Satir {line_no}: acik pozisyona ikinci alis"
                    )
                    continue
                if abs(gross + fee - amount) > TOL:
                    issues.append(
                        f"Satir {line_no}: alis nakit akisi uyusmuyor"
                    )
                cash -= gross + fee
                positions[symbol] = {
                    "qty": qty, "cost": gross + fee,
                    "time": utc(execution_ms),
                    "price": price,
                }

            elif side == "SELL":
                if symbol not in positions:
                    issues.append(
                        f"Satir {line_no}: pozisyonsuz satis"
                    )
                    continue
                entry = positions.pop(symbol)
                proceeds = gross - fee
                pnl = proceeds - entry["cost"]
                if abs(entry["qty"] - qty) > TOL:
                    issues.append(
                        f"Satir {line_no}: satilan miktar uyusmuyor"
                    )
                if abs(proceeds - amount) > TOL:
                    issues.append(
                        f"Satir {line_no}: satis nakit akisi uyusmuyor"
                    )
                if abs(pnl - reported_pnl) > TOL:
                    issues.append(
                        f"Satir {line_no}: kapanan PnL uyusmuyor"
                    )
                cash += proceeds
                realized_by_symbol[symbol] += pnl
                closed.append({
                    "symbol": symbol,
                    "buy_time": entry["time"],
                    "sell_time": utc(execution_ms),
                    "buy_price": entry["price"],
                    "sell_price": price,
                    "pnl": pnl,
                    "return_pct": pnl / entry["cost"] * 100,
                    "sell_outside": outside,
                })
            else:
                issues.append(
                    f"Satir {line_no}: bilinmeyen islem turu"
                )
                continue

            if abs(cash - reported_cash) > TOL:
                issues.append(
                    f"Satir {line_no}: islem sonrasi nakit uyusmuyor"
                )

        except (KeyError, ValueError, TypeError, InvalidOperation) as e:
            issues.append(f"Satir {line_no}: okunamayan islem: {e}")

    say("=== ISLEM / MUM ESLESMESI ===")
    say(f"CSV islem satiri: {len(trades)}")
    say(f"Arsiv mumuyla eslesen islem: {len(trade_details)}")
    say(f"Kapanan islem: {len(closed)}")
    say(f"Acik pozisyon: {len(positions)}")
    say(f"Kontrol sorunu: {len(issues)}")
    for issue in issues[:25]:
        say("  " + issue)
    if len(issues) > 25:
        say(f"  ... {len(issues)-25} sorun daha")
    say()

    say("=== EN BUYUK 15 KAPANMIS KAR ===")
    for x in sorted(
        closed, key=lambda v: v["pnl"], reverse=True
    )[:15]:
        say(
            f"{x['symbol']:<13} {x['buy_time']} -> "
            f"{x['sell_time']} | "
            f"alis={x['buy_price']} satis={x['sell_price']} | "
            f"PnL={fmt(x['pnl'])} TRY | "
            f"islem getirisi={fmt(x['return_pct'])}%"
        )
    say()

    say("=== EN BUYUK 10 KAPANMIS ZARAR ===")
    for x in sorted(closed, key=lambda v: v["pnl"])[:10]:
        say(
            f"{x['symbol']:<13} {x['buy_time']} -> "
            f"{x['sell_time']} | "
            f"PnL={fmt(x['pnl'])} TRY "
            f"({fmt(x['return_pct'])}%)"
        )
    say()

    say("=== ONETRY VE MUBARAKTRY | TUM KAPANAN ISLEMLER ===")
    for x in closed:
        if x["symbol"] in {"ONETRY", "MUBARAKTRY"}:
            say(
                f"{x['symbol']:<13} {x['buy_time']} -> "
                f"{x['sell_time']} | "
                f"alis={x['buy_price']} satis={x['sell_price']} | "
                f"PnL={fmt(x['pnl'])} TRY "
                f"({fmt(x['return_pct'])}%)"
            )
    say()

    say("=== ACIK POZISYONLAR | TAHMINI DEGER ===")
    final_ms = ms_from_utc(equity[-1]["candle_utc"])
    open_total = D("0")
    for symbol, p in sorted(positions.items()):
        candle = candles.get((symbol, final_ms))
        if candle is None:
            issues.append(
                f"Son mum eksik: {symbol} {utc(final_ms)}"
            )
            continue
        last_close = candle[4]
        estimated = p["qty"] * last_close * (1 - SLIP) * (1 - FEE)
        pnl = estimated - p["cost"]
        open_total += estimated
        say(
            f"{symbol:<13} alis={p['time']} | "
            f"alis_fiyati={p['price']} | "
            f"son_kapanis={last_close} | "
            f"tahmini_deger={estimated:.2f} TRY | "
            f"acik_PnL={fmt(pnl)} TRY"
        )
    say()

    # Mumun kendi saatlik hareketi ve mum araligi.
    # Bunlar veri hatasi degil, incelenecek adaylardir.
    hour_moves = []
    hour_ranges = []
    day_moves = []
    for symbol, sequence in by_symbol.items():
        sequence.sort(key=lambda x: x[0])
        daily = defaultdict(list)
        for t, op, hi, lo, cl in sequence:
            hour_moves.append(
                (abs((cl / op - 1) * 100),
                 (cl / op - 1) * 100, symbol, t, op, cl)
            )
            hour_ranges.append(
                ((hi / lo - 1) * 100, symbol, t, lo, hi)
            )
            daily[t // (24 * HOUR)].append((t, op, cl))

        for day, day_rows in daily.items():
            # Yalnizca tam 24 saatlik gunler.
            if len(day_rows) != 24:
                continue
            day_rows.sort()
            if any(
                day_rows[i][0] - day_rows[i-1][0] != HOUR
                for i in range(1, 24)
            ):
                continue
            first_open = day_rows[0][1]
            last_close = day_rows[-1][2]
            change = (last_close / first_open - 1) * 100
            day_moves.append(
                (abs(change), change, symbol,
                 day * 24 * HOUR, first_open, last_close)
            )

    say("=== EN BUYUK 20 SAATLIK ACILIS/KAPANIS HAREKETI ===")
    for _, pct, symbol, t, op, cl in sorted(
        hour_moves, reverse=True
    )[:20]:
        say(
            f"{symbol:<13} {utc(t)} | "
            f"acilis={op} kapanis={cl} | {fmt(pct)}%"
        )
    say()

    say("=== EN GENIS 15 SAATLIK HIGH/LOW ARALIGI ===")
    for pct, symbol, t, lo, hi in sorted(
        hour_ranges, reverse=True
    )[:15]:
        say(
            f"{symbol:<13} {utc(t)} | "
            f"low={lo} high={hi} | +{pct:.2f}%"
        )
    say()

    say("=== EN BUYUK 20 TAM GUNLUK HAREKET ===")
    for _, pct, symbol, t, op, cl in sorted(
        day_moves, reverse=True
    )[:20]:
        say(
            f"{symbol:<13} {utc(t)[:10]} | "
            f"acilis={op} kapanis={cl} | {fmt(pct)}%"
        )
    say()

    say("=== ISLEM ANINDA MUM ARALIGI DISINDA FIYAT ===")
    outside_trades = [x for x in trade_details if x["outside"]]
    say(f"Adet: {len(outside_trades)}")
    for x in outside_trades[:25]:
        say(
            f"{x['symbol']:<13} {x['time']} {x['side']} | "
            f"mum=[{x['low']}, {x['high']}] "
            f"varsayilan_islem={x['price']}"
        )
    if len(outside_trades) > 25:
        say(f"... {len(outside_trades)-25} islem daha")
    say("Not: Kayma nedeniyle mum araligi disi fiyat tek basina hata degildir.")
    say()

    say("=== KÂR YOGUNLASMASI ===")
    positives = sorted(
        (x for x in closed if x["pnl"] > 0),
        key=lambda x: x["pnl"], reverse=True
    )
    total_realized = sum(
        (x["pnl"] for x in closed), D("0")
    )
    say(f"Kapanmis toplam PnL: {fmt(total_realized)} TRY")
    for n in (1, 3, 5, 10):
        top = sum(
            (x["pnl"] for x in positives[:n]), D("0")
        )
        say(
            f"En karli {n} kapanan islemin brut kar toplami: "
            f"{fmt(top)} TRY"
        )
    say("Bu toplamlar zararli islemleri dusmez; portfoy getirisi degildir.")
    say()

    say("=== BAGIMSIZ SON BAKIYE KONTROLU ===")
    csv_cash = number(equity[-1]["cash_try"])
    csv_open = number(equity[-1]["open_value_try"])
    csv_equity = number(equity[-1]["equity_try"])
    say(f"Yeniden oynatilan nakit: {cash:.8f} TRY")
    say(f"CSV nakit: {csv_cash:.8f} TRY")
    say(f"Yeniden degerlenen acik pozisyon: {open_total:.8f} TRY")
    say(f"CSV acik pozisyon: {csv_open:.8f} TRY")
    say(f"Yeniden hesaplanan ozsermaye: {cash+open_total:.8f} TRY")
    say(f"CSV ozsermaye: {csv_equity:.8f} TRY")
    checks = {
        "Nakit": abs(cash - csv_cash) <= D("0.01"),
        "Acik deger": abs(open_total - csv_open) <= D("0.01"),
        "Ozsermaye": abs(cash + open_total - csv_equity) <= D("0.01"),
        "Acik sayisi": len(positions) == int(
            equity[-1]["open_positions"]
        ),
        "Islem/mum kontrolu": not issues,
    }
    for name, ok in checks.items():
        say(f"{name}: {'TUTTU' if ok else 'HATA'}")
    say(
        "GENEL: "
        + ("TUTTU" if all(checks.values()) else "INCELEME GEREKIYOR")
    )
    say()
    say("SONRAKI ADIM: Supheli tarih/fiyatlari borsa kaynaklariyla dogrula.")
    say("Yerel arsiv eslesmesi, bagimsiz borsa dogrulamasi degildir.")
    say("Gercek emir gonderilmedi; veritabanina yazilmadi.")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nRapor kaydedildi: {OUT}")

if __name__ == "__main__":
    main()
