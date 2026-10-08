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

TARGETS = {
    "LONG_TERM_BTC_VOL",
    "BITCOIN_PRICE",
    "UNKNOWN",
}

VARIABLES = {
    "SP500_REALIZED_VOL",
    "SP500_VOL_RISK_PREMIUM",
    "BALTIC_DRY_INDEX",
    "BITCOIN_PRICE",
    "UNKNOWN",
}

RELATIONS = {"EFFECT", "ASSOCIATION", "UNKNOWN"}
DIRECTIONS = {"POSITIVE", "NEGATIVE", "UNKNOWN"}


# Bu cevap anahtari onceki deneyden degistirilmeden alindi.
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
        6,
    ),
]


# Kaynak cumlelerinin elle kontrol edilmis cevap anahtari.
# Modelin kaynak cikarimi yanlissa bu test onay vermez.
SOURCE_GOLD = {
    3: {
        "target": "LONG_TERM_BTC_VOL",
        "variable": "SP500_REALIZED_VOL",
        "relation": "EFFECT",
        "direction": "NEGATIVE",
    },
    5: {
        "target": "LONG_TERM_BTC_VOL",
        "variable": "SP500_VOL_RISK_PREMIUM",
        "relation": "EFFECT",
        "direction": "POSITIVE",
    },
    6: {
        "target": "LONG_TERM_BTC_VOL",
        "variable": "BALTIC_DRY_INDEX",
        "relation": "ASSOCIATION",
        "direction": "POSITIVE",
    },
}


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
            SELECT k.content
            FROM sources s
            JOIN knowledge k ON k.source_id = s.id
            WHERE s.id = ? AND k.id = ?
            """,
            (SOURCE_ID, KNOWLEDGE_ID),
        ).fetchone()
    finally:
        connection.close()

    if row is None or not row[0]:
        raise RuntimeError("Beklenen kaynak ozeti bulunamadi.")

    sentences = [
        sentence.strip()
        for sentence in re.split(
            r"(?<=[.!?])\s+(?=[A-Z])",
            row[0].strip(),
        )
        if sentence.strip()
    ]

    checks = {
        3: "negative and highly significant effect",
        5: "significantly positive effect",
        6: "strong positive association",
    }

    if len(sentences) != 8:
        raise RuntimeError(
            f"Kaynak metni degismis olabilir: "
            f"8 yerine {len(sentences)} cumle bulundu."
        )

    for number, phrase in checks.items():
        if phrase.casefold() not in sentences[number - 1].casefold():
            raise RuntimeError(
                f"Kaynak cumlesi {number} beklenen metinle uyusmuyor."
            )

    return sentences


def ask_ollama(system_prompt, text):
    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system_prompt},
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

    return json.loads(outer["message"]["content"])


def extract_target(text):
    system = """
Identify only the TARGET variable in the text.

Return ONLY JSON:
{"target": "..."}

Allowed values:
LONG_TERM_BTC_VOL
BITCOIN_PRICE
UNKNOWN

Volatility and price are different quantities.
Use UNKNOWN if the target is unclear.
Do not evaluate the claim or provide trading advice.
""".strip()

    data = ask_ollama(system, text)

    if not isinstance(data, dict):
        return None

    if set(data) != {"target"}:
        return None

    if data["target"] not in TARGETS:
        return None

    return data["target"]


def extract_other_fields(text):
    system = """
Extract three fields from the text.

Return ONLY JSON:
{
  "variable": "...",
  "relation": "...",
  "direction": "..."
}

Allowed variable values:
SP500_REALIZED_VOL
SP500_VOL_RISK_PREMIUM
BALTIC_DRY_INDEX
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

