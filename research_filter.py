
import argparse
import sqlite3

from research_engine import (
    init_database,
    connect,
    get_research_stats
)


# PortfolioAI - Research Filter
# Kaynaklari silmeden on siniflandirma yapar.
# Bu siniflandirma bilimsel dogrulama degildir.

FINANCE_TERMS = (
    "financial",
    "finance",
    "trading",
    "stock market",
    "cryptocurrency",
    "cryptoasset",
    "bitcoin",
    "ethereum",
    "portfolio",
    "asset pricing",
    "exchange rate",
    "foreign exchange",
    "forex",
    "market volatility",
    "price prediction",
    "risk management",
    "technical analysis",
    "liquidity",
    "order book",
    "market microstructure",
    "quantitative investment"
)

NON_FINANCE_TERMS = (
    "molecular dynamics",
    "molecular simulation",
    "protein folding",
    "particle physics",
    "fluid dynamics",
    "image classification",
    "speech recognition"
)

# REVIEW_REQUIRED:
# Konuyla ilgili gorunuyor, ama insan incelemesi gerekli.
#
# REVIEW_UNCERTAIN:
# Ilgi duzeyi belirsiz veya ozet eksik.
#
# REVIEW_IRRELEVANT:
# Finans disi olduguna dair belirgin isaret var.
#
# Bu durumlar kaynak kalitesini veya bilimsel
# guvenilirligini onaylamaz.

ALLOWED_STATUSES = (
    "REVIEW_REQUIRED",
    "REVIEW_UNCERTAIN",
    "REVIEW_IRRELEVANT"
)


def has_term(text, terms):
    return any(term in text for term in terms)


def classify_source(source):

    title = (source["title"] or "").lower()
    source_type = (source["source_type"] or "").upper()
    abstract = (source["abstract"] or "").lower()

    # Kitaplarin yalnizca künye kaydi var.
    # Kitap icerigi okunmus gibi davranmayalim.
    if source_type == "BOOK":
        return (
            "REVIEW_UNCERTAIN",
            "Kitap icerigi henuz incelenmedi."
        )

    if has_term(title, NON_FINANCE_TERMS):
        return (
            "REVIEW_IRRELEVANT",
            "Baslikta finans disi konu bulundu."
        )

    if has_term(title, FINANCE_TERMS):
        return (
            "REVIEW_REQUIRED",
            "Baslik finansla ilgili gorunuyor; "
            "icerik ve kalite incelenmeli."
        )

    if not abstract:
        return (
            "REVIEW_UNCERTAIN",
            "Finans baglantisi belirsiz; ozet yok."
        )

    if has_term(abstract, FINANCE_TERMS):
        return (
            "REVIEW_UNCERTAIN",
            "Finans terimi yalnizca ozette bulundu; "
            "konu uygunlugu kontrol edilmeli."
        )

    return (
        "REVIEW_UNCERTAIN",
        "Finansla ilgi kurmak icin yeterli kanit yok."
    )


def load_sources():

    with connect() as db:

        return db.execute(
            """
            SELECT
                s.id,
                s.title,
                s.source_type,
                s.status,
                (
                    SELECT k.content
                    FROM knowledge AS k
                    WHERE k.source_id = s.id
                      AND k.topic LIKE 'Yazar ozeti%'
                    ORDER BY k.id DESC
                    LIMIT 1
                ) AS abstract
            FROM sources AS s
            ORDER BY s.id
            """
        ).fetchall()


def review_sources():

    results = []

    for source in load_sources():

        suggested_status, reason = classify_source(
            source
        )

        results.append({
            "id": source["id"],
            "title": source["title"],
            "old_status": source["status"],
            "suggested_status": suggested_status,
            "reason": reason
        })

    return results


def apply_reviews(results):
    """
    Yalnizca PENDING kaynaklari gunceller.
    Daha once incelenmis kayitlari ezmez.
    """

    updated = 0

    with connect() as db:

        for item in results:

            if item["suggested_status"] not in ALLOWED_STATUSES:
                raise ValueError(
                    "Gecersiz siniflandirma durumu."
                )

            cursor = db.execute(
                """
                UPDATE sources
                SET status = ?
                WHERE id = ?
                  AND status = 'PENDING'
                """,
                (
                    item["suggested_status"],
                    item["id"]
                )
            )

            updated += cursor.rowcount

    return updated


def main():

    parser = argparse.ArgumentParser(
        description="PortfolioAI kaynak on inceleme"
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Siniflandirmayi veritabanina kaydet"
    )

    args = parser.parse_args()

    init_database()

    results = review_sources()

    print("PORTFOLIOAI - RESEARCH FILTER")
    print("-----------------------------")

    counts = {
        status: 0
        for status in ALLOWED_STATUSES
    }

    for item in results:

        status = item["suggested_status"]
        counts[status] += 1

        print()
        print(
            f"Kaynak #{item['id']}: "
            f"{item['title']}"
        )
        print("Mevcut durum:", item["old_status"])
        print("Onerilen durum:", status)
        print("Gerekce:", item["reason"])

    print()
    print("SINIFLANDIRMA OZETI")
    print("-------------------")

    for status, count in counts.items():
        print(f"{status}: {count}")

    if args.apply:

        updated = apply_reviews(results)

        print()
        print(
            "Veritabaninda guncellenen kaynak:",
            updated
        )

    else:

        print()
        print(
            "ON IZLEME: Veritabaninda "
            "degisiklik yapilmadi."
        )

    print()
    print("VERITABANI DURUMU")
    print("-----------------")
    print(get_research_stats())


if __name__ == "__main__":

    try:
        main()

    except (
        sqlite3.Error,
        ValueError
    ) as error:

        print(
            "Research Filter hatasi:",
            error
        )