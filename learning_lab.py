# PortfolioAI - Ayri ogrenme altyapisi
# Bu dosya calisan ajana veya mevcut veritabanlarina dokunmaz.

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "learning_lab.db"


def init_database():
    with sqlite3.connect(DB_PATH, timeout=10) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                published_at TEXT,
                collected_at TEXT NOT NULL,
                content_hash TEXT UNIQUE,
                content TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                training_period TEXT NOT NULL,
                test_period TEXT NOT NULL,
                metrics_json TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS level_progress (
                level INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'LOCKED',
                evidence_json TEXT,
                updated_at TEXT NOT NULL
            )
        """)


if __name__ == "__main__":
    init_database()
    print("OGRENME LABORATUVARI HAZIR:", DB_PATH)
