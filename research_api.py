
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/api/research", tags=["research"])
DATABASE = Path(__file__).resolve().parent / "research.db"


@router.get("/notes")
def list_research_notes():
    if not DATABASE.is_file():
        raise HTTPException(
            status_code=503,
            detail="Arastirma veritabani bulunamadi",
        )

    try:
        with sqlite3.connect(
            DATABASE.resolve().as_uri() + "?mode=ro",
            uri=True,
        ) as db:
            db.row_factory = sqlite3.Row

            rows = db.execute(
                """
                SELECT
                    n.id,
                    n.source_id,
                    n.knowledge_id,
                    n.note_type,
                    n.status,
                    n.content,
                    n.limitations,
                    n.created_at,
                    s.title AS source_title,
                    s.url AS source_url
                FROM research_notes AS n
                JOIN sources AS s ON s.id = n.source_id
                ORDER BY n.created_at DESC, n.id DESC
                """
            ).fetchall()

    except sqlite3.Error:
        raise HTTPException(
            status_code=503,
            detail="Arastirma notlari okunamadi",
        )

    return {
        "notes": [dict(row) for row in rows],
        "count": len(rows),
        "disclaimer": (
            "Arastirma notlari yatirim tavsiyesi veya "
            "alim-satim onayi degildir. DRAFT notlar "
            "dogrulanmis bulgu olarak yorumlanmamalidir."
        ),
    }