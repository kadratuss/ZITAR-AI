import json

# Onceki deneyin kaynak okuma, model cagrisi ve
# Python karar fonksiyonlarini yeniden kullaniyoruz.
import split_relation_test as base


VARIABLES = {
    "SP500_REALIZED_VOL",
    "SP500_VOL_RISK_PREMIUM",
    "BALTIC_DRY_INDEX",
    "BITCOIN_PRICE",
    "UNKNOWN",
}

RELATIONS = {"EFFECT", "ASSOCIATION", "UNKNOWN"}
DIRECTIONS = {"POSITIVE", "NEGATIVE", "UNKNOWN"}


# Ilk bes iddianin dogru alanlari, onceki kaynak
# ve iddialara gore model calistirilmadan once sabitlendi.
CLAIM_GOLD = {
    1: {
        "target": "LONG_TERM_BTC_VOL",
        "variable": "SP500_REALIZED_VOL",
        "relation": "EFFECT",
        "direction": "NEGATIVE",
    },
    2: {
        "target": "LONG_TERM_BTC_VOL",
        "variable": "SP500_VOL_RISK_PREMIUM",
        "relation": "EFFECT",
        "direction": "POSITIVE",
    },
    3: {
        "target": "LONG_TERM_BTC_VOL",
        "variable": "BALTIC_DRY_INDEX",
        "relation": "ASSOCIATION",
        "direction": "POSITIVE",
    },
    4: {
        "target": "LONG_TERM_BTC_VOL",
        "variable": "SP500_REALIZED_VOL",
        "relation": "EFFECT",
        "direction": "POSITIVE",
    },
    5: {
        "target": "LONG_TERM_BTC_VOL",
        "variable": "BALTIC_DRY_INDEX",
        "relation": "ASSOCIATION",
        "direction": "NEGATIVE",
    },
}


def extract_variable(text):
    system = """
Identify ONLY the explanatory variable in the text.

Return ONLY JSON with exactly one field:
{"variable": "..."}

Allowed values:
SP500_REALIZED_VOL
SP500_VOL_RISK_PREMIUM
BALTIC_DRY_INDEX
BITCOIN_PRICE
UNKNOWN

The explanatory variable is the factor described
as affecting or being related to another quantity.

Distinguish it from the target variable.
Use UNKNOWN when unclear.
Do not judge whether the claim is true.
""".strip()

    data = base.ask_ollama(system, text)

    if not isinstance(data, dict):
        return None

    if set(data) != {"variable"}:
        return None

    if data["variable"] not in VARIABLES:
        return None

    return data["variable"]


def extract_relation_direction(text):
    system = """
Extract ONLY the relation type and direction
from the supplied text.

Return ONLY JSON with exactly these fields:
{
  "relation": "...",
  "direction": "..."
}

Allowed relation values:
EFFECT
ASSOCIATION
UNKNOWN

Allowed direction values:
POSITIVE
NEGATIVE
UNKNOWN

Distinguish an effect from an association.
Do not infer causation from association.
Use UNKNOWN if a field is unclear.
Do not judge whether the claim is true.
""".strip()

    data = base.ask_ollama(system, text)

    if not isinstance(data, dict):
        return None

    if set(data) != {"relation", "direction"}:
        return None

    if data["relation"] not in RELATIONS:
        return None

    if data["direction"] not in DIRECTIONS:
        return None

    return data


def extract_three_stage(text):
    # 1. Hedef degisken
    target = base.extract_target(text)

    # 2. Aciklayici degisken
    variable = extract_variable(text)

    # 3. Iliski turu ve yon
    relation_data = extract_relation_direction(text)

    # Hatali veya eksik ciktiyi duzeltmiyoruz.
    if (
        target is None
        or variable is None
        or relation_data is None
    ):
        return None

    return {
        "target": target,
        "variable": variable,
        **relation_data,
    }


def show(data):
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
    )


def safe_extract(text):
    try:
        return extract_three_stage(text)
    except Exception as error:
        print("Model hatasi:", error)
        return None


def main():
    sentences = base.load_sentences()

    print("PERSONAL AI - UC ASAMALI ILISKI TESTI")
    print("=" * 60)
    print("Model:", base.MODEL)
    print("Kaynak: 11 | Bilgi: 2")
    print("Veritabani: sadece okuma")
    print("Strateji ve alim-satim: kapali")

    source_data = {}
    source_correct = 0

    print("\nKAYNAK CIKARIMLARI")

    for number in (3, 5, 6):
        text = sentences[number - 1]

        print("\n" + "-" * 60)
        print(f"KAYNAK CUMLESI {number}: {text}")

        extracted = safe_extract(text)
        gold = base.SOURCE_GOLD[number]

        correct = extracted == gold
        source_correct += int(correct)

        source_data[number] = extracted

        print("Model cikarimi:", show(extracted))
        print("Beklenen:", show(gold))
        print(
            "Alan kontrolu:",
            "GECTI" if correct else "KALDI",
        )

    claim_correct = 0
    decision_correct = 0

    print("\n" + "=" * 60)
    print("BES ILISKI TESTI")

    # Onceki deneyin ilk bes testi:
    # uc tutarli, iki ters yonlu iddia.
    for index, test in enumerate(base.TESTS[:5], start=1):
        name, text, expected, source_id = test

        print("\n" + "-" * 60)
        print(f"TEST {index}: {name}")
        print("Iddia:", text)

        claim = safe_extract(text)
        gold = CLAIM_GOLD[index]

        fields_ok = claim == gold
        claim_correct += int(fields_ok)

        print("Model cikarimi:", show(claim))
        print("Beklenen alanlar:", show(gold))
        print(
            "Alan kontrolu:",
            "GECTI" if fields_ok else "KALDI",
        )

        # Kaynak cikarimi yanlissa otomatik karar yok.
        if source_data[source_id] != base.SOURCE_GOLD[source_id]:
            actual = "REVIEW"
        else:
            actual = base.decide(
                source_data[source_id],
                claim,
            )

        decision_ok = actual == expected
        decision_correct += int(decision_ok)

        print("Beklenen karar:", expected)
        print("Python karari:", actual)
        print(
            "Karar kontrolu:",
            "GECTI" if decision_ok else "KALDI",
        )

    print("\n" + "=" * 60)
    print("SONUCLAR")
    print(f"Kaynak alanlari: {source_correct}/3")
    print(f"Iddia alanlari: {claim_correct}/5")
    print(f"Iliski kararlari: {decision_correct}/5")

    print(
        "\nNOT: Bu deney onceki bes iddiayi "
        "ayni cevap anahtariyla tekrar sinar."
    )
    print(
        "Yeni kaynaklarda genel guvenilirlik "
        "veya yatirim performansi kaniti degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print("DURDURULDU:", error)