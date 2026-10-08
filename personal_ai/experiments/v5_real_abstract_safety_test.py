import sqlite3
from pathlib import Path

import bridge_v5_test as v5
import real_model_v2_bridge_test as bridge


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATABASE = PROJECT_DIR / "research.db"
SOURCE_ID = 11
EXPECTED = "REVIEW"


def main():
    connection = sqlite3.connect(
        f"file:{DATABASE.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        rows = connection.execute(
            """
            SELECT content
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
            f"Kaynak 11 icin tek metin bekleniyordu; "
            f"bulunan kayit: {len(rows)}"
        )

    text = rows[0][0].strip()

    print("PERSONAL AI - V5 GERCEK OZET GUVENLIK TESTI")
    print("=" * 60)
    print("Kaynak:", SOURCE_ID)
    print("Beklenen karar:", EXPECTED)
    print("V5 kodunda degisiklik: YOK")
    print("Veritabani: SADECE OKUMA")
    print("Strateji ve alim-satim: KAPALI")
    print("\nKAYNAK METNI:\n", text)

    model_result = bridge.e2e.extract_real_model(text)
    result = v5.check_v5(text, model_result)

    print("\nHam model cevaplari:", model_result["raw"])
    print("Ilk dort kapi:", model_result["status"])
    print("Ilk kapi gerekceleri:", model_result["reasons"])
    print("V5 karar:", result["status"])
    print("V5 asama:", result["stage"])
    print("V5 gerekceler:", result["reasons"])
    print(
        "TEST:",
        "PASS" if result["status"] == EXPECTED else "FAIL",
    )
    print(
        "\nNOT: Bu tek kaynak ozetiyle yapilan dar kapsamli "
        "bir guvenlik kontroludur."
    )
    print("Bilimsel dogrulama veya genel guvenilirlik kaniti degildir.")


if __name__ == "__main__":
    main()