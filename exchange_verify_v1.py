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
REPORT = ROOT / "exchange_verify_report_v1.txt"
DIFFS = ROOT / "exchange_verify_differences_v1.csv"

SYMBOLS = ("ONETRY", "MUBARAKTRY", "BTCTRY")
START = "2026-08-26 20:00"
END = "2026-09-22 19:00"
HOUR = 3_600_000
FIELDS = ("open", "high", "low", "close")
PRICE_TOL = D("0.00000001")

# Binance TR resmi dokumanindaki iki sembol turu adresi.
ENDPOINTS = (
    "https://api.binance.me/api/v1/klines",
    "https://cloudme-tr.2meta.app/api/v1/klines",
)

def ms(text):
    return int(datetime.strptime(
        text, "%Y-%m-%d %H:%M"
    ).replace(tzinfo=timezone.utc).timestamp() * 1000)

def utc(value):
    return datetime.fromtimestamp(
        value / 1000, timezone.utc
    ).strftime("%Y-%m-%d %H:%M")

def request_klines(endpoint, symbol, start, end):
    params = urlencode({
        "symbol": symbol,
        "interval": "1h",
        "startTime": start,
        "endTime": end + HOUR - 1,
        "limit": 1000,
    })
    req = Request(
        endpoint + "?" + params,
        headers={
            "User-Agent": "PortfolioAI-Research/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urlopen(req, timeout=18) as response:
        payload = json.load(response)

    if isinstance(payload, dict):
        if payload.get("code") not in (None, 0, "0"):
            raise ValueError(
                f"API kodu={payload.get('code')} "
                f"mesaj={payload.get('msg')}"
            )
        data = payload.get("data")
    elif isinstance(payload, list):
        data = payload
    else:
        raise ValueError("Bilinmeyen API yanit bicimi")

    if not isinstance(data, list):
        raise ValueError("API mum listesi donmedi")

    parsed = {}
    for item in data:
        if not isinstance(item, list) or len(item) < 7:
            raise ValueError("Beklenmeyen mum satiri")
        t = int(item[0])
        values = tuple(D(str(item[i])) for i in (1, 2, 3, 4))
        if not all(x.is_finite() and x > 0 for x in values):
            raise ValueError("Gecersiz API fiyati")
        if t in parsed:
            raise ValueError("API ayni saati iki kez dondurdu")
        if start <= t <= end:
            parsed[t] = values
    return parsed

def main():
    if REPORT.exists() or DIFFS.exists():
        raise FileExistsError(
            "Rapor dosyasi zaten var; uzerine yazilmadi."
        )
    if not DB.is_file() or not TRADES.is_file():
        raise FileNotFoundError(
            "long_history.db veya portfolio_trades_audit.csv eksik"
        )

    start, end = ms(START), ms(END)
    expected_times = set(range(start, end + HOUR, HOUR))
    with sqlite3.connect(
        DB.as_uri() + "?mode=ro", uri=True
    ) as db:
        local = {}
        for symbol in SYMBOLS:
            rows = db.execute("""
                SELECT open_time_ms, open_price, high_price,
                       low_price, close_price
                FROM historical_candles
                WHERE symbol=? AND interval='1h'
                  AND open_time_ms BETWEEN ? AND ?
                ORDER BY open_time_ms
            """, (symbol, start, end)).fetchall()
            local[symbol] = {
                int(r[0]): tuple(D(str(x)) for x in r[1:])
                for r in rows
            }

    with TRADES.open(
        encoding="utf-8-sig", newline=""
    ) as f:
        trade_rows = list(csv.DictReader(f))

    trade_hours = defaultdict(set)
    for row in trade_rows:
        if row["symbol"] in SYMBOLS:
            trade_hours[row["symbol"]].add(
                ms(row["execution_utc"])
            )

    lines = [
        "PORTFOLIOAI | BINANCE TR BAGIMSIZ FIYAT KONTROLU V1",
        f"UTC donem: {START} .. {END}",
        "Sadece halka acik GET istekleri; API anahtari yok.",
        "Yerel arsiv ve API OHLC degerleri karsilastirilir.",
        "",
    ]
    differences = []
    all_passed = True

    for symbol in SYMBOLS:
        lines.append(f"===== {symbol} =====")
        remote = None
        chosen_endpoint = None
        errors = []

        for endpoint in ENDPOINTS:
            try:
                candidate = request_klines(
                    endpoint, symbol, start, end
                )
                # Bos veya birkac mum donduren adresi
                # tam donem dogrulamasi sayma.
                if len(candidate) < len(expected_times) * 0.90:
                    errors.append(
                        f"{endpoint}: yetersiz mum "
                        f"({len(candidate)}/{len(expected_times)})"
                    )
                    continue
                remote = candidate
                chosen_endpoint = endpoint
                break
            except (
                HTTPError, URLError, TimeoutError,
                ValueError, OSError
            ) as exc:
                errors.append(
                    f"{endpoint}: {type(exc).__name__}: {exc}"
                )
            time.sleep(0.3)

        if remote is None:
            all_passed = False
            lines.append("DURUM: DOGRULANAMADI")
            lines.extend("  " + error for error in errors)
            lines.append("")
            continue

        local_rows = local[symbol]
        common = sorted(set(local_rows) & set(remote))
        missing_local = sorted(expected_times - set(local_rows))
        missing_api = sorted(expected_times - set(remote))
        mismatched_hours = set()
        trade_mismatch = set()
        max_relative = D("0")

        for t in common:
            a, b = local_rows[t], remote[t]
            for field, lv, rv in zip(FIELDS, a, b):
                absolute = abs(lv - rv)
                relative = (
                    absolute / abs(rv) * 100
                    if rv != 0 else D("0")
                )
                max_relative = max(max_relative, relative)
                if absolute > PRICE_TOL:
                    mismatched_hours.add(t)
                    if t in trade_hours[symbol]:
                        trade_mismatch.add(t)
                    differences.append([
                        symbol, utc(t), field,
                        str(lv), str(rv),
                        str(absolute), str(relative),
                        "EVET" if t in trade_hours[symbol] else "HAYIR",
                        chosen_endpoint,
                    ])

        missing_trade = sorted(
            t for t in trade_hours[symbol]
            if t not in local_rows or t not in remote
        )
        passed = (
            not missing_local and not missing_api
            and not mismatched_hours and not missing_trade
        )
        all_passed &= passed

        lines.append(f"API adresi: {chosen_endpoint}")
        lines.append(f"Beklenen saat: {len(expected_times)}")
        lines.append(f"Yerel mum: {len(local_rows)}")
        lines.append(f"API mumu: {len(remote)}")
        lines.append(f"Ortak saat: {len(common)}")
        lines.append(f"Yerelde eksik saat: {len(missing_local)}")
        lines.append(f"API'de eksik saat: {len(missing_api)}")
        lines.append(
            f"Fiyati farkli saat: {len(mismatched_hours)}"
        )
        lines.append(
            f"Islem yapilan farkli saat: {len(trade_mismatch)}"
        )
        lines.append(
            f"Islem yapilan eksik saat: {len(missing_trade)}"
        )
        lines.append(
            f"En buyuk goreli OHLC farki: %{max_relative:.8f}"
        )
        lines.append(
            "DURUM: " + (
                "OHLC ESLESTI" if passed
                else "FARK VAR - BACKTESTI DOGRULANMIS SAYMA"
            )
        )
        for t in sorted(mismatched_hours)[:10]:
            lines.append(
                f"  FARK {utc(t)} "
                f"yerel={local_rows[t]} API={remote[t]}"
            )
        for t in missing_api[:5]:
            lines.append(f"  API EKSIK {utc(t)}")
        lines.append("")

    lines.append(
        "GENEL SONUC: " + (
            "UC PARITEDE OHLC ESLESTI"
            if all_passed
            else "EKSIK VEYA FARKLI VERI VAR; DOGRULAMA TAMAMLANMADI"
        )
    )
    lines.append(
        "Bu kontrol emir defteri, spread veya gerceklesebilirligi dogrulamaz."
    )
    lines.append(
        "Diger 18 parite bu surumde API ile karsilastirilmadi."
    )

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
            "trade_hour", "api_endpoint",
        ])
        writer.writerows(differences)

    print("\n".join(lines))
    print(f"\nRapor: {REPORT.name}")
    print(f"Farklar: {DIFFS.name} ({len(differences)} satir)")

if __name__ == "__main__":
    main()
