from __future__ import annotations

import json
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import requests


BASE = Path(__file__).resolve().parent

MASTER_STATE = BASE / "zitar_master_portfolio_v1.json"

BOOK_API = "https://api.binance.me/api/v3/ticker/bookTicker"

MONEY = Decimal("0.01")


def D(value) -> Decimal:
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(
        MONEY,
        rounding=ROUND_HALF_UP
    )


def load_json(path: Path) -> dict:
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def get_json(url, params=None):

    last = None
    delays = (1, 2, 4, 8)

    for attempt in range(5):

        try:

            r = requests.get(
                url,
                params=params,
                timeout=20,
                headers={
                    "User-Agent":
                        "PortfolioAI-Paper-V3/1.0"
                },
            )

            r.raise_for_status()

            return r.json()

        except Exception as exc:

            last = exc

            if attempt < 4:
                time.sleep(
                    delays[attempt]
                )

    raise RuntimeError(
        "HTTP/API failed after 5 attempts: "
        f"{last}"
    )


def fetch_book_snapshot(
    universe: list[str]
) -> dict[str, dict[str, Decimal]]:

    data = get_json(BOOK_API)

    if not isinstance(data, list):
        raise RuntimeError(
            "bookTicker list donmedi"
        )

    wanted = set(universe)

    result = {}

    for row in data:

        symbol = row.get("symbol")

        if symbol not in wanted:
            continue

        bid = D(row["bidPrice"])
        ask = D(row["askPrice"])

        if bid <= 0 or ask <= 0:
            raise RuntimeError(
                f"Gecersiz book price: {symbol}"
            )

        if ask < bid:
            raise RuntimeError(
                f"Crossed book: {symbol}"
            )

        result[symbol] = {
            "bid": bid,
            "ask": ask,
        }

    missing = wanted - set(result)

    if missing:
        raise RuntimeError(
            "bookTicker eksik: "
            + ",".join(
                sorted(missing)
            )
        )

    return result


def main():

    print(
        "ZITAR MASTER MARK-TO-MARKET V1"
    )

    print(
        "DRY RUN ONLY • "
        "NO MASTER WRITE • "
        "NO V3 WRITE • "
        "NO PAPER ORDER • "
        "NO REAL ORDER"
    )

    print()

    if not MASTER_STATE.exists():
        raise SystemExit(
            "FAIL: master state not found"
        )

    master = load_json(
        MASTER_STATE
    )

    if master.get("schema") != \
            "ZITAR_MASTER_PORTFOLIO_V1":

        raise SystemExit(
            "FAIL: unexpected master schema"
        )

    account = master.get(
        "account",
        {}
    )

    positions = account.get(
        "positions",
        {}
    )

    cash = D(
        account.get(
            "cash_try",
            "0"
        )
    )

    stored_equity = D(
        account.get(
            "equity_try",
            "0"
        )
    )

    print(
        "master period:",
        master.get(
            "current_period",
            {}
        ).get(
            "period_id"
        )
    )

    print(
        "stored cash:",
        money(cash),
        "TRY"
    )

    print(
        "stored equity:",
        money(stored_equity),
        "TRY"
    )

    print(
        "open positions:",
        len(positions)
    )

    if not positions:

        print()
        print(
            "No open positions."
        )

        print(
            "Master modified:",
            False
        )

        print(
            "V3 modified:",
            False
        )

        print(
            "Real order:",
            False
        )

        print(
            "STATUS: PASS"
        )

        return

    symbols = sorted(
        positions.keys()
    )

    books = fetch_book_snapshot(
        symbols
    )

    total_market_value = Decimal("0")
    total_unrealized = Decimal("0")

    print()
    print("LIVE BID MARKS")
    print("--------------")

    for symbol in symbols:

        pos = positions[symbol]

        quantity = D(
            pos["quantity"]
        )

        total_cost = D(
            pos["total_cost_try"]
        )

        stored_mark = D(
            pos.get(
                "last_mark_price",
                pos[
                    "entry_reference_price"
                ]
            )
        )

        bid = books[
            symbol
        ]["bid"]

        ask = books[
            symbol
        ]["ask"]

        market_value = (
            quantity *
            bid
        )

        unrealized = (
            market_value -
            total_cost
        )

        total_market_value += \
            market_value

        total_unrealized += \
            unrealized

        print()
        print(
            "symbol:",
            symbol
        )

        print(
            "quantity:",
            quantity
        )

        print(
            "stored mark:",
            stored_mark
        )

        print(
            "live bid:",
            bid
        )

        print(
            "live ask:",
            ask
        )

        print(
            "live market value:",
            money(
                market_value
            ),
            "TRY"
        )

        print(
            "live unrealized P/L:",
            money(
                unrealized
            ),
            "TRY"
        )

    live_equity = (
        cash +
        total_market_value
    )

    equity_delta = (
        live_equity -
        stored_equity
    )

    print()
    print("MASTER LIVE VALUATION")
    print("---------------------")

    print(
        "cash:",
        money(cash),
        "TRY"
    )

    print(
        "live position value:",
        money(
            total_market_value
        ),
        "TRY"
    )

    print(
        "live unrealized P/L:",
        money(
            total_unrealized
        ),
        "TRY"
    )

    print(
        "stored equity:",
        money(
            stored_equity
        ),
        "TRY"
    )

    print(
        "live equity:",
        money(
            live_equity
        ),
        "TRY"
    )

    print(
        "equity delta:",
        money(
            equity_delta
        ),
        "TRY"
    )

    print()
    print(
        "Master modified:",
        False
    )

    print(
        "V3 modified:",
        False
    )

    print(
        "Paper order:",
        False
    )

    print(
        "Real order:",
        False
    )

    print(
        "STATUS: PASS"
    )


if __name__ == "__main__":
    main()
