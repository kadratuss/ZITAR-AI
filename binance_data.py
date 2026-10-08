
import requests
from datetime import datetime, timezone

BASE_URL = "https://api.binance.me"

def get_btc_price():

    url = BASE_URL + "/api/v3/trades"

    response = requests.get(
        url,
        params={
            "symbol": "BTCTRY",
            "limit": 1
        },
        timeout=10
    )

    response.raise_for_status()

    result = response.json()

    # API liste veya sozluk dondurebilir
    if isinstance(result, list):
        trades = result

    elif isinstance(result, dict):
        if result.get("code") not in (None, 0):
            raise ValueError(
                f"Binance API hatasi: {result}"
            )

        trades = result.get("data", [])

    else:
        raise ValueError("Beklenmeyen API yaniti")

    if not isinstance(trades, list) or not trades:
        raise ValueError("Islem verisi bulunamadi")

    price = trades[0]["price"]

    return {
        "symbol": "BTC/TRY",
        "price": price,
        "currency": "TRY",
        "source": "Binance TR",
        "received_at": datetime.now(
            timezone.utc
        ).isoformat()
    }


if __name__ == "__main__":

    try:
        data = get_btc_price()

        print("PortfolioAI - Binance TR")
        print("------------------------")
        print("Parite:", data["symbol"])
        print(
            "Son islem fiyati:",
            data["price"],
            "TRY"
        )
        print("Kaynak:", data["source"])
        print("Alinma zamani:", data["received_at"])

    except Exception as error:
        print("Baglanti hatasi:", error)