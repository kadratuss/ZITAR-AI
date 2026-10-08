
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

from paper_trading import init_database, get_portfolio
from market_engine import get_market_data


INITIAL_CAPITAL = Decimal("10000.00")


def to_decimal(value):
    try:
        number = Decimal(str(value))

        if not number.is_finite():
            raise ValueError("Gecersiz sayi")

        return number

    except (InvalidOperation, TypeError):
        raise ValueError("Gecersiz sayisal deger")


def get_portfolio_valuation():

    init_database()

    portfolio = get_portfolio()

    balance = to_decimal(portfolio["balance"])

    realized_pnl = to_decimal(
        portfolio["realized_pnl"]
    )

    positions = portfolio["positions"]

    # Acik pozisyon yoksa piyasa verisi gerekmez.
    if not positions:

        return {
            "mode": "PAPER_TRADING",
            "currency": "TRY",
            "initial_capital": str(INITIAL_CAPITAL),
            "balance": str(balance),
            "positions_value": "0.00",
            "total_equity": str(balance),
            "realized_pnl": str(realized_pnl),
            "unrealized_pnl": "0.00",
            "total_pnl": str(
                balance - INITIAL_CAPITAL
            ),
            "open_positions": 0,
            "positions": [],
            "priced_at": None,
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat()
        }

    # Binance TR piyasa verilerini al.
    market_data = get_market_data()

    prices = {}

    for item in market_data["pairs"]:

        symbol = item["symbol"]

        prices[symbol] = to_decimal(
            item["price"]
        )

    positions_value = Decimal("0")
    unrealized_pnl = Decimal("0")

    valued_positions = []

    for position in positions:

        symbol = position["symbol"]

        qty = to_decimal(
            position["quantity"]
        )

        cost = to_decimal(
            position["cost_basis"]
        )

        # Fiyat bulunamazsa yanlis portfoy
        # degeri gostermek yerine hata ver.
        if symbol not in prices:
            raise ValueError(
                f"{symbol} icin guncel fiyat bulunamadi"
            )

        current_price = prices[symbol]

        market_value = qty * current_price

        pnl = market_value - cost

        pnl_percent = (
            pnl / cost * Decimal("100")
            if cost > 0
            else Decimal("0")
        )

        positions_value += market_value

        unrealized_pnl += pnl

        valued_positions.append({
            "symbol": symbol,
            "quantity": str(qty),
            "cost_basis": str(cost),
            "current_price": str(current_price),
            "market_value": str(
                market_value.quantize(
                    Decimal("0.01")
                )
            ),
            "unrealized_pnl": str(
                pnl.quantize(
                    Decimal("0.01")
                )
            ),
            "unrealized_pnl_percent": str(
                pnl_percent.quantize(
                    Decimal("0.01")
                )
            )
        })

    total_equity = balance + positions_value

    total_pnl = total_equity - INITIAL_CAPITAL

    return {
        "mode": "PAPER_TRADING",
        "currency": "TRY",
        "initial_capital": str(INITIAL_CAPITAL),
        "balance": str(balance),
        "positions_value": str(
            positions_value.quantize(
                Decimal("0.01")
            )
        ),
        "total_equity": str(
            total_equity.quantize(
                Decimal("0.01")
            )
        ),
        "realized_pnl": str(realized_pnl),
        "unrealized_pnl": str(
            unrealized_pnl.quantize(
                Decimal("0.01")
            )
        ),
        "total_pnl": str(
            total_pnl.quantize(
                Decimal("0.01")
            )
        ),
        "open_positions": len(
            valued_positions
        ),
        "positions": valued_positions,
        "priced_at": market_data["received_at"],
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat()
    }


if __name__ == "__main__":

    try:

        result = get_portfolio_valuation()

        print()
        print("PortfolioAI - Portfoy Degerleme")
        print("--------------------------------")

        print(
            "Sanal bakiye:",
            result["balance"],
            "TRY"
        )

        print(
            "Pozisyon degeri:",
            result["positions_value"],
            "TRY"
        )

        print(
            "Toplam portfoy:",
            result["total_equity"],
            "TRY"
        )

        print(
            "Gerceklesen kar/zarar:",
            result["realized_pnl"],
            "TRY"
        )

        print(
            "Gerceklesmemis kar/zarar:",
            result["unrealized_pnl"],
            "TRY"
        )

        print(
            "Toplam kar/zarar:",
            result["total_pnl"],
            "TRY"
        )

        print(
            "Acik pozisyon:",
            result["open_positions"]
        )

        for position in result["positions"]:

            print()
            print(
                "Parite:",
                position["symbol"]
            )

            print(
                "Guncel fiyat:",
                position["current_price"]
            )

            print(
                "Piyasa degeri:",
                position["market_value"]
            )

            print(
                "Kar/Zarar:",
                position["unrealized_pnl"]
            )

    except Exception as error:

        print(
            "Portfoy degerleme hatasi:",
            error
        )