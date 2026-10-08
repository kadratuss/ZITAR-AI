
import requests
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

BASE_URL = "https://api.binance.me"
TOP_N = 20


def get_market_data():
    url = BASE_URL + "/api/v3/ticker/24hr"

    response = requests.get(
        url,
        timeout=20
    )

    response.raise_for_status()
    result = response.json()

    if isinstance(result, dict):
        if result.get("code") not in (None, 0):
            raise ValueError(
                f"API hatasi: {result}"
            )
        result = result.get("data", [])

    if not isinstance(result, list):
        raise ValueError(
            "Beklenmeyen API yaniti"
        )

    markets = []

    for item in result:
        try:
            symbol = item["symbol"]

            if not symbol.endswith("TRY"):
                continue

            price = Decimal(str(item["lastPrice"]))
            volume = Decimal(str(item["quoteVolume"]))
            change = Decimal(
                str(item["priceChangePercent"])
            )

            if price <= 0 or volume <= 0:
                continue

            markets.append({
                "symbol": symbol,
                "price": float(price),
                "volume_try": float(volume),
                "change_percent": float(change)
            })

        except (
            KeyError,
            ValueError,
            TypeError,
            InvalidOperation
        ):
            continue

    markets.sort(
        key=lambda x: x["volume_try"],
        reverse=True
    )

    return {
        "source": "Binance TR",
        "market": "Spot TRY",
        "selection": "24h quote volume",
        "requested_count": TOP_N,
        "count": min(TOP_N, len(markets)),
        "received_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "pairs": markets[:TOP_N]
    }


if __name__ == "__main__":
    try:
        data = get_market_data()

        print("PortfolioAI - Piyasa Motoru")
        print("--------------------------")
        print("Bulunan parite:", data["count"])
        print()

        for index, pair in enumerate(
            data["pairs"], start=1
        ):
            print(
                f"{index:02d}. "
                f"{pair['symbol']:12} "
                f"Fiyat: {pair['price']:,.4f} "
                f"Hacim: {pair['volume_try']:,.0f} TRY "
                f"Degisim: %{pair['change_percent']:+.2f}"
            )

    except Exception as error:
        print("Piyasa motoru hatasi:", error)