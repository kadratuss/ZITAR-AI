from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal as D
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from collections import defaultdict
import csv
import json
import sqlite3
import time

ROOT = Path(__file__).resolve().parent
DB = ROOT / "long_history.db"
TRADES = ROOT / "portfolio_trades_audit.csv"
REPORT = ROOT / "exchange_verify_all_report_v2.txt"
DIFFS = ROOT / "exchange_verify_all_differences_v2.csv"

START = "2026-08-26 20:00"
END = "2026-09-22 19:00"
HOUR = 3_600_000
TOL = D("0.00000001")
FIELDS = ("open", "high", "low", "close")
ENDPOINT = "https://api.binance.me/api/v1/klines"

def to_ms(text):
    return int(datetime.strptime(
        text, "%Y-%m-%d %H:%M"
    ).replace(tzinfo=timezone.utc).timestamp() * 1000)

def utc(value):
    return datetime.fromtimestamp(
        value / 1000, timezone.utc
    ).strftime("%Y-%m-%d %H:%M")

def fetch(symbol, start, end):
    params = urlencode({
        "symbol": symbol,
        "interval": "1h",
        "startTime": start,
        "endTime": end + HOUR - 1,
        "limit": 1000,
    })
    req = Request(
        ENDPOINT + "?" + params,
        headers={
            "User-Agent": "PortfolioAI-Research/1.0",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=20) as response:
        payload = json.load(response)

    if isinstance(payload, dict):
        if payload.get("code") not in (None, 0, "0"):
            raise ValueError(
                f"API kodu={payload.get('code')}, "
                f"mesaj={payload.get('msg')}"
            )
        payload = payload.get("data")

    if not isinstance(payload, list):
        raise ValueError("API mum listesi donmedi")

    result = {}
    for row in payload:
        if not isinstance(row, list) or len(row) < 7:
            raise ValueError("Beklenmeyen API mum satiri")
        t = int(row[0])
        values = tuple(D(str(row[i])) for i in (1, 2, 3, 4))
        if t in result:
            raise ValueError(f"Tekrarlanan API saati: {utc(t)}")
        if not all(v.is_finite() and v > 0 for v in values):
            raise ValueError(f"Gecersiz API fiyati: {utc(t)}")
        if start <= t <= end:
            result[t] = values
    return result

def main():
    if REPORT.exists() or DIFFS.exists():
        raise FileExistsError(
            "V2 raporu zaten var; uzerine yazilmadi."
        )
    if not DB.is_file() or not TRADES.is_file():
        raise FileNotFoundError(
            "long_history.db veya portfolio_trades_audit.csv eksik"
        )

    start, end = to_ms(START), to_ms(END)
    expected = set(range(start, end + HOUR, HOUR))

    with TRADES.open(encoding="utf-8-sig", newline="") as f:
        trades = list(csv.DictReader(f))

    # Teste gercekten dahil olan pariteleri islem kaydindan
    # ve ortak donem arsivinden belirle.
    traded_symbols = {r["symbol"] for r in trades}
    trade_hours = defaultdict(set)
    for row in trades:
        trade_hours[row["symbol"]].add(
            to_ms(row["execution_utc"])
        )

    with sqlite3.connect(
        DB.as_uri() + "?mode=ro", uri=True
    ) as db:
        local = {}
        for symbol in sorted(traded_symbols):
            rows = db.execute("""
                SELECT open_time_ms, open_price, high_price,
                       low_price, close_price
                FROM historical_candles
                WHERE symbol=? AND interval='1h'
                  AND open_time_ms BETWEEN ? AND ?
                ORDER BY open_time_ms
            """, (symbol, start, end)).fetchall()
            local[symbol] = {
                int(row[0]): tuple(
                    D(str(value)) for value in row[1:]
                )
                for row in rows
            }

    lines = [
        "PORTFOLIOAI | TUM PARITELER API FIYAT DOGRULAMA V2",
        f"UTC donem: {START} .. {END}",
        f"Beklenen saat/parite: {len(expected)}",
        f"Islem kaydinda bulunan parite: {len(traded_symbols)}",
        "Yontem: Binance TR API ile yerel saatlik OHLC karsilastirmasi.",
        "Bu test hacim, spread ve emir gerceklesmesini dogrulamaz.",
        "",
    ]
    differences = []
    passed_count = 0
    failed_count = 0
    total_compared = 0
    total_trade_mismatches = 0

    for index, symbol in enumerate(sorted(traded_symbols), 1):
        print(
            f"[{index}/{len(traded_symbols)}] {symbol} kontrol ediliyor...",
            flush=True
        )
        local_rows = local[symbol]
        remote = None
        last_error = None

        for attempt in range(3):
            try:
                remote = fetch(symbol, start, end)
                break
            except (
                HTTPError, URLError, TimeoutError,
                ValueError, OSError
            ) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))

        lines.append(f"===== {symbol} =====")
        if remote is None:
            failed_count += 1
            lines.append("DURUM: API ERISIM HATASI")
            lines.append(f"Hata: {last_error}")
            lines.append("")
            continue

        common = sorted(set(local_rows) & set(remote))
        missing_local = sorted(expected - set(local_rows))
        missing_api = sorted(expected - set(remote))
        mismatched = set()
        trade_mismatches = set()
        max_pct = D("0")

        for t in common:
            for field, lv, rv in zip(
                FIELDS, local_rows[t], remote[t]
            ):
                diff = abs(lv - rv)
                pct = diff / rv * 100
                max_pct = max(max_pct, pct)
                if diff > TOL:
                    mismatched.add(t)
                    if t in trade_hours[symbol]:
                        trade_mismatches.add(t)
                    differences.append([
                        symbol, utc(t), field,
                        str(lv), str(rv),
                        str(diff), str(pct),
                        "EVET" if t in trade_hours[symbol] else "HAYIR",
                    ])

        missing_trade = [
            t for t in trade_hours[symbol]
            if t not in local_rows or t not in remote
        ]
        passed = (
            not missing_local
            and not missing_api
            and not mismatched
            and not missing_trade
        )
        total_compared += len(common)
        total_trade_mismatches += (
            len(trade_mismatches) + len(missing_trade)
        )
        if passed:
            passed_count += 1
        else:
            failed_count += 1

        lines.extend([
            f"Yerel mum: {len(local_rows)}",
            f"API mumu: {len(remote)}",
            f"Ortak mum: {len(common)}",
            f"Yerelde eksik saat: {len(missing_local)}",
            f"API'de eksik saat: {len(missing_api)}",
            f"Fiyati farkli saat: {len(mismatched)}",
            f"Islem saatinde fark/eksik: "
            f"{len(trade_mismatches) + len(missing_trade)}",
            f"En buyuk goreli OHLC farki: %{max_pct:.8f}",
            "DURUM: " + (
                "OHLC ESLESTI" if passed else "FARK VEYA EKSIK VAR"
            ),
        ])
        for t in sorted(mismatched)[:5]:
            lines.append(
                f"  FARK {utc(t)} "
                f"yerel={local_rows[t]} API={remote[t]}"
            )
        for t in missing_api[:3]:
            lines.append(f"  API EKSIK {utc(t)}")
        lines.append("")
        time.sleep(0.2)

    lines.extend([
        "===== GENEL OZET =====",
        f"Kontrol edilen parite: {len(traded_symbols)}",
        f"OHLC eslesen parite: {passed_count}",
        f"Sorunlu/dogrulanamayan parite: {failed_count}",
        f"Karsilastirilan ortak saatlik mum: {total_compared}",
        f"Islem saatinde fark/eksik: {total_trade_mismatches}",
        f"Farkli OHLC alani: {len(differences)}",
        "GENEL SONUC: " + (
            "TUM KONTROL EDILEN PARITELER ESLESTI"
            if failed_count == 0
            else "FARK VEYA ERISIM SORUNU VAR"
        ),
        "",
        "Not: Islem yapilmayan ama strateji evreninde bulunan",
        "pariteler bu surumde kontrol edilmis sayilmaz.",
        "Gercek emir gonderilmedi; veritabanina yazilmadi.",
    ])

    REPORT.write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    with DIFFS.open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.writer(f)
        writer.writerow([
            "symbol", "utc", "field", "local", "api",
            "absolute_difference", "relative_difference_pct",
            "trade_hour",
        ])
        writer.writerows(differences)

    print("\n".join(lines[-15:]))
    print(f"\nRapor: {REPORT.name}")
    print(f"Farklar: {DIFFS.name} ({len(differences)} satir)")

if __name__ == "__main__":
    main()
