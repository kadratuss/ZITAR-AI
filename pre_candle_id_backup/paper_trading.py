
import sqlite3
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "portfolio.db"

INITIAL_BALANCE = Decimal("10000.00")
COMMISSION_RATE = Decimal("0.001")

MONEY = Decimal("0.01")
QUANTITY = Decimal("0.00000001")


def now():
    return datetime.now(timezone.utc).isoformat()


def decimal_value(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Geçersiz sayısal değer")

    if not number.is_finite():
        raise ValueError("Sayı sonlu olmalıdır")

    return number


def money(value):
    return value.quantize(MONEY)


def quantity(value):
    return value.quantize(
        QUANTITY,
        rounding=ROUND_DOWN
    )


def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row

    db.execute("PRAGMA busy_timeout = 10000")
    db.execute("PRAGMA foreign_keys = ON")

    return db


def init_database():

    with connect() as db:

        db.execute("""
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY
                    CHECK (id = 1),
                balance TEXT NOT NULL,
                realized_pnl TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                quantity TEXT NOT NULL,
                cost_basis TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity TEXT NOT NULL,
                price TEXT NOT NULL,
                gross TEXT NOT NULL,
                fee TEXT NOT NULL,
                realized_pnl TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        db.execute("""
            INSERT OR IGNORE INTO account
            (id, balance, realized_pnl)
            VALUES (1, ?, ?)
        """, (
            str(INITIAL_BALANCE),
            "0.00"
        ))


def get_portfolio():

    with connect() as db:

        account = db.execute("""
            SELECT balance, realized_pnl
            FROM account
            WHERE id = 1
        """).fetchone()

        positions = db.execute("""
            SELECT symbol, quantity, cost_basis
            FROM positions
            ORDER BY symbol
        """).fetchall()

        trades = db.execute("""
            SELECT *
            FROM trades
            ORDER BY id DESC
            LIMIT 50
        """).fetchall()

    return {
        "mode": "PAPER_TRADING",
        "currency": "TRY",
        "balance": account["balance"],
        "realized_pnl": account["realized_pnl"],
        "positions": [
            dict(row) for row in positions
        ],
        "recent_trades": [
            dict(row) for row in trades
        ]
    }


def buy(symbol, amount_try, price):

    symbol = str(symbol).upper().strip()

    if not symbol.endswith("TRY"):
        raise ValueError("Yalnızca TRY pariteleri")

    amount = money(decimal_value(amount_try))
    price = decimal_value(price)

    if amount <= 0 or price <= 0:
        raise ValueError("Tutar ve fiyat pozitif olmalı")

    with connect() as db:

        db.execute("BEGIN IMMEDIATE")

        account = db.execute("""
            SELECT balance
            FROM account
            WHERE id = 1
        """).fetchone()

        balance = decimal_value(account["balance"])

        if amount > balance:
            raise ValueError("Yetersiz sanal bakiye")

        fee = money(amount * COMMISSION_RATE)

        spendable = amount - fee

        qty = quantity(spendable / price)

        if qty <= 0:
            raise ValueError("İşlem miktarı çok küçük")

        gross = money(qty * price)
        total = gross + fee

        if total > balance:
            raise ValueError("Yetersiz bakiye")

        position = db.execute("""
            SELECT quantity, cost_basis
            FROM positions
            WHERE symbol = ?
        """, (symbol,)).fetchone()

        old_qty = Decimal("0")
        old_cost = Decimal("0")

        if position:
            old_qty = decimal_value(
                position["quantity"]
            )
            old_cost = decimal_value(
                position["cost_basis"]
            )

        new_qty = old_qty + qty
        new_cost = old_cost + total

        db.execute("""
            INSERT INTO positions
            (symbol, quantity, cost_basis)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol)
            DO UPDATE SET
                quantity = excluded.quantity,
                cost_basis = excluded.cost_basis
        """, (
            symbol,
            str(new_qty),
            str(new_cost)
        ))

        db.execute("""
            UPDATE account
            SET balance = ?
            WHERE id = 1
        """, (str(balance - total),))

        db.execute("""
            INSERT INTO trades
            (
                symbol, side, quantity,
                price, gross, fee,
                realized_pnl, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            "BUY",
            str(qty),
            str(price),
            str(gross),
            str(fee),
            "0.00",
            now()
        ))

    return {
        "status": "success",
        "side": "BUY",
        "symbol": symbol,
        "quantity": str(qty),
        "price": str(price),
        "total": str(total),
        "fee": str(fee)
    }


def sell(symbol, qty, price):

    symbol = str(symbol).upper().strip()

    qty = quantity(decimal_value(qty))
    price = decimal_value(price)

    if qty <= 0 or price <= 0:
        raise ValueError("Miktar ve fiyat pozitif olmalı")

    with connect() as db:

        db.execute("BEGIN IMMEDIATE")

        position = db.execute("""
            SELECT quantity, cost_basis
            FROM positions
            WHERE symbol = ?
        """, (symbol,)).fetchone()

        if not position:
            raise ValueError("Açık pozisyon bulunamadı")

        held = decimal_value(position["quantity"])
        cost = decimal_value(position["cost_basis"])

        if qty > held:
            raise ValueError("Yetersiz coin miktarı")

        gross = money(qty * price)
        fee = money(gross * COMMISSION_RATE)

        proceeds = gross - fee

        if qty == held:
            allocated_cost = cost
        else:
            allocated_cost = money(
                cost * qty / held
            )

        pnl = proceeds - allocated_cost

        account = db.execute("""
            SELECT balance, realized_pnl
            FROM account
            WHERE id = 1
        """).fetchone()

        balance = decimal_value(account["balance"])

        realized = decimal_value(
            account["realized_pnl"]
        )

        db.execute("""
            UPDATE account
            SET balance = ?,
                realized_pnl = ?
            WHERE id = 1
        """, (
            str(balance + proceeds),
            str(realized + pnl)
        ))

        remaining = held - qty

        if remaining == 0:

            db.execute("""
                DELETE FROM positions
                WHERE symbol = ?
            """, (symbol,))

        else:

            db.execute("""
                UPDATE positions
                SET quantity = ?,
                    cost_basis = ?
                WHERE symbol = ?
            """, (
                str(remaining),
                str(cost - allocated_cost),
                symbol
            ))

        db.execute("""
            INSERT INTO trades
            (
                symbol, side, quantity,
                price, gross, fee,
                realized_pnl, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            "SELL",
            str(qty),
            str(price),
            str(gross),
            str(fee),
            str(pnl),
            now()
        ))

    return {
        "status": "success",
        "side": "SELL",
        "symbol": symbol,
        "quantity": str(qty),
        "price": str(price),
        "received": str(proceeds),
        "fee": str(fee),
        "realized_pnl": str(pnl)
    }


if __name__ == "__main__":

    init_database()

    print("PortfolioAI Sanal Islem Motoru")
    print("-----------------------------")
    print(get_portfolio())