Use only the supplied text.
Distinguish an effect from an association.
Do not infer causation from association.
If a field cannot be determined, use UNKNOWN.
Do not evaluate truth or provide trading advice.
""".strip()

    data = ask_ollama(system, text)

    if not isinstance(data, dict):
        return None

    if set(data) != {"variable", "relation", "direction"}:
        return None

    if data["variable"] not in VARIABLES:
        return None

    if data["relation"] not in RELATIONS:
        return None

    if data["direction"] not in DIRECTIONS:
        return None

    return data


def extract_split(text):
    # Iki ayri model cagrisi. Hicbir alan elle duzeltilmez.
    target = extract_target(text)
    other = extract_other_fields(text)

    if target is None or other is None:
        return None

    return {
        "target": target,
        **other,
    }


def decide(source, claim):
    if source is None or claim is None:
        return "REVIEW"

    if "UNKNOWN" in source.values():
        return "REVIEW"

    if "UNKNOWN" in claim.values():
        return "REVIEW"

    if source["target"] != claim["target"]:
        return "REVIEW"

    if source["variable"] != claim["variable"]:
        return "REVIEW"

    # Bir iliskiyi nedensel etkiye donusturup onaylamiyoruz.
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


def show(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def main():
    sentences = load_sentences()

    print("PERSONAL AI - IKI ASAMALI ILISKI TESTI")
    print("=" * 60)
    print("Model:", MODEL)
    print("Kaynak: 11 | Bilgi: 2")
    print("Veritabani: sadece okuma")
    print("Strateji ve alim-satim: kapali")

    source_data = {}
    source_valid = {}

    print("\nKAYNAK CIKARIMLARI")

    for number in (3, 5, 6):
        text = sentences[number - 1]

        print("\n" + "-" * 60)
        print(f"KAYNAK CUMLESI {number}: {text}")

        try:
            extracted = extract_split(text)
        except Exception as error:
            print("Model hatasi:", error)
            extracted = None

        valid = extracted == SOURCE_GOLD[number]

        source_data[number] = extracted
        source_valid[number] = valid

        print("Model cikarimi:", show(extracted))
        print("Onceden sabitlenen cevap:", show(SOURCE_GOLD[number]))
        print(
            "Kaynak kontrolu:",
            "GECTI" if valid else "KALDI - REVIEW zorunlu",
        )

    relation_passed = 0
    review_passed = 0

    print("\n" + "=" * 60)
    print("IDDIA TESTLERI")

    for index, (name, text, expected, source_id) in \
            enumerate(TESTS, start=1):

        print("\n" + "-" * 60)
        print(f"TEST {index}: {name}")
        print("Iddia:", text)
        print("Beklenen:", expected)

        try:
            claim = extract_split(text)
        except Exception as error:
            print("Model hatasi:", error)
            claim = None

        print("Model cikarimi:", show(claim))

        if source_id is None:
            # Bu iddia icin secilmis destekleyici kaynak
            # cumlesi yok. Otomatik onay verilmiyor.
            actual = "REVIEW"

        elif not source_valid[source_id]:
            # Kaynak cikarimi elle kontrol edilmis
            # cevapla uyusmuyorsa karsilastirma yapma.
            actual = "REVIEW"

        else:
            actual = decide(source_data[source_id], claim)

        success = actual == expected

        print("Python karari:", actual)
        print("SONUC:", "GECTI" if success else "KALDI")

        if expected == "REVIEW":
            review_passed += int(success)
        else:
            relation_passed += int(success)

    print("\n" + "=" * 60)
    print(
        "KAYNAK CIKARIMI:",
        f"{sum(source_valid.values())}/{len(source_valid)}",
    )
    print("ILISKI TESTLERI:", f"{relation_passed}/5")
    print("REVIEW KONTROLLERI:", f"{review_passed}/2")
    print(
        "TOPLAM:",
        f"{relation_passed + review_passed}/{len(TESTS)}",
    )

    print(
        "\nNOT: REVIEW kontrolleri, modelin iddiayi "
        "dogru anladigini tek basina kanitlamaz."
    )
    print(
        "Bu test tek bir yazar ozetine ozeldir; "
        "genel guvenilirlik veya yatirim performansi kaniti degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print("DURDURULDU:", error)