import re
import sqlite3
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATABASE = PROJECT_DIR / "research.db"
SOURCE_ID = 11


def main():
    connection = sqlite3.connect(
        f"file:{DATABASE.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        rows = connection.execute(
            """
            SELECT id, topic, content
            FROM knowledge
            WHERE source_id = ?
              AND content IS NOT NULL
              AND TRIM(content) != ''
            ORDER BY id
            """,
            (SOURCE_ID,),
        ).fetchall()
    finally:
        connection.close()

    if len(rows) != 1:
        raise RuntimeError(
            f"Kaynak {SOURCE_ID} icin tek metin bekleniyordu; "
            f"bulunan kayit: {len(rows)}"
        )

    knowledge_id, topic, text = rows[0]

    # Bu ozet icin basit cumle ayirma.
    # Genel amacli akademik PDF ayracisi degildir.
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    print("PERSONAL AI - KAYNAK 11 CUMLE ENVANTERI")
    print("=" * 60)
    print("Kaynak ID:", SOURCE_ID)
    print("Bilgi kaydi ID:", knowledge_id)
    print("Konu:", topic)
    print("Cumle sayisi:", len(sentences))
    print("Veritabani: SADECE OKUMA")
    print("Ollama: CAGIRILMADI")
    print("V5: DEGISTIRILMEDI")
    print()

    for number, sentence in enumerate(sentences, 1):
        print(f"[{number}] {sentence}")
        print()

    print("NOT: Cumle numaralari bu kayit icin gecerlidir.")
    print("Henuz hicbir cumleye READY/REVIEW karari verilmedi.")


if __name__ == "__main__":
    main()