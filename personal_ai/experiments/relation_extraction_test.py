import json
import urllib.error
import urllib.request


MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://localhost:11434/api/chat"

# Kaynak 14'ün daha önce incelediğimiz yazar özetinden
# alınan ilgili cümleler. Bu test veritabanını kullanmaz.
SOURCE_SENTENCES = {
    3: (
        "We show that the reduction in arbitrage opportunities "
        "is associated primarily with computers taking liquidity."
    ),
    5: (
        "In contrast, the reduction in the autocorrelation of "
        "returns owes more to the algorithmic provision of liquidity."
    ),
}

# Modelin kullanmasına izin verilen sınırlı etiketler.
SUBJECTS = {
    "ARBITRAGE_REDUCTION",
    "RETURN_AUTOCORRELATION_REDUCTION",
    "OTHER",
    "UNKNOWN",
}

MECHANISMS = {
    "LIQUIDITY_TAKING",
    "LIQUIDITY_PROVISION",
    "OTHER",
    "UNKNOWN",
}

RELATIONS = {
    "PRIMARILY_ASSOCIATED_WITH",
    "OWES_MORE_TO",
    "OTHER",
    "UNKNOWN",
}


def ask_ollama(text):
    system_prompt = """
You extract relations from ONE English financial research sentence.

Return ONLY a JSON object with exactly these fields:
{
  "subject": "...",
  "relation": "...",
  "mechanism": "..."
}

Allowed subject values:
ARBITRAGE_REDUCTION
RETURN_AUTOCORRELATION_REDUCTION
OTHER
UNKNOWN

Allowed relation values:
PRIMARILY_ASSOCIATED_WITH
OWES_MORE_TO
OTHER
UNKNOWN

Allowed mechanism values:
LIQUIDITY_TAKING
LIQUIDITY_PROVISION
OTHER
UNKNOWN

Rules:
- "taking liquidity" means LIQUIDITY_TAKING.
- "provision of liquidity" means LIQUIDITY_PROVISION.
- Do not treat taking and provision as synonyms.
- Do not infer information absent from the sentence.
- If uncertain, use UNKNOWN.
- Do not give trading advice.
"""

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
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))

    content = result["message"]["content"]
    return json.loads(content)


def validate_extraction(data):
    if not isinstance(data, dict):
        return None

    if set(data) != {"subject", "relation", "mechanism"}:
        return None

    if data["subject"] not in SUBJECTS:
        return None

    if data["relation"] not in RELATIONS:
        return None

    if data["mechanism"] not in MECHANISMS:
        return None

    return data


def python_decision(extracted, claim):
    """
    Python karar verir; modelin kendi verdiği
    CONSISTENT/CONTRADICTION kararı kabul edilmez.
    """

    if extracted is None:
        return "REVIEW"

    if (
        "UNKNOWN" in extracted.values()
        or "OTHER" in extracted.values()
    ):
        return "REVIEW"

    if extracted["subject"] != claim["subject"]:
        return "REVIEW"

    if extracted["relation"] != claim["relation"]:
        return "REVIEW"

    if extracted["mechanism"] == claim["mechanism"]:
        return "CONSISTENT"

    opposites = {
        "LIQUIDITY_TAKING": "LIQUIDITY_PROVISION",
        "LIQUIDITY_PROVISION": "LIQUIDITY_TAKING",
    }

    if (
        opposites.get(extracted["mechanism"])
        == claim["mechanism"]
    ):
        return "CONTRADICTION"

    return "REVIEW"


TESTS = [
    {
        "name": "Arbitraj - likidite alma",
        "source_id": 3,
        "claim": {
            "subject": "ARBITRAGE_REDUCTION",
            "relation": "PRIMARILY_ASSOCIATED_WITH",
            "mechanism": "LIQUIDITY_TAKING",
        },
        "expected": "CONSISTENT",
    },
    {
        "name": "Arbitraj - likidite sağlama karışıklığı",
        "source_id": 3,
        "claim": {
            "subject": "ARBITRAGE_REDUCTION",
            "relation": "PRIMARILY_ASSOCIATED_WITH",
            "mechanism": "LIQUIDITY_PROVISION",
        },
        "expected": "CONTRADICTION",
    },
    {
        "name": "Otokorelasyon - likidite sağlama",
        "source_id": 5,
        "claim": {
            "subject": "RETURN_AUTOCORRELATION_REDUCTION",
            "relation": "OWES_MORE_TO",
            "mechanism": "LIQUIDITY_PROVISION",
        },
        "expected": "CONSISTENT",
    },
    {
        "name": "Otokorelasyon - likidite alma karışıklığı",
        "source_id": 5,
        "claim": {
            "subject": "RETURN_AUTOCORRELATION_REDUCTION",
            "relation": "OWES_MORE_TO",
            "mechanism": "LIQUIDITY_TAKING",
        },
        "expected": "CONTRADICTION",
    },
    {
        "name": "İlgisiz konu için otomatik onay yok",
        "source_id": 3,
        "claim": {
            "subject": "RETURN_AUTOCORRELATION_REDUCTION",
            "relation": "PRIMARILY_ASSOCIATED_WITH",
            "mechanism": "LIQUIDITY_TAKING",
        },
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - MODEL ILISKI CIKARIMI + PYTHON KARARI")
    print("=" * 60)
    print("Veritabani: kullanilmiyor | Strateji ve islem: kapali")
    print("Model:", MODEL)

    extracted_by_source = {}

    for source_id, sentence in SOURCE_SENTENCES.items():
        print("\n" + "-" * 60)
        print("KAYNAK CUMLESI:", source_id)
        print(sentence)
        print("\nOllama yaniti bekleniyor...")

        try:
            raw = ask_ollama(sentence)
            print("HAM MODEL CIKTISI:")
            print(json.dumps(raw, ensure_ascii=False, indent=2))
            extracted = validate_extraction(raw)

            if extracted is None:
                print("UYARI: Gecersiz alan veya etiket; REVIEW uygulanacak.")

        except (
            urllib.error.URLError,
            TimeoutError,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:
            print("MODEL HATASI:", exc)
            extracted = None

        extracted_by_source[source_id] = extracted

    passed = 0

    print("\n" + "=" * 60)
    print("PYTHON KARAR TESTLERI")

    for index, test in enumerate(TESTS, start=1):
        extracted = extracted_by_source[test["source_id"]]
        actual = python_decision(extracted, test["claim"])
        success = actual == test["expected"]

        if success:
            passed += 1

        print(f"\nTEST {index}: {test['name']}")
        print("Beklenen:", test["expected"])
        print("Python karari:", actual)
        print("SONUC:", "GECTI" if success else "KALDI")

    print("\n" + "=" * 60)
    print(f"GENEL SONUC: {passed}/{len(TESTS)} kontrol gecti.")
    print("NOT: Dar kapsamli, iki kaynak cumleli bir testtir.")
    print("Bilimsel dogrulama veya genel guvenilirlik kaniti degildir.")
    print("Veritabanina yazilmadi.")
    print("Strateji olusturulmadi veya degistirilmedi.")
    print("Alim-satim islemi tetiklenmedi.")


if __name__ == "__main__":
    main()