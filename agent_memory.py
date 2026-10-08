
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import json

# PortfolioAI - AI Agent Hafizasi

DB_PATH = Path(__file__).resolve().parent / "agent_memory.db"


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout = 10000")
    return db


def init_database():

    with connect() as db:

        # Piyasa gozlemleri
        db.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                price TEXT NOT NULL,
                volume_try TEXT,
                change_percent TEXT,
                observed_at TEXT NOT NULL
            )
        """)

        # Strateji analizleri
        db.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                indicators TEXT NOT NULL,
                signal TEXT NOT NULL,
                confidence REAL,
                created_at TEXT NOT NULL
            )
        """)

        # Sanal islem deneyimleri
        db.execute("""
            CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER UNIQUE NOT NULL,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                strategy_version TEXT NOT NULL,
                market_context TEXT NOT NULL,
                realized_pnl TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # Ogrenme modeli surumleri
        db.execute("""
            CREATE TABLE IF NOT EXISTS model_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                version TEXT NOT NULL,
                parameters TEXT NOT NULL,
                metrics TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(strategy, version)
            )
        """)


def save_observation(
    symbol,
    price,
    volume_try=None,
    change_percent=None
):

    with connect() as db:

        cursor = db.execute("""
            INSERT INTO observations (
                symbol,
                price,
                volume_try,
                change_percent,
                observed_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            str(symbol).upper(),
            str(price),
            str(volume_try) if volume_try is not None else None,
            str(change_percent) if change_percent is not None else None,
            now()
        ))

        return cursor.lastrowid


def save_analysis(
    symbol,
    strategy,
    indicators,
    signal,
    confidence=None,
    strategy_version="1.0"
):

    if signal not in ("BUY", "SELL", "HOLD"):
        raise ValueError("Gecersiz analiz sinyali")

    if confidence is not None:
        confidence = float(confidence)

        if not 0 <= confidence <= 1:
            raise ValueError("Guven degeri 0-1 arasinda olmali")

    with connect() as db:

        cursor = db.execute("""
            INSERT INTO analyses (
                symbol,
                strategy,
                strategy_version,
                indicators,
                signal,
                confidence,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            str(symbol).upper(),
            strategy,
            strategy_version,
            json.dumps(indicators, ensure_ascii=False),
            signal,
            confidence,
            now()
        ))

        return cursor.lastrowid


def save_experience(
    trade_id,
    symbol,
    strategy,
    market_context,
    realized_pnl,
    strategy_version="1.0"
):

    with connect() as db:

        cursor = db.execute("""
            INSERT INTO experiences (
                trade_id,
                symbol,
                strategy,
                strategy_version,
                market_context,
                realized_pnl,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id,
            str(symbol).upper(),
            strategy,
            strategy_version,
            json.dumps(market_context, ensure_ascii=False),
            str(realized_pnl),
            now()
        ))

        return cursor.lastrowid


def get_memory_stats():

    with connect() as db:

        observations = db.execute(
            "SELECT COUNT(*) FROM observations"
        ).fetchone()[0]

        analyses = db.execute(
            "SELECT COUNT(*) FROM analyses"
        ).fetchone()[0]

        experiences = db.execute(
            "SELECT COUNT(*) FROM experiences"
        ).fetchone()[0]

        models = db.execute(
            "SELECT COUNT(*) FROM model_versions"
        ).fetchone()[0]

    return {
        "observations": observations,
        "analyses": analyses,
        "experiences": experiences,
        "model_versions": models
    }


if __name__ == "__main__":

    init_database()

    print("PortfolioAI - AI Agent Hafizasi")
    print("------------------------------")
    print(get_memory_stats())