
import json
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request

from research_engine import (
    init_database,
    connect,
    get_research_stats,
    now
)


# PortfolioAI - Research Reader
# OpenAlex akademik arastirma modulu
# Yalnizca kaynak ve yazar ozeti kaydeder.
# Islem yapmaz, strateji degistirmez.

API_URL = "https://api.openalex.org/works"

SEARCH_TERMS = [
    "financial time series forecasting",
    "cryptocurrency volatility",
    "algorithmic trading"
]

RESULTS_PER_SEARCH = 3


def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        value or ""
    ).strip()


def fetch_papers(search_term):

    params = urllib.parse.urlencode({
        "search": search_term,
        "per-page": RESULTS_PER_SEARCH
    })

    url = API_URL + "?" + params

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "PortfolioAI-Research/0.1",
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=25
    ) as response:

        data = response.read(3_000_001)

        if len(data) > 3_000_000:
            raise ValueError(
                "API yaniti beklenenden buyuk."
            )

    result = json.loads(
        data.decode("utf-8")
    )

    return result.get("results", [])


def reconstruct_abstract(inverted_index):
    """
    OpenAlex ozetleri kelime-konum biciminde verebilir.
    Bu fonksiyon ozeti yeniden olusturur.
    """

    if not isinstance(inverted_index, dict):
        return ""

    positions = {}

    for word, indexes in inverted_index.items():

        if not isinstance(indexes, list):
            continue

        for position in indexes:

            if (
                isinstance(position, int)
                and not isinstance(position, bool)
                and 0 <= position < 100_000
            ):
                positions[position] = word

    if not positions:
        return ""

    words = [
        word
        for _, word in sorted(
            positions.items()
        )
    ]

    return clean_text(
        " ".join(words)
    )


def parse_paper(item):

    title = clean_text(
        item.get("display_name")
    )

    openalex_id = item.get("id")

    if not isinstance(openalex_id, str):
        return None

    parsed = urllib.parse.urlparse(
        openalex_id
    )

    if (
        parsed.scheme != "https"
        or parsed.hostname != "openalex.org"
        or not parsed.path.startswith("/W")
    ):
        return None

    if not title:
        return None

    authors = []

    for authorship in item.get(
        "authorships", []
    ):

        author = authorship.get(
            "author"
        ) or {}

        name = clean_text(
            author.get("display_name")
        )

        if name:
            authors.append(name)

    abstract = reconstruct_abstract(
        item.get("abstract_inverted_index")
    )

    return {
        "title": title,
        "author": ", ".join(authors),
        "url": openalex_id,
        "publication_date": item.get(
            "publication_date"
        ),
        "abstract": abstract
    }


def save_paper(paper, search_term):
    """
    Kaynak ve ozeti tek veritabani
    islemi icinde kaydeder.
    """

    with connect() as db:

        existing = db.execute(
            """
            SELECT id
            FROM sources
            WHERE url = ?
            LIMIT 1
            """,
            (paper["url"],)
        ).fetchone()

        if existing:
            return "EXISTS", existing["id"]

        cursor = db.execute(
            """
            INSERT INTO sources (
                title,
                author,
                source_type,
                url,
                publication_date,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper["title"],
                paper["author"],
                "PAPER",
                paper["url"],
                paper["publication_date"],
                "PENDING",
                now()
            )
        )

        source_id = cursor.lastrowid

        if paper["abstract"]:

            db.execute(
                """
                INSERT INTO knowledge (
                    source_id,
                    topic,
                    content,
                    page_reference,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    "Yazar ozeti - " + search_term,
                    paper["abstract"],
                    "OpenAlex abstract: "
                    + paper["url"],
                    now()
                )
            )

        return "ADDED", source_id


def collect_research():

    init_database()

    added = 0
    existing = 0
    errors = 0
    abstracts = 0

    print(
        "PORTFOLIOAI - OPENALEX RESEARCH"
    )
    print("-----------------------------")

    for search_term in SEARCH_TERMS:

        print()
        print(
            "Arastiriliyor:",
            search_term
        )

        try:

            results = fetch_papers(
                search_term
            )

        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            ValueError,
            json.JSONDecodeError
        ) as error:

            errors += 1

            print(
                "[ARAMA HATASI]",
                type(error).__name__,
                str(error)
            )

            continue

        print(
            "Gelen sonuc:",
            len(results)
        )

        for item in results:

            try:

                paper = parse_paper(item)

                if paper is None:
                    print(
                        "[ATLANDI] Eksik veya "
                        "gecersiz kaynak bilgisi"
                    )
                    continue

                status, source_id = save_paper(
                    paper,
                    search_term
                )

                if status == "ADDED":

                    added += 1

                    if paper["abstract"]:
                        abstracts += 1

                    print(
                        "[EKLENDI]",
                        source_id,
                        paper["title"]
                    )

                    if not paper["abstract"]:
                        print(
                            "  Yazar ozeti bulunamadi."
                        )

                else:

                    existing += 1

                    print(
                        "[MEVCUT]",
                        source_id,
                        paper["title"]
                    )

                print(
                    "  Kaynak:",
                    paper["url"]
                )

            except (
                sqlite3.Error,
                ValueError,
                TypeError,
                AttributeError
            ) as error:

                errors += 1

                print(
                    "[KAYIT HATASI]",
                    type(error).__name__,
                    str(error)
                )

    print()
    print("ARASTIRMA SONUCU")
    print("----------------")

    print("Yeni makale:", added)
    print("Mevcut makale:", existing)
    print("Yeni yazar ozeti:", abstracts)
    print("Hata:", errors)

    print()
    print("VERITABANI DURUMU")
    print("-----------------")

    print(get_research_stats())


if __name__ == "__main__":
    collect_research()