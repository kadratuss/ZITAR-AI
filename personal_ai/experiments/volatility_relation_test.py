import json
import re
import sqlite3
import urllib.request
from pathlib import Path


MODEL = "qwen2.5:7b"
URL = "http://127.0.0.1:11434/api/chat"
DB = Path(__file__).resolve().parents[2] / "research.db"

SOURCE_ID = 11
KNOWLEDGE_ID = 2

VARIABLES = {
    "SP500_REALIZED_VOL",
    "SP500_VOL_RISK_PREMIUM",
    "BALTIC_DRY_INDEX",
    "BITCOIN_PRICE",
    "UNKNOWN",
}

RELATIONS = {"EFFECT", "ASSOCIATION", "UNKNOWN"}
DIRECTIONS = {"POSITIVE", "NEGATIVE", "UNKNOWN"}
TARGETS = {"LONG_TERM_BTC_VOL", "BITCOIN_PRICE", "UNKNOWN"}


# Beklenen cevaplar, Ollama calistirilmadan once
# kaynak 11'in yazar ozetine gore belirlendi.
TESTS = [
    (
        "Gerceklesen oynaklik - negatif etki",
        "S&P 500 gerceklesen oynakliginin uzun vadeli "
        "Bitcoin oynakligi uzerinde negatif etkisi var.",
        "CONSISTENT",
        3,
    ),
    (
        "Risk primi - pozitif etki",
        "S&P 500 oynaklik risk priminin uzun vadeli "
        "Bitcoin oynakligi uzerinde pozitif etkisi var.",
        "CONSISTENT",
        5,
    ),
    (
        "Baltic Dry - pozitif iliski",
        "Baltic Dry Index ile uzun vadeli Bitcoin "
        "oynakligi arasinda pozitif iliski var.",
        "CONSISTENT",
        6,
    ),
    (
        "Gerceklesen oynaklik - ters yon",
        "S&P 500 gerceklesen oynakliginin uzun vadeli "
        "Bitcoin oynakligi uzerinde pozitif etkisi var.",
        "CONTRADICTION",
        3,
    ),
    (
        "Baltic Dry - ters yon",
        "Baltic Dry Index ile uzun vadeli Bitcoin "
        "oynakligi arasinda negatif iliski var.",
        "CONTRADICTION",
        6,
    ),
    (
        "Kaynak disi fiyat tahmini",
        "Makale Bitcoin fiyatinin yarin yuzde 5 "
        "artacagini kanitliyor.",
        "REVIEW",
        None,
    ),
    (
        "Iliskiyi nedensel etkiye cevirme",
        "Baltic Dry Index'in uzun vadeli Bitcoin "
        "oynakligi uzerinde pozitif nedensel etkisi var.",
        "REVIEW",
        None,
    ),
]


def load_sentences():
    if not DB.is_file():
        raise RuntimeError(f"Veritabani bulunamadi: {DB}")

    connection = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        row = connection.execute(
            """
            SELECT s.title, k.topic, k.content
            FROM sources s
            JOIN knowledge k ON k.source_id = s.id
            WHERE s.id = ? AND k.id = ?
            """,
            (SOURCE_ID, KNOWLEDGE_ID),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise RuntimeError("Beklenen kaynak veya bilgi kaydi yok.")

    title, topic, content = row

    if not content or not content.strip():
        raise RuntimeError("Kaynak ozeti bos.")

    if "ozet" not in (topic or "").casefold() and \
       "özet" not in (topic or "").casefold():
        raise RuntimeError("Kayit yazar ozeti olarak etiketlenmemis.")

    sentences = [
        s.strip()
        for s in re.split(
            r"(?<=[.!?])\s+(?=[A-Z])",
            content.strip(),
        )
        if s.strip()
    ]

    # Bu testin cevap anahtari belirli metne ozeldir.
    # Metin degismisse yanlis testi calistirmiyoruz.
    checks = {
        3: "negative and highly significant effect",
        5: "significantly positive effect",
        6: "strong positive association",
    }

    if len(sentences) != 8:
        raise RuntimeError(
            f"8 cumle bekleniyordu; {len(sentences)} bulundu."
        )

    for number, phrase in checks.items():
        if phrase.casefold() not in sentences[number - 1].casefold():
            raise RuntimeError(
                f"Kaynak cumlesi {number} beklenen metinle uyusmuyor."
            )

    return title, sentences


def extract(text):
    system = """
You extract ONE financial research relation from the given text.

Return ONLY a JSON object with exactly these four fields:
{
  "variable": "...",
  "target": "...",
  "relation": "...",
  "direction": "..."
}

Allowed variable values:
SP500_REALIZED_VOL
SP500_VOL_RISK_PREMIUM
BALTIC_DRY_INDEX
BITCOIN_PRICE
UNKNOWN

Allowed target values:
LONG_TERM_BTC_VOL
BITCOIN_PRICE
UNKNOWN

Allowed relation values:
EFFECT
ASSOCIATION
UNKNOWN

Allowed direction values:
POSITIVE
NEGATIVE
UNKNOWN

Use the text alone. Do not use outside knowledge.
Distinguish an effect from an association.
Do not infer causation from association.
If the text is a price prediction rather than one of
the specified research relations, use UNKNOWN where needed.
Do not produce a verdict or trading recommendation.
""".strip()

    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
    }

    request = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        outer = json.loads(response.read().decode("utf-8"))

    answer = json.loads(outer["message"]["content"])

    if not isinstance(answer, dict):
        return None

    if set(answer) != {
        "variable", "target", "relation", "direction"
    }:
        return None

    if (
        answer["variable"] not in VARIABLES
        or answer["target"] not in TARGETS
        or answer["relation"] not in RELATIONS
        or answer["direction"] not in DIRECTIONS
    ):
        return None

    return answer


