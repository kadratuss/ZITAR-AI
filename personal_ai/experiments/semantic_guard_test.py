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

FIELDS = ("method", "dataset", "reported_result", "success_rate")

# Bunlar bilimsel dogrulama kurallari degildir.
# Yalnizca bu deneyde kabul ettigimiz dar bilgi alanlaridir.
ALLOWED_EVIDENCE = {
    "method": (
        r"\bSVM\b",
        r"support vector machine",
    ),
    "dataset": (
        r"five real futures contracts",
        r"Chicago Mercantile Market",
    ),
    "reported_result": (
        r"outperforms the BP neural network",
        r"comparable generalization performance",
        r"higher generalization performance",
        r"fewer support vectors",
    ),
}

# Bu deneyde kaynak disina tasan yorumlari engellemek icin.
FORBIDDEN_INTERPRETATIONS = (
    r"\bcrypto\b",
    r"\bcryptocurrency\b",
    r"\bbitcoin\b",
    r"\bBTC\b",
    r"\bprofitable\b",
    r"\bprofit guarantee\b",
    r"\bguaranteed\b",
    r"\btrading signal\b",
    r"\bbuy\b",
    r"\bsell\b",
)


def read_source():
    if not DB_PATH.is_file():
        raise RuntimeError(f"Veritabani bulunamadi: {DB_PATH}")

    connection = sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        rows = connection.execute(
            """
            SELECT s.id, s.title, k.id, k.topic, k.content
            FROM sources AS s
            JOIN knowledge AS k ON k.source_id = s.id
            WHERE s.id = ?
              AND k.content IS NOT NULL
              AND TRIM(k.content) != ''
            ORDER BY k.id
            """,
            (SOURCE_ID,),
        ).fetchall()

        if len(rows) != 1:
            raise RuntimeError(
                f"Kaynak {SOURCE_ID} icin {len(rows)} dolu kayit "
                "bulundu. Yanlis kaydi secmemek icin durduruldu."
            )

        source_id, title, knowledge_id, topic, text = rows[0]

        return {
            "source_id": source_id,
            "title": title,
            "knowledge_id": knowledge_id,
            "topic": topic,
            "text": text.strip(),
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
You extract information from a supplied research abstract.

Use ONLY the supplied text. Do not use outside knowledge.

Return a JSON object with EXACTLY four keys:
method, dataset, reported_result, success_rate

Each value must be null or an object with EXACTLY:
value, sentence_id, quote

value: a short English description.
sentence_id: an integer identifying the supporting sentence.
quote: an EXACT continuous substring from that sentence.

Rules:
- Do not invent information.
- Do not extrapolate results to cryptocurrency.
- Do not recommend trading actions.
- Do not turn qualitative comparisons into numeric success rates.
- If no numeric success rate is explicitly reported, use null.
- A sample size or dataset size is not a success rate.
- Do not claim to have read the full paper.
- Return JSON only.
""".strip()

    user_prompt = (
        f"TITLE:\n{source['title']}\n\n"
        f"ABSTRACT SENTENCES:\n{numbered_text}\n\n"
        "Extract the four fields."
    )

    payload = {
        "model": MODEL_NAME,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_ctx": 4096,
        },
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw_response = json.loads(
                response.read().decode("utf-8")
            )
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(
            f"Ollama baglantisi veya yaniti basarisiz: {error}"
        ) from error

    try:
        content = raw_response["message"]["content"]
        result = json.loads(content)
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Ollama beklenen JSON yanitini vermedi."
        ) from error

    if not isinstance(result, dict):
        raise RuntimeError("Ollama JSON nesnesi dondurmedi.")

    return result


def check_field(field, item, sentences):
    """
    Dar kapsamli kontrol:
    1. Yapi dogru mu?
    2. Alinti secilen cumlede birebir var mi?
    3. Aciklama kaynak disi riskli iddia iceriyor mu?
    4. Alinti bu alan icin beklenen ifadelerden birini iceriyor mu?

    Bu, genel anlamsal veya bilimsel dogrulama DEGILDIR.
    """

    if item is None:
        return "NOT_REPORTED", "Model bilgi bildirmedi."

    if not isinstance(item, dict):
        return "REJECTED", "Alan nesne veya null olmali."

    if set(item) != {"value", "sentence_id", "quote"}:
        return "REJECTED", "Alan yapisi gecersiz."

    value = item["value"]
    sentence_id = item["sentence_id"]
    quote = item["quote"]

    if not isinstance(value, str) or not value.strip():
        return "REJECTED", "Aciklama bos veya gecersiz."

    if type(sentence_id) is not int:
        return "REJECTED", "Cumle numarasi tam sayi degil."

    if not 1 <= sentence_id <= len(sentences):
        return "REJECTED", "Cumle numarasi kaynak disinda."

    if not isinstance(quote, str) or not quote.strip():
        return "REJECTED", "Alinti bos veya gecersiz."

    source_sentence = sentences[sentence_id - 1]

    if quote not in source_sentence:
        return "REJECTED", "Alinti kaynak cumlesinde birebir yok."

    for pattern in FORBIDDEN_INTERPRETATIONS:
        if re.search(pattern, value, flags=re.IGNORECASE):
            return (
                "REJECTED",
                "Aciklama bu deneyde izin verilmeyen "
                "kaynak disi ticaret/kripto yorumu iceriyor.",
            )

    if field == "success_rate":
        return (
            "REVIEW_REQUIRED",
            "Sayisal basari orani icin ayri olcum ve "
            "baglam kontrolu gerekiyor.",
        )

    patterns = ALLOWED_EVIDENCE.get(field)

    if patterns is None:
        return "REJECTED", "Taninmayan alan."

    if not any(
        re.search(pattern, quote, flags=re.IGNORECASE)
        for pattern in patterns
    ):
        return (
            "REVIEW_REQUIRED",
            "Alinti birebir eslesti ancak bu alan icin "
            "beklenen dar kanit ifadesi bulunamadi.",
        )

    return (
        "LIMITED_MATCH",
        "Alinti ve dar alan kurali eslesti. "
        "Aciklamanin tum anlami bilimsel olarak "
        "dogrulanmis sayilmaz.",
    )


def print_result(field, item, sentences):
    status, reason = check_field(field, item, sentences)

    print()
    print(f"ALAN: {field}")
    print(f"DURUM: {status}")
    print(f"GEREKCE: {reason}")

    if isinstance(item, dict):
        print(f"Aciklama: {item.get('value')}")
        print(f"Cumle numarasi: {item.get('sentence_id')}")
        print(f"Alinti: {item.get('quote')}")
    else:
        print(f"Deger: {item}")

    return status


def run_adversarial_tests(sentences):
    """
    Bilerek eklenen kaynak disi yorumlar.
    Bu testler Ollama ciktisi degildir.
    """

    print()
    print("KAYNAK DISI YORUM ENGELLEME TESTLERI")
    print("=" * 58)

    # Kaynakta SVM gecen bir cumleyi bul.
    svm_sentence_id = next(
        (
            number
            for number, sentence in enumerate(sentences, start=1)
            if re.search(r"\bSVM\b", sentence)
        ),
        None,
    )

    if svm_sentence_id is None:
        print("DURDURULDU: SVM iceren cumle bulunamadi.")
        return False

    svm_quote = sentences[svm_sentence_id - 1]

    invented_claims = [
        (
            "Kripto karliligi iddiasi",
            "This SVM strategy is guaranteed profitable in crypto.",
            "method",
        ),
        (
            "Alim sinyali iddiasi",
            "This paper provides a Bitcoin buy trading signal.",
            "method",
        ),
    ]

    all_rejected = True

    for label, value, field in invented_claims:
        fake_item = {
            "value": value,
            "sentence_id": svm_sentence_id,
            "quote": svm_quote,
        }

        status, reason = check_field(
            field,
            fake_item,
            sentences,
        )

        passed = status == "REJECTED"

        print()
        print(f"TEST: {label}")
        print(f"Sonuc: {'GECTI' if passed else 'KALDI'}")
        print(f"Kontrol durumu: {status}")
        print(f"Gerekce: {reason}")

        if not passed:
            all_rejected = False

    return all_rejected


def main():
    print("PERSONAL AI - ANLAM SINIRI KONTROL DENEYI")
    print("=" * 58)

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
        print(f"DURDURULDU: {error}")
        return

    print()
    print("MODEL CIKTISI")
    print("=" * 58)

    if set(extracted) != set(FIELDS):
        print("DURDURULDU: Model beklenen dort alani vermedi.")
        print(f"Gelen alanlar: {list(extracted)}")
        return

    statuses = {}

    for field in FIELDS:
        statuses[field] = print_result(
            field,
            extracted[field],
            sentences,
        )

    adversarial_passed = run_adversarial_tests(sentences)

    print()
    print("GENEL SONUC")
    print("=" * 58)

    for field, status in statuses.items():
        print(f"{field}: {status}")

    print(
        "Kaynak disi yorum testleri: "
        + ("GECTI" if adversarial_passed else "KALDI")
    )

    if statuses["success_rate"] == "NOT_REPORTED":
        print("Basari yuzdesi: Kaynakta raporlanmadi.")
    else:
        print(
            "Basari yuzdesi: Otomatik kabul edilmedi; "
            "ayri inceleme gerekiyor."
        )

    print()
    print(
        "NOT: LIMITED_MATCH yalnizca dar kapsamli "
        "alinti ve kural eslesmesidir."
    )
    print("Bilimsel sonuc bagimsiz dogrulanmadi.")
    print("Veritabanina yazilmadi.")
    print("Strateji olusturulmadi veya degistirilmedi.")
    print("Alim-satim islemi tetiklenmedi.")


if __name__ == "__main__":
    main()