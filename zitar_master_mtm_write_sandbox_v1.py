from __future__ import annotations

import copy
import json
import time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import requests


BASE = Path(__file__).resolve().parent

MASTER = BASE / "zitar_master_portfolio_v1.json"
SANDBOX = BASE / "zitar_master_mtm_write_sandbox_v1.json"

BOOK_API = "https://api.binance.me/api/v3/ticker/bookTicker"

MONEY = Decimal("0.01")
PCT = Decimal("0.0001")


def D(value) -> Decimal:
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(
        MONEY,
        rounding=ROUND_HALF_UP
    )


def pct(value: Decimal) -> Decimal:
    return value.quantize(
        PCT,
        rounding=ROUND_HALF_UP
    )


def load_json(path: Path) -> dict:
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def atomic_save(
    path: Path,
    data: dict
) -> None:

    payload = json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    )

    temp = path.with_name(
        path.name + ".tmp"
    )

    temp.write_text(
        payload,
        encoding="utf-8"
    )

    temp.replace(path)


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

    data = get_json(
        BOOK_API
    )

    if not isinstance(data, list):
        raise RuntimeError(
            "bookTicker list donmedi"
        )

    wanted = set(universe)
    result = {}

    for row in data:

        symbol = row.get(
            "symbol"
        )

        if symbol not in wanted:
            continue

        bid = D(
            row["bidPrice"]
        )

        ask = D(
            row["askPrice"]
        )

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

    missing = (
        wanted -
        set(result)
    )

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
        "ZITAR MASTER MTM WRITE SANDBOX V1"
    )

    print(
        "LIVE BID • SANDBOX WRITE ONLY • "
        "NO REAL MASTER WRITE • "
        "NO V3 WRITE • NO ORDER"
    )

    print()

    if not MASTER.exists():
        raise SystemExit(
            "FAIL: real master not found"
        )

    real_before_bytes = \
        MASTER.read_bytes()

    real_master = load_json(
        MASTER
    )

    if real_master.get(
        "schema"
    ) != "ZITAR_MASTER_PORTFOLIO_V1":

        raise SystemExit(
            "FAIL: unexpected master schema"
        )

    sandbox = copy.deepcopy(
        real_master
    )

    account = sandbox[
        "account"
    ]

    positions = account[
        "positions"
    ]

    cash = D(
        account["cash_try"]
    )

    stored_equity = D(
        account["equity_try"]
    )

    print(
        "stored equity:",
        money(stored_equity),
        "TRY"
    )

    print(
        "cash:",
        money(cash),
        "TRY"
    )

    print(
        "positions:",
        len(positions)
    )

    if positions:

        books = fetch_book_snapshot(
            sorted(
                positions.keys()
            )
        )

    else:
        books = {}

    market_value_total = \
        Decimal("0")

    unrealized_total = \
        Decimal("0")

    print()
    print("POSITION MARKS")
    print("--------------")

    for symbol, pos in \
            positions.items():

        quantity = D(
            pos["quantity"]
        )

        total_cost = D(
            pos["total_cost_try"]
        )

        old_mark = D(
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

        pos[
            "last_mark_price"
        ] = str(bid)

        pos[
            "market_value_try"
        ] = str(
            money(
                market_value
            )
        )

        pos[
            "unrealized_pnl_try"
        ] = str(
            money(
                unrealized
            )
        )

        market_value_total += \
            market_value

        unrealized_total += \
            unrealized

        print()
        print(
            "symbol:",
            symbol
        )

        print(
            "old mark:",
            old_mark
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
            "market value:",
            money(
                market_value
            ),
            "TRY"
        )

        print(
            "unrealized P/L:",
            money(
                unrealized
            ),
            "TRY"
        )

    equity = (
        cash +
        market_value_total
    )

    account[
        "position_market_value_try"
    ] = str(
        money(
            market_value_total
        )
    )

    account[
        "unrealized_pnl_try"
    ] = str(
        money(
            unrealized_total
        )
    )

    account[
        "equity_try"
    ] = str(
        money(
            equity
        )
    )

    account[
        "open_position_count"
    ] = len(
        positions
    )

    period = sandbox[
        "current_period"
    ]

    period[
        "current_equity_try"
    ] = str(
        money(
            equity
        )
    )

    start_equity = D(
        period[
            "start_equity_try"
        ]
    )

    if start_equity != 0:

        daily_return = (
            (
                equity -
                start_equity
            )
            /
            start_equity
            *
            Decimal("100")
        )

    else:

        daily_return = \
            Decimal("0")

    period[
        "daily_return_pct"
    ] = str(
        pct(
            daily_return
        )
    )

    # Mark-to-market yalnız değerleme yapar.
    # Realized muhasebeye dokunmamalıdır.
    real_daily_realized = \
        real_master[
            "current_period"
        ][
            "daily_realized_pnl_try"
        ]

    real_account_realized = \
        real_master[
            "account"
        ][
            "realized_pnl_try"
        ]

    real_lifetime_realized = \
        real_master[
            "lifetime"
        ][
            "total_realized_pnl_try"
        ]

    atomic_save(
        SANDBOX,
        sandbox
    )

    loaded = load_json(
        SANDBOX
    )

    identity_ok = (
        money(
            D(
                loaded[
                    "account"
                ][
                    "cash_try"
                ]
            )
            +
            D(
                loaded[
                    "account"
                ][
                    "position_market_value_try"
                ]
            )
        )
        ==
        money(
            D(
                loaded[
                    "account"
                ][
                    "equity_try"
                ]
            )
        )
    )

    period_sync_ok = (
        loaded[
            "account"
        ][
            "equity_try"
        ]
        ==
        loaded[
            "current_period"
        ][
            "current_equity_try"
        ]
    )

    realized_unchanged = (
        loaded[
            "current_period"
        ][
            "daily_realized_pnl_try"
        ]
        ==
        real_daily_realized
        and
        loaded[
            "account"
        ][
            "realized_pnl_try"
        ]
        ==
        real_account_realized
        and
        loaded[
            "lifetime"
        ][
            "total_realized_pnl_try"
        ]
        ==
        real_lifetime_realized
    )

    real_master_unchanged = (
        MASTER.read_bytes()
        ==
        real_before_bytes
    )

    print()
    print("SANDBOX RESULT")
    print("--------------")

    print(
        "position value:",
        loaded[
            "account"
        ][
            "position_market_value_try"
        ],
        "TRY"
    )

    print(
        "unrealized P/L:",
        loaded[
            "account"
        ][
            "unrealized_pnl_try"
        ],
        "TRY"
    )

    print(
        "equity:",
        loaded[
            "account"
        ][
            "equity_try"
        ],
        "TRY"
    )

    print(
        "period equity:",
        loaded[
            "current_period"
        ][
            "current_equity_try"
        ],
        "TRY"
    )

    print(
        "daily return:",
        loaded[
            "current_period"
        ][
            "daily_return_pct"
        ],
        "%"
    )

    print()
    print(
        "ACCOUNTING IDENTITY:",
        "PASS"
        if identity_ok
        else "FAIL"
    )

    print(
        "PERIOD EQUITY SYNC:",
        "PASS"
        if period_sync_ok
        else "FAIL"
    )

    print(
        "REALIZED UNCHANGED:",
        "PASS"
        if realized_unchanged
        else "FAIL"
    )

    print(
        "REAL MASTER UNCHANGED:",
        "PASS"
        if real_master_unchanged
        else "FAIL"
    )

    print()
    print(
        "sandbox:",
        SANDBOX
    )

    if not all(
        (
            identity_ok,
            period_sync_ok,
            realized_unchanged,
            real_master_unchanged,
        )
    ):
        raise SystemExit(
            "STATUS: FAIL"
        )

    print(
        "STATUS: PASS"
    )


if __name__ == "__main__":
    main()
