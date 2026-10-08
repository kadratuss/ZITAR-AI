import re

import direction_evidence_gate_test as direction
import text_evidence_gate_test as evidence


# Bilerek dar tutulmus ifade listesi.
# Tum Ingilizce/Turkce iliski anlatimlarini kapsamaz.
RELATION_PHRASES = {
    "EFFECT": [
        "effect on",
        "impact on",
        "has an effect on",
        "etkisi var",
        "etkisi vardir",
        "etkisi bulunuyor",
        "etkisi bulunmaktadir",
    ],
    "ASSOCIATION": [
        "association between",
        "associated with",
        "relationship between",
        "is related to",
        "arasinda iliski var",
        "arasinda bir iliski var",
        "ile iliskili",
    ],
}


def find_phrases(text, phrases):
    return [
        phrase
        for phrase in phrases
        if evidence.contains_phrase(text, phrase)
    ]


def has_negation(text):
    normalized = evidence.normalize(text)

    words = [
        "not",
        "no",
        "never",
        "degil",
        "yok",
        "olmayan",
    ]

    return any(
        re.search(
            r"(?<!\w)" + re.escape(word) + r"(?!\w)",
            normalized,
        )
        for word in words
    )


def relation_gate(text, extraction):
    expected = extraction.get("relation")

    effect_matches = find_phrases(
        text,
        RELATION_PHRASES["EFFECT"],
    )
    association_matches = find_phrases(
        text,
        RELATION_PHRASES["ASSOCIATION"],
    )

    matches = {
        "EFFECT": effect_matches,
        "ASSOCIATION": association_matches,
    }

    reasons = []

    if has_negation(text):
        reasons.append("OLUMSUZLUK_VAR")

    if effect_matches and association_matches:
        reasons.append("IKI_ILISKI_TURU_BIRDEN_VAR")

    if not effect_matches and not association_matches:
        reasons.append("METINDE_ILISKI_TURU_DAYANAGI_YOK")

    if expected == "EFFECT" and not effect_matches:
        reasons.append("MODEL_ILISKI_TURU_METINLE_UYUSMUYOR")

    elif expected == "ASSOCIATION" and not association_matches:
        reasons.append("MODEL_ILISKI_TURU_METINLE_UYUSMUYOR")

    elif expected not in ("EFFECT", "ASSOCIATION"):
        reasons.append("DESTEKLENMEYEN_ILISKI_TURU")

    return {
        "status": "REVIEW" if reasons else "READY",
        "reasons": reasons,
        "relation_matches": matches,
    }


def combined_gate(text, raw):
    """
    Sirayla:
    1. Etiket bicimi
    2. Hedef ve degiskenin metin dayanagi
    3. Yon dayanagi
    4. Iliski turu dayanagi
    """
    previous = direction.combined_gate(text, raw)

    if previous["status"] != "READY":
        return {
            "status": "REVIEW",
            "reasons": previous["reasons"],
            "relation_matches": {},
        }

    extraction = {
        "target": raw[0]["target"],
        "variable": raw[1]["variable"],
        "relation": raw[2]["relation"],
        "direction": raw[2]["direction"],
    }

    return relation_gate(text, extraction)


def raw_answers(relation, direction_value="NEGATIVE"):
    return [
        {"target": "LONG_TERM_BTC_VOL"},
        {"variable": "SP500_REALIZED_VOL"},
        {
            "relation": relation,
            "direction": direction_value,
        },
    ]


CASES = [
    {
        "name": "Ingilizce etki, dogru etiket",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility."
        ),
        "raw": raw_answers("EFFECT"),
        "expected": "READY",
    },
    {
        "name": "Ingilizce etki, yanlis iliski etiketi",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility."
        ),
        "raw": raw_answers("ASSOCIATION"),
        "expected": "REVIEW",
    },
    {
        "name": "Ingilizce iliski, dogru etiket",
        "text": (
            "S&P 500 realized volatility has a negative "
            "association between it and long-term "
            "Bitcoin volatility."
        ),
        "raw": raw_answers("ASSOCIATION"),
        "expected": "READY",
    },
    {
        "name": "Ingilizce iliski, yanlis etki etiketi",
        "text": (
            "S&P 500 realized volatility has a negative "
            "association between it and long-term "
            "Bitcoin volatility."
        ),
        "raw": raw_answers("EFFECT"),
        "expected": "REVIEW",
    },
    {
        "name": "Turkce etki, dogru etiket",
        "text": (
            "S&P 500 gerceklesen oynakliginin uzun vadeli "
            "Bitcoin oynakligi uzerinde negatif etkisi var."
        ),
        "raw": raw_answers("EFFECT"),
        "expected": "READY",
    },
    {
        "name": "Turkce etki, yanlis iliski etiketi",
        "text": (
            "S&P 500 gerceklesen oynakliginin uzun vadeli "
            "Bitcoin oynakligi uzerinde negatif etkisi var."
        ),
        "raw": raw_answers("ASSOCIATION"),
        "expected": "REVIEW",
    },
    {
        "name": "Iliski turu acik degil",
        "text": (
            "S&P 500 realized volatility and long-term "
            "Bitcoin volatility both decreased; "
            "the direction was negative."
        ),
        "raw": raw_answers("EFFECT"),
        "expected": "REVIEW",
    },
    {
        "name": "Iki iliski turu birlikte",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility, "
            "and an association between them is reported."
        ),
        "raw": raw_answers("EFFECT"),
        "expected": "REVIEW",
    },
    {
        "name": "Olumsuzlanan etki",
        "text": (
            "S&P 500 realized volatility has no negative "
            "effect on long-term Bitcoin volatility."
        ),
        "raw": raw_answers("EFFECT"),
        "expected": "REVIEW",
    },
    {
        "name": "Kapsam disi sahte etiketler",
        "text": "AT narrows spreads.",
        "raw": raw_answers("EFFECT"),
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - ILISKI TURU DAYANAGI KAPISI")
    print("=" * 60)
    print("Model cagrisi: YOK - kontrollu test girdileri")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0

    for index, case in enumerate(CASES, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {index}: {case['name']}")
        print("Metin:", case["text"])
        print(
            "Modelin iliski etiketi:",
            case["raw"][2]["relation"],
        )

        result = combined_gate(
            case["text"],
            case["raw"],
        )

        print("Kapi sonucu:", result["status"])
        print("Gerekceler:", result["reasons"])
        print(
            "Iliski ifadeleri:",
            result["relation_matches"],
        )

        ok = result["status"] == case["expected"]

        print("Beklenen:", case["expected"])
        print("Test:", "PASS" if ok else "FAIL")

        if ok:
            passed += 1

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")

    if passed == len(CASES):
        print(
            "Dort kapi kontrollu orneklerde "
            "beklenen sonuclari verdi."
        )
    else:
        print("Beklenmeyen sonuc var; ciktiyi incele.")

    print(
        "UYARI: READY, arastirmanin nedensellik "
        "kanitladigi anlamina gelmez."
    )
    print(
        "Bu test kelime dayanagini kontrol eder; "
        "karmasik cumleleri ve iliskinin gercekten "
        "hangi degiskenlere baglandigini cozumlemez."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()