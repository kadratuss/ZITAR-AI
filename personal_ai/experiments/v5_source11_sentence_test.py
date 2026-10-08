import re
import sqlite3
from pathlib import Path

import bridge_v5_test as v5
import real_model_v2_bridge_test as bridge


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATABASE = PROJECT_DIR / "research.db"

# Model calistirilmadan ONCE sabitlenen beklentiler.
EXPECTED = {
    1: "REVIEW",
    2: "REVIEW",
    3: "READY",
    4: "REVIEW",
    5: "REVIEW",
    6: "REVIEW",
    7: "REVIEW",
    8: "REVIEW",
}


def get_sentences():
    connection = sqlite3.connect(
        f"file:{DATABASE.as_posix()}?mode=ro",
        uri=True,
    )
    try:
        rows = connection.execute(
            """
            SELECT content
            FROM knowledge
            WHERE source_id = 11
              AND content IS NOT NULL
              AND TRIM(content) != ''
            ORDER BY id
            """
        ).fetchall()
    finally:
        connection.close()

    if len(rows) != 1:
        raise RuntimeError(
            f"Kaynak 11 icin tek kayit bekleniyordu: {len(rows)}"
        )

    sentences = re.split(
        r"(?<=[.!?])\s+(?=[A-Z])",
        rows[0][0].strip(),
    )
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) != 8:
        raise RuntimeError(
            f"Beklenen 8 cumle, bulunan: {len(sentences)}"
        )

    return sentences


def main():
    sentences = get_sentences()

    print("PERSONAL AI - KAYNAK 11 / V5 CUMLE TESTI")
    print("=" * 60)
    print("Beklenen kararlar onceden sabitlendi.")
    print("V5 kodunda degisiklik: YOK")
    print("Veritabani: SADECE OKUMA")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0
    missed_ready = 0

    for number, text in enumerate(sentences, 1):
        expected = EXPECTED[number]

        print("\n" + "-" * 60)
        print(f"CUMLE {number}/8")
        print("Metin:", text)
        print("Beklenen:", expected)

        model_result = bridge.e2e.extract_real_model(text)
        result = v5.check_v5(text, model_result)
        actual = result["status"]

        passed += int(actual == expected)
        false_ready += int(
            actual == "READY" and expected == "REVIEW"
        )
        missed_ready += int(
            actual == "REVIEW" and expected == "READY"
        )

        print("Ham model cevaplari:", model_result["raw"])
        print("Ilk dort kapi:", model_result["status"])
        print("Ilk kapi gerekceleri:", model_result["reasons"])
        print("V5 karar:", actual)
        print("V5 asama:", result["stage"])
        print("V5 gerekceler:", result["reasons"])
        print(
            "TEST:",
            "PASS" if actual == expected else "FAIL",
        )

    print("\n" + "=" * 60)
    print(f"TOPLAM: {passed}/8")
    print("Yanlis READY:", false_ready)
    print("Beklenen READY yerine REVIEW:", missed_ready)
    print(
        "NOT: Kaynak 11 ve 3. cumlesi onceki "
        "gelistirme testlerinde kullanildi."
    )
    print("Bu test bagimsiz dogrulama degildir.")
    print("Veritabanina yazilmadi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()