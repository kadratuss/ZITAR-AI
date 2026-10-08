
import sqlite3

from research_engine import connect, init_database, now


# PortfolioAI - Research Notes
#
# Kaynak metni: knowledge tablosunda
# Ajanin kendi notu: research_notes tablosunda
#
# Bu dosya tek basina calistirildiginda yalnizca
# tablo olusturur ve mevcut kayitlari okur.
# Otomatik not uretmez, islem yapmaz.


def init_notes_database():
    init_database()

    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS research_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                knowledge_id INTEGER NOT NULL,
                note_type TEXT NOT NULL,
                content TEXT NOT NULL,
                limitations TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                created_at TEXT NOT NULL,

                FOREIGN KEY (source_id)
                    REFERENCES sources(id),

                FOREIGN KEY (knowledge_id)
                    REFERENCES knowledge(id),

                CHECK (
                    note_type IN (
                        'SUMMARY',
                        'FINDING',
                        'QUESTION',
                        'STRATEGY_HYPOTHESIS'
                    )
                ),

                CHECK (
                    status IN (
                        'DRAFT',
                        'REVIEW_REQUIRED',
                        'APPROVED',
                        'REJECTED'
                    )
                )
            )
        """)

        db.execute("""
            CREATE INDEX IF NOT EXISTS
                idx_research_notes_source
            ON research_notes(source_id)
        """)


def add_note(
    source_id,
    knowledge_id,
    note_type,
    content,
    limitations
):
    """
    Ajanin arastirma notunu DRAFT olarak kaydeder.

    Kaynak ve ozet ayni makaleye ait olmalidir.
    Finans disi kaynaklardan not olusturulmaz.
    Bu fonksiyon mevcut testte cagrilmaz.
    """

    allowed_types = {
        "SUMMARY",
        "FINDING",
        "QUESTION",
        "STRATEGY_HYPOTHESIS"
    }

    if note_type not in allowed_types:
        raise ValueError("Gecersiz not turu.")

    if not str(content).strip():
        raise ValueError("Not icerigi bos olamaz.")

    if not str(limitations).strip():
        raise ValueError(
            "Notun sinirlari belirtilmelidir."
        )

    with connect() as db:
        record = db.execute("""
            SELECT
                s.id AS source_id,
                s.status AS source_status,
                k.id AS knowledge_id
            FROM sources AS s
            JOIN knowledge AS k
                ON k.source_id = s.id
            WHERE s.id = ?
              AND k.id = ?
              AND k.topic LIKE 'Yazar ozeti%'
            LIMIT 1
        """, (
            source_id,
            knowledge_id
        )).fetchone()

        if record is None:
            raise ValueError(
                "Kaynak ve yazar ozeti eslesmiyor."
            )

        if record["source_status"] != "REVIEW_REQUIRED":
            raise ValueError(
                "Kaynak not olusturmaya uygun degil."
            )

        cursor = db.execute("""
            INSERT INTO research_notes (
                source_id,
                knowledge_id,
                note_type,
                content,
                limitations,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 'DRAFT', ?)
        """, (
            source_id,
            knowledge_id,
            note_type,
            content.strip(),
            limitations.strip(),
            now()
        ))

        return cursor.lastrowid


def get_notes_stats():
    with connect() as db:
        row = db.execute("""
            SELECT COUNT(*) AS total
            FROM research_notes
        """).fetchone()

        return row["total"]


def show_available_abstracts():
    with connect() as db:
        rows = db.execute("""
            SELECT
                s.id AS source_id,
                s.title,
                s.status,
                k.id AS knowledge_id
            FROM knowledge AS k
            JOIN sources AS s
                ON s.id = k.source_id
            WHERE k.topic LIKE 'Yazar ozeti%'
            ORDER BY s.id, k.id
        """).fetchall()

    print()
    print("KAYITLI YAZAR OZETLERI")
    print("----------------------")

    if not rows:
        print("Henuz yazar ozeti yok.")
        return

    for row in rows:
        print(
            f"Kaynak #{row['source_id']} | "
            f"Ozet #{row['knowledge_id']} | "
            f"{row['status']}"
        )
        print(row["title"])
        print()


def main():
    init_notes_database()

    print("PORTFOLIOAI - RESEARCH NOTES")
    print("----------------------------")
    print("Not tablosu hazir.")

    show_available_abstracts()

    print("ARASTIRMA NOTLARI")
    print("-----------------")
    print("Toplam not:", get_notes_stats())
    print()
    print("Bu testte yeni not olusturulmadi.")


if __name__ == "__main__":
    try:
        main()
    except (sqlite3.Error, ValueError) as error:
        print("Research Notes hatasi:", error)