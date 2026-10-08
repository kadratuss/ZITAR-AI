
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

# PortfolioAI - Research Engine
# Arastirma ve finansal bilgi tabani

DB_PATH = Path(__file__).resolve().parent / "research.db"


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout = 10000")
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_database():

    with connect() as db:

        # Kitaplar, makaleler ve diger kaynaklar
        db.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT,
                source_type TEXT NOT NULL,
                url TEXT,
                publication_date TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TEXT NOT NULL
            )
        """)

        # Kaynaklardan elde edilen bilgiler
        db.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                page_reference TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(source_id)
                    REFERENCES sources(id)
            )
        """)

        # Yeni strateji fikirleri
        db.execute("""
            CREATE TABLE IF NOT EXISTS strategy_ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                parameters TEXT NOT NULL,
                source_id INTEGER,
                status TEXT NOT NULL DEFAULT 'RESEARCH',
                created_at TEXT NOT NULL,
                FOREIGN KEY(source_id)
                    REFERENCES sources(id)
            )
        """)

        # Deneysel strateji testleri
        db.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER NOT NULL,
                dataset TEXT NOT NULL,
                parameters TEXT NOT NULL,
                metrics TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(strategy_id)
                    REFERENCES strategy_ideas(id)
            )
        """)


def add_source(
    title,
    author,
    source_type,
    url=None,
    publication_date=None
):

    if not str(title).strip():
        raise ValueError("Kaynak basligi bos olamaz")

    allowed_types = (
        "BOOK",
        "PAPER",
        "ARTICLE",
        "DOCUMENTATION"
    )

    source_type = str(source_type).upper()

    if source_type not in allowed_types:
        raise ValueError("Gecersiz kaynak turu")

    if url:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            raise ValueError("Gecersiz kaynak adresi")

        if not parsed.netloc:
            raise ValueError("Gecersiz kaynak adresi")

    with connect() as db:

        cursor = db.execute("""
            INSERT INTO sources (
                title,
                author,
                source_type,
                url,
                publication_date,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            title,
            author,
            source_type,
            url,
            publication_date,
            now()
        ))

        return cursor.lastrowid


def add_knowledge(
    source_id,
    topic,
    content,
    page_reference=None
):

    if not str(content).strip():
        raise ValueError("Bilgi icerigi bos olamaz")

    with connect() as db:

        cursor = db.execute("""
            INSERT INTO knowledge (
                source_id,
                topic,
                content,
                page_reference,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            source_id,
            topic,
            content,
            page_reference,
            now()
        ))

        return cursor.lastrowid


def add_strategy(
    name,
    description,
    parameters,
    source_id=None
):

    with connect() as db:

        cursor = db.execute("""
            INSERT INTO strategy_ideas (
                name,
                description,
                parameters,
                source_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            name,
            description,
            json.dumps(
                parameters,
                ensure_ascii=False
            ),
            source_id,
            now()
        ))

        return cursor.lastrowid


def add_experiment(
    strategy_id,
    dataset,
    parameters,
    metrics,
    status="PENDING"
):

    with connect() as db:

        cursor = db.execute("""
            INSERT INTO experiments (
                strategy_id,
                dataset,
                parameters,
                metrics,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            strategy_id,
            dataset,
            json.dumps(
                parameters,
                ensure_ascii=False
            ),
            json.dumps(
                metrics,
                ensure_ascii=False
            ),
            status,
            now()
        ))

        return cursor.lastrowid


def get_research_stats():

    with connect() as db:

        tables = (
            "sources",
            "knowledge",
            "strategy_ideas",
            "experiments"
        )

        result = {}

        for table in tables:

            count = db.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            result[table] = count

        return result


if __name__ == "__main__":

    init_database()

    print("PortfolioAI - Research Engine")
    print("-----------------------------")

    stats = get_research_stats()

    for name, count in stats.items():
        print(f"{name}: {count}")