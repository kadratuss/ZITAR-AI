
import argparse
import sqlite3

from research_engine import connect
from research_notes import (
    init_notes_database,
    add_note
)


# PortfolioAI - Research Note Generator
#
# Ilk surum:
# - Tek makalenin kayitli yazar ozetini okur.
# - Kaynak baglantili bir DRAFT not hazirlar.
# - Varsayilan olarak sadece on izleme yapar.
# - AI modeli kullanmaz.
# - Strateji veya islem olusturmaz.

DEFAULT_SOURCE_ID = 11


def load_source(source_id):

    with connect() as db:
        return db.execute(
            """
            SELECT
                s.id AS source_id,
                s.title,
                s.url,
                s.status,
                k.id AS knowledge_id,
                k.content AS abstract,
                k.page_reference
            FROM sources AS s
            JOIN knowledge AS k
                ON k.source_id = s.id
            WHERE s.id = ?
              AND k.topic LIKE 'Yazar ozeti%'
            ORDER BY k.id DESC
            LIMIT 1
            """,
            (source_id,)
        ).fetchone()


def note_exists(source_id, knowledge_id):

    with connect() as db:
        row = db.execute(
            """
            SELECT id
            FROM research_notes
            WHERE source_id = ?
              AND knowledge_id = ?
              AND note_type = 'SUMMARY'
            LIMIT 1
            """,
            (source_id, knowledge_id)
        ).fetchone()

        return row["id"] if row else None


def prepare_note(source):

    abstract = (source["abstract"] or "").strip()

    if not abstract:
        raise ValueError(
            "Bu kaynakta kayitli yazar ozeti yok."
        )

    # Bu bir AI ozeti degildir.
    # Kayitli yazar ozetini kaynakli taslak
    # olarak aktaririz; yeni bulgu eklemeyiz.
    content = (
        "KAYNAK OZETINDEN AKTARILAN TASLAK\n\n"
        "Makale: " + source["title"] + "\n"
        "Kaynak: " + (source["url"] or "Yok") + "\n"
        "Referans: "
        + (source["page_reference"] or "Belirtilmedi")
        + "\n\n"
        "Yazar ozeti:\n"
        + abstract
    )

    limitations = (
        "Bu kayit yalnizca OpenAlex uzerinden "
        "alinan yazar ozetine dayanir. Tam metin "
        "incelenmedi. Iddialar bagimsiz olarak "
        "dogrulanmadi. Bu metin AI tarafindan "
        "uretilmis yeni bir bilimsel bulgu veya "
        "yatirim tavsiyesi degildir."
    )

    return content, limitations


def main():

    parser = argparse.ArgumentParser(
        description="Tek kaynak icin taslak not"
    )

    parser.add_argument(
        "--source-id",
        type=int,
        default=DEFAULT_SOURCE_ID
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Taslak notu veritabanina kaydet"
    )

    args = parser.parse_args()

    init_notes_database()

    source = load_source(args.source_id)

    if source is None:
        print(
            "Kaynak veya yazar ozeti bulunamadi:",
            args.source_id
        )
        return

    print("PORTFOLIOAI - NOTE GENERATOR")
    print("----------------------------")
    print("Kaynak:", source["source_id"])
    print("Baslik:", source["title"])
    print("Durum:", source["status"])
    print("Ozet ID:", source["knowledge_id"])
    print("Baglanti:", source["url"])

    if source["status"] != "REVIEW_REQUIRED":
        print()
        print(
            "DURDURULDU: Kaynak durumu "
            "REVIEW_REQUIRED degil."
        )
        return

    existing_id = note_exists(
        source["source_id"],
        source["knowledge_id"]
    )

    if existing_id is not None:
        print()
        print(
            "Bu ozet icin mevcut SUMMARY notu:",
            existing_id
        )
        print("Tekrar kayit olusturulmadi.")
        return

    content, limitations = prepare_note(source)

    print()
    print("TASLAK NOT")
    print("----------")
    print(content)

    print()
    print("SINIRLAMALAR")
    print("-----------")
    print(limitations)

    if not args.save:
        print()
        print(
            "ON IZLEME: Veritabanina not "
            "kaydedilmedi."
        )
        print(
            "Kaydetmek icin --save kullan."
        )
        return

    note_id = add_note(
        source_id=source["source_id"],
        knowledge_id=source["knowledge_id"],
        note_type="SUMMARY",
        content=content,
        limitations=limitations
    )

    print()
    print("Taslak not kaydedildi.")
    print("Not ID:", note_id)
    print("Durum: DRAFT")


if __name__ == "__main__":

    try:
        main()

    except (sqlite3.Error, ValueError) as error:
        print(
            "Note Generator hatasi:",
            error
        )