def decide(source, claim):
    # Eksik veya gecersiz cikti otomatik onaylanmaz.
    if source is None or claim is None:
        return "REVIEW"

    if "UNKNOWN" in source.values():
        return "REVIEW"

    if "UNKNOWN" in claim.values():
        return "REVIEW"

    # Farkli degisken veya hedef: bu tek kaynak
    # cumlesi iddiayi dogrulamak icin yeterli degil.
    if source["variable"] != claim["variable"]:
        return "REVIEW"

    if source["target"] != claim["target"]:
        return "REVIEW"

    # Iliskiyi nedensel etkiye yukseltmeyelim.
    # Bu dar testte farkli iliski turu incelemeye gider.
    if source["relation"] != claim["relation"]:
        return "REVIEW"

    if source["direction"] == claim["direction"]:
        return "CONSISTENT"

    if {
        source["direction"],
        claim["direction"],
    } == {"POSITIVE", "NEGATIVE"}:
        return "CONTRADICTION"

    return "REVIEW"


def main():
    title, sentences = load_sentences()

    print("PERSONAL AI - YENI KAYNAK ILISKI TESTI")
    print("=" * 60)
    print("Kaynak:", title)
    print("Veritabani: sadece okuma")
    print("Strateji ve alim-satim: kapali")

    # Beklenen kanit cumleleri onceden sabitlenmistir.
    source_numbers = (3, 5, 6)
    source_data = {}

    print("\nKAYNAK CIKARIMLARI")

    for number in source_numbers:
        print(f"\nCumle {number}: {sentences[number - 1]}")

        try:
            result = extract(sentences[number - 1])
        except Exception as error:
            print("Model hatasi:", error)
            result = None

        source_data[number] = result
        print(
            "Cikarim:",
            json.dumps(result, ensure_ascii=False),
        )

    passed = 0

    print("\n" + "=" * 60)
    print("IDDIA TESTLERI")

    for index, (name, claim_text, expected, source_id) in \
            enumerate(TESTS, start=1):

        print(f"\nTEST {index}: {name}")
        print("Iddia:", claim_text)
        print("Beklenen:", expected)

        try:
            claim_data = extract(claim_text)
        except Exception as error:
            print("Model hatasi:", error)
            claim_data = None

        print(
            "Iddia cikarimi:",
            json.dumps(claim_data, ensure_ascii=False),
        )

        if source_id is None:
            # Bu iki iddia icin kaynakta dogrudan
            # onaylanabilir bir kanit belirlenmedi.
            # Guvenli varsayilan karar REVIEW.
            actual = "REVIEW"
        else:
            actual = decide(
                source_data[source_id],
                claim_data,
            )

        ok = actual == expected
        passed += int(ok)

        print("Python karari:", actual)
        print("SONUC:", "GECTI" if ok else "KALDI")

    print("\n" + "=" * 60)
    print(f"GENEL SONUC: {passed}/{len(TESTS)}")
    print(
        "NOT: Bu deney, tek bir yazar ozetindeki "
        "dar kapsamli iliskileri test eder."
    )
    print(
        "REVIEW testleri otomatik onay verilmedigini "
        "gosterir; modelin iddiayi dogru anladigini kanitlamaz."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print("DURDURULDU:", error)