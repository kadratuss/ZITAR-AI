
from research_engine import (
    init_database,
    add_source,
    get_research_stats,
    connect
)

# PortfolioAI - Research Collector
# Finansal kaynak kutuphanesi

STARTER_SOURCES = [
    {
        "title": "Technical Analysis of the Financial Markets",
        "author": "John J. Murphy",
        "source_type": "BOOK",
        "url": None,
        "publication_date": "1999"
    },
    {
        "title": "Trading in the Zone",
        "author": "Mark Douglas",
        "source_type": "BOOK",
        "url": None,
        "publication_date": "2000"
    },
    {
        "title": "Advances in Financial Machine Learning",
        "author": "Marcos Lopez de Prado",
        "source_type": "BOOK",
        "url": None,
        "publication_date": "2018"
    },
    {
        "title": "Evidence-Based Technical Analysis",
        "author": "David Aronson",
        "source_type": "BOOK",
        "url": None,
        "publication_date": "2006"
    },
    {
        "title": "Quantitative Trading",
        "author": "Ernest P. Chan",
        "source_type": "BOOK",
        "url": None,
        "publication_date": "2008"
    },
    {
        "title": "Algorithmic Trading",
        "author": "Ernest P. Chan",
        "source_type": "BOOK",
        "url": None,
        "publication_date": "2013"
    }
]


def source_exists(title, author):

    with connect() as db:

        result = db.execute(
            """
            SELECT id
            FROM sources
            WHERE title = ?
              AND author = ?
            LIMIT 1
            """,
            (title, author)
        ).fetchone()

        return result is not None


def collect_sources():

    init_database()

    added = 0
    skipped = 0

    for source in STARTER_SOURCES:

        title = source["title"]
        author = source["author"]

        if source_exists(title, author):

            print(
                "[MEVCUT]",
                title
            )

            skipped += 1
            continue

        source_id = add_source(
            title=title,
            author=author,
            source_type=source["source_type"],
            url=source["url"],
            publication_date=source["publication_date"]
        )

        print(
            "[EKLENDI]",
            source_id,
            title
        )

        added += 1

    return {
        "added": added,
        "skipped": skipped
    }


def show_library():

    with connect() as db:

        sources = db.execute(
            """
            SELECT
                id,
                title,
                author,
                source_type,
                status
            FROM sources
            ORDER BY id
            """
        ).fetchall()

    print()
    print("PORTFOLIOAI KAYNAK KUTUPHANESI")
    print("-----------------------------")

    for source in sources:

        print(
            f"{source['id']:02d}. "
            f"{source['title']} "
            f"- {source['author']} "
            f"[{source['status']}]"
        )


if __name__ == "__main__":

    try:

        result = collect_sources()

        show_library()

        print()
        print("KAYNAK TOPLAMA SONUCU")
        print("--------------------")

        print(
            "Yeni kaynak:",
            result["added"]
        )

        print(
            "Tekrar atlanan:",
            result["skipped"]
        )

        print()
        print("VERITABANI DURUMU")
        print("-----------------")

        print(get_research_stats())

    except Exception as error:

        print(
            "Research Collector hatasi:",
            error
        )