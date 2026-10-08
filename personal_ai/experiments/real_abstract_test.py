import re
import sqlite3
from pathlib import Path


# Bu dosya:
# PortfolioAI-Backend/personal_ai/experiments/real_abstract_test.py
#
# Veritabani:
# PortfolioAI-Backend/research.db

PROJECT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_DIR / "research.db"

SOURCE_ID = 9


def read_source():
    """Kaynak 9'a ait tek dolu bilgi kaydini salt okunur getir."""

    if not DB_PATH.is_file():
        raise RuntimeError(
            f"Veritabani bulunamadi: {DB_PATH}"
        )

    connection = sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        rows = connection.execute(
            """
            SELECT
                s.id,
                s.title,
                k.id,
                k.topic,
                k.content
            FROM sources AS s
            JOIN knowledge AS k
                ON k.source_id = s.id
            WHERE s.id = ?
              AND k.content IS NOT NULL
              AND TRIM(k.content) != ''
            ORDER BY k.id
            """,
            (SOURCE_ID,),
        ).fetchall()

        if len(rows) != 1:
            raise RuntimeError(
                f"Kaynak ID {SOURCE_ID} icin "
                f"{len(rows)} dolu bilgi kaydi bulundu. "
                "Yanlis metni secmemek icin durduruldu."
            )

        row = rows[0]

        return {
            "source_id": row[0],
            "title": row[1],
            "knowledge_id": row[2],
            "topic": row[3],
            "text": row[4].strip(),
        }

    finally:
        connection.close()


def split_sentences(text):
    """Metni basit bir kuralla cumlelere ayir."""

    normalized = re.sub(r"\s+", " ", text).strip()

    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if sentence.strip()
    ]


def find_exact_evidence(sentences, required_patterns):
    """
    Verilen desenlerin HEPSINI iceren kaynak cumlesini bul.
    Eslestirme, bilimsel dogrulama anlamina gelmez.
    """

    matches = []

    for sentence_number, sentence in enumerate(sentences, start=1):
        if all(
            re.search(pattern, sentence, flags=re.IGNORECASE)
            for pattern in required_patterns
        ):
            matches.append((sentence_number, sentence))

    return matches


def print_evidence(label, sentences, patterns):
    """Iddiayi ve kaynakta bulunan birebir cumleleri yazdir."""

    print()
    print(f"IDDI A: {label}".replace("IDDI A", "IDDIA"))

    matches = find_exact_evidence(sentences, patterns)

    if not matches:
        print("DURUM: KANIT BULUNAMADI")
        print(
            "Bu ifade icin belirlenen kelimeleri ayni "
            "kaynak cumlesinde bulamadik."
        )
        return False

    print("DURUM: KAYNAK METNINDE IFADE BULUNDU")

    for sentence_number, sentence in matches:
        print(f"Cumle {sentence_number}: {sentence}")

    print(
        "NOT: Bu yalnizca kaynak metni eslesmesidir; "
        "makalenin bilimsel sonucunu bagimsiz dogrulamaz."
    )

    return True


def main():
    print("PERSONAL AI - GERCEK KAYNAK METNI KONTROLU")
    print("=" * 52)

    try:
        source = read_source()
    except (sqlite3.Error, OSError, RuntimeError) as error:
        print(f"DURDURULDU: {error}")
        return

    print(f"Kaynak ID: {source['source_id']}")
    print(f"Baslik: {source['title']}")
    print(f"Bilgi kaydi ID: {source['knowledge_id']}")
    print(f"Konu etiketi: {source['topic']}")
    print(f"Metin uzunlugu: {len(source['text'])} karakter")

    sentences = split_sentences(source["text"])

    print(f"Cumle sayisi: {len(sentences)}")

    if not sentences:
        print("DURDURULDU: Kaynak metni bos.")
        return

    print()
    print("KAYNAKTAN ALINAN METIN")
    print("-" * 52)

    for number, sentence in enumerate(sentences, start=1):
        print(f"{number}. {sentence}")

    print()
    print("BIREBIR KANIT KONTROLLERI")
    print("-" * 52)

    checks = [
        (
            "Calisma SVM yontemini ele aliyor.",
            [r"\bSVM\b"],
        ),
        (
            "Metinde finansal zaman serisi tahmini geciyor.",
            [r"financial time series", r"forecast"],
        ),
        (
            "Metinde bes gercek vadeli islem sozlesmesi geciyor.",
            [r"\bfive\b", r"futures contracts"],
        ),
    ]

    passed = 0

    for label, patterns in checks:
        if print_evidence(label, sentences, patterns):
            passed += 1

    print()
    print("=" * 52)
    print(f"SONUC: {passed}/{len(checks)} metin kontrolu eslesti.")
    print(
        "Bu test, yalnizca kaynakta ilgili ifadelerin "
        "bulunup bulunmadigini kontrol eder."
    )
    print("Veritabanina yazilmadi.")
    print("Ollama cagrilmadi.")
    print("Herhangi bir alim-satim islemi tetiklenmedi.")


if __name__ == "__main__":
    main()