import json
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_DIR / "research.db"

SOURCE_ID = 9
MODEL_NAME = "qwen2.5:7b"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"


def read_source():
    """Kaynak ID 9'a bagli tek dolu metni salt okunur getir."""

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
                f"Kaynak {SOURCE_ID} icin {len(rows)} dolu "
                "bilgi kaydi bulundu. Otomatik secim yapilmadi."
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
    normalized = re.sub(r"\s+", " ", text).strip()

    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if sentence.strip()
    ]


def ask_ollama(source, sentences):
    numbered_text = "\n".join(
        f"{number}. {sentence}"
        for number, sentence in enumerate(sentences, start=1)
    )

    system_prompt = """
You are a cautious research information extractor.

Use ONLY the supplied source text. Do not use outside knowledge.

Return a JSON object with exactly these keys:
- method
- dataset
- reported_result
- success_rate

Each key must contain either null or an object with exactly:
- value: a short English description of what the source says
- sentence_id: the source sentence number as an integer
- quote: an EXACT continuous substring copied from that sentence

Rules:
1. Do not invent information.
2. Do not infer a numeric success rate from qualitative results.
3. If a field is not explicitly stated, return null.
4. Do not treat participant counts, dates, or dataset sizes as success rates.
5. The quote must be copied exactly, preserving its characters.
6. Do not claim to have read the full paper. You only have this text.
7. Do not recommend a trading strategy.
8. Return JSON only, without Markdown.
""".strip()

    user_prompt = f"""
SOURCE TITLE:
{source["title"]}

SOURCE TEXT WITH SENTENCE NUMBERS:
{numbered_text}

Extract the four requested fields.
""".strip()

    payload = {
        "model": MODEL_NAME,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_ctx": 4096,
        },
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=180,
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.URLError as error:
        raise RuntimeError(
            "Ollama baglantisi kurulamadi. "
            f"Ayrinti: {error}"
        ) from error

    except TimeoutError as error:
        raise RuntimeError(
            "Ollama 180 saniye icinde yanit vermedi."
        ) from error

    try:
        content = result["message"]["content"]
        extracted = json.loads(content)

    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Ollama gecerli JSON yaniti vermedi: {result}"
        ) from error

    if not isinstance(extracted, dict):
        raise RuntimeError(
            "Modelin yaniti JSON nesnesi degil."
        )

    return extracted


def validate_field(field_name, item, sentences):
    """
    Yalnizca veri yapisini, cumle numarasini ve
    alintinin birebir metin eslesmesini kontrol eder.

    Bu kontrol anlamsal veya bilimsel dogrulama degildir.
    """

    if item is None:
        return {
            "status": "NOT_REPORTED",
            "reason": "Model bu alan icin bilgi bildirmedi.",
        }

    if not isinstance(item, dict):
        return {
            "status": "REJECTED",
            "reason": "Alan nesne veya null olmali.",
        }

    if set(item.keys()) != {
        "value",
        "sentence_id",
        "quote",
    }:
        return {
            "status": "REJECTED",
            "reason": "Alan yapisi beklenen bicimde degil.",
        }

    value = item["value"]
    sentence_id = item["sentence_id"]
    quote = item["quote"]

    if not isinstance(value, str) or not value.strip():
        return {
            "status": "REJECTED",
            "reason": "Aciklama bos veya gecersiz.",
        }

    if (
        type(sentence_id) is not int
        or not 1 <= sentence_id <= len(sentences)
    ):
        return {
            "status": "REJECTED",
            "reason": "Cumle numarasi gecersiz.",
        }

    if not isinstance(quote, str) or not quote.strip():
        return {
            "status": "REJECTED",
            "reason": "Kaynak alintisi bos veya gecersiz.",
        }

    source_sentence = sentences[sentence_id - 1]

    if quote not in source_sentence:
        return {
            "status": "REJECTED",
            "reason": (
                "Alinti secilen kaynak cumlesinde "
                "birebir bulunamadi."
            ),
        }

    return {
        "status": "QUOTE_MATCH",
        "reason": (
            "Cumle numarasi ve birebir alinti eslesti. "
            "Aciklamanin anlami ayrica incelenmeli."
        ),
    }


def main():
    print("PERSONAL AI - OLLAMA KAYNAK CIKARIM TESTI")
    print("=" * 55)

    try:
        source = read_source()
        sentences = split_sentences(source["text"])

        if not sentences:
            raise RuntimeError("Kaynak metni bos.")

        print(f"Kaynak ID: {source['source_id']}")
        print(f"Baslik: {source['title']}")
        print(f"Bilgi kaydi ID: {source['knowledge_id']}")
        print(f"Cumle sayisi: {len(sentences)}")
        print(f"Model: {MODEL_NAME}")
        print()
        print("Ollama yaniti bekleniyor...")

        extracted = ask_ollama(source, sentences)

    except (
        RuntimeError,
        sqlite3.Error,
        OSError,
        ValueError,
    ) as error:
        print()
        print(f"DURDURULDU: {error}")
        return

    expected_fields = [
        "method",
        "dataset",
        "reported_result",
        "success_rate",
    ]

    print()
    print("MODEL CIKTISI VE KANIT KONTROLU")
    print("=" * 55)

    if set(extracted.keys()) != set(expected_fields):
        print(
            "UYARI: Model beklenen alan yapisina "
            "tam olarak uymadi."
        )
        print(
            "Gelen alanlar:",
            ", ".join(extracted.keys()),
        )

    matched = 0
    rejected = 0
    not_reported = 0

    for field_name in expected_fields:
        item = extracted.get(field_name)

        validation = validate_field(
            field_name,
            item,
            sentences,
        )

        status = validation["status"]

        if status == "QUOTE_MATCH":
            matched += 1
        elif status == "REJECTED":
            rejected += 1
        else:
            not_reported += 1

        print()
        print(f"ALAN: {field_name}")
        print(f"DURUM: {status}")
        print(f"GEREKCE: {validation['reason']}")

        if isinstance(item, dict):
            print(f"Modelin aciklamasi: {item.get('value')}")
            print(f"Cumle numarasi: {item.get('sentence_id')}")
            print(f"Alinti: {item.get('quote')}")
        else:
            print(f"Modelin degeri: {item}")

    print()
    print("=" * 55)
    print(f"Alintisi eslesen alan: {matched}")
    print(f"Reddedilen alan: {rejected}")
    print(f"Bildirilmemis alan: {not_reported}")

    if rejected:
        print(
            "SONUC: En az bir alan kanit kontrolunden gecemedi."
        )
    else:
        print(
            "SONUC: Yapisal ve birebir alinti kontrolu tamamlandi."
        )

    print()
    print(
        "NOT: Alinti eslesmesi, modelin aciklamasinin "
        "anlamsal olarak dogru oldugunu kanitlamaz."
    )
    print(
        "Kaynak metni makalenin tamami degil; "
        "bu test yalnizca eldeki metni inceler."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji olusturulmadi.")
    print("Alim-satim islemi tetiklenmedi.")


if __name__ == "__main__":
    main()