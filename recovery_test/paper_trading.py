import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path

# YALNIZCA recovery_test klasorundeki sanal veritabani.
DB_PATH = Path(__file__).resolve().parent / "agent_portfolio.db"

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
        raise ValueError("Gecersiz sayisal deger")

    if not number.is_finite():
        raise ValueError("Sayi sonlu olmali")

    return number


def money(value):
    return value.quantize(MONEY)


def quantity(value):
    return value.quantize(QUANTITY, rounding=ROUND_DOWN)


def valid_candle_id(candle_id):
    if isinstance(candle_id, bool) or not isinstance(candle_id, int):
        raise ValueError("candle_id tam sayi olmali")

    if candle_id <= 0:
        raise ValueError("candle_id pozitif olmali")

    return candle_id


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
                id INTEGER PRIMARY KEY CHECK (id = 1),
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
                created_at TEXT NOT NULL,
                candle_id INTEGER
            )
        """)

        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(trades)")
        }

        # Eski test kopyasindaki islemler NULL kalir.
        # Gecmise donuk mum kimligi uydurulmaz.
        if "candle_id" not in columns:
            db.execute(
                "ALTER TABLE trades ADD COLUMN candle_id INTEGER"
            )

        db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_trades_unique_candle_id
            ON trades(candle_id)
            WHERE candle_id IS NOT NULL
        """)

        db.execute("""
            INSERT OR IGNORE INTO account
            (id, balance, realized_pnl)
            VALUES (1, ?, ?)
        """, (str(INITIAL_BALANCE), "0.00"))


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
        "mode": "PAPER_TRADING_TEST",
        "currency": "TRY",
        "balance": account["balance"],
        "realized_pnl": account["realized_pnl"],
        "positions": [dict(row) for row in positions],
        "recent_trades": [dict(row) for row in trades],
    }


def ensure_unused_candle(db, candle_id):
    existing = db.execute(
        "SELECT id, side FROM trades WHERE candle_id = ?",
        (candle_id,),
    ).fetchone()

    if existing is not None:
        raise RuntimeError(
            f"Bu mum icin islem zaten kayitli: "
            f"candle_id={candle_id}, "
            f"trade_id={existing['id']}, "
            f"side={existing['side']}"
        )


def buy(symbol, amount_try, price, candle_id):
    candle_id = valid_candle_id(candle_id)
    symbol = str(symbol).upper().strip()

    if not symbol.endswith("TRY"):
        raise ValueError("Yalnizca TRY pariteleri")

    amount = money(decimal_value(amount_try))
    price = decimal_value(price)

    if amount <= 0 or price <= 0:
        raise ValueError("Tutar ve fiyat pozitif olmali")

    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        ensure_unused_candle(db, candle_id)

        account = db.execute("""
            SELECT balance FROM account WHERE id = 1
        """).fetchone()

        balance = decimal_value(account["balance"])

        if amount > balance:
            raise ValueError("Yetersiz sanal bakiye")

        fee = money(amount * COMMISSION_RATE)
        spendable = amount - fee
        qty = quantity(spendable / price)

        if qty <= 0:
            raise ValueError("Islem miktari cok kucuk")

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

        if position is not None:
            old_qty = decimal_value(position["quantity"])
            old_cost = decimal_value(position["cost_basis"])

        new_qty = old_qty + qty
        new_cost = old_cost + total

        db.execute("""
            INSERT INTO positions (symbol, quantity, cost_basis)
            VALUES (?, ?, ?)
            ON CONFLICT(symbol)
            DO UPDATE SET
                quantity = excluded.quantity,
                cost_basis = excluded.cost_basis
        """, (symbol, str(new_qty), str(new_cost)))

        db.execute("""
            UPDATE account SET balance = ? WHERE id = 1
        """, (str(balance - total),))

        cursor = db.execute("""
            INSERT INTO trades (
                symbol, side, quantity, price, gross, fee,
                realized_pnl, created_at, candle_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, "BUY", str(qty), str(price),
            str(gross), str(fee), "0.00", now(), candle_id,
        ))

        trade_id = cursor.lastrowid

    return {
        "status": "success",
        "trade_id": trade_id,
        "candle_id": candle_id,
        "side": "BUY",
        "symbol": symbol,
        "quantity": str(qty),
        "price": str(price),
        "total": str(total),
        "fee": str(fee),
    }


def sell(symbol, qty, price, candle_id):
    candle_id = valid_candle_id(candle_id)
    symbol = str(symbol).upper().strip()
    qty = quantity(decimal_value(qty))
    price = decimal_value(price)

    if qty <= 0 or price <= 0:
        raise ValueError("Miktar ve fiyat pozitif olmali")

    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        ensure_unused_candle(db, candle_id)

        position = db.execute("""
            SELECT quantity, cost_basis
            FROM positions
            WHERE symbol = ?
        """, (symbol,)).fetchone()

        if position is None:
            raise ValueError("Acik pozisyon bulunamadi")

        held = decimal_value(position["quantity"])
        cost = decimal_value(position["cost_basis"])

        if qty > held:
            raise ValueError("Yetersiz coin miktari")

        gross = money(qty * price)
        fee = money(gross * COMMISSION_RATE)
        proceeds = gross - fee

        if qty == held:
            allocated_cost = cost
        else:
            allocated_cost = money(cost * qty / held)

        pnl = proceeds - allocated_cost

        account = db.execute("""
            SELECT balance, realized_pnl
            FROM account
            WHERE id = 1
        """).fetchone()

        balance = decimal_value(account["balance"])
        realized = decimal_value(account["realized_pnl"])

        db.execute("""
            UPDATE account
            SET balance = ?, realized_pnl = ?
            WHERE id = 1
        """, (
            str(balance + proceeds),
            str(realized + pnl),
        ))

        remaining = held - qty

        if remaining == 0:
            db.execute(
                "DELETE FROM positions WHERE symbol = ?",
                (symbol,),
            )
        else:
            db.execute("""
                UPDATE positions
                SET quantity = ?, cost_basis = ?
                WHERE symbol = ?
            """, (
                str(remaining),
                str(cost - allocated_cost),
                symbol,
            ))

        cursor = db.execute("""
            INSERT INTO trades (
                symbol, side, quantity, price, gross, fee,
                realized_pnl, created_at, candle_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol, "SELL", str(qty), str(price),
            str(gross), str(fee), str(pnl), now(), candle_id,
        ))

        trade_id = cursor.lastrowid

    return {
        "status": "success",
        "trade_id": trade_id,
        "candle_id": candle_id,
        "side": "SELL",
        "symbol": symbol,
        "quantity": str(qty),
        "price": str(price),
        "received": str(proceeds),
        "fee": str(fee),
        "realized_pnl": str(pnl),
    }


if __name__ == "__main__":
    init_database()
    print("PortfolioAI - TEST Sanal Islem Motoru")
    print("Veritabani:", DB_PATH)
    print(get_portfolio())