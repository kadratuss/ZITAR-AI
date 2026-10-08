import re

import text_evidence_gate_test as evidence


DIRECTION_PHRASES = {
    "POSITIVE": [
        "positive",
        "positively",
        "pozitif",
        "olumlu",
    ],
    "NEGATIVE": [
        "negative",
        "negatively",
        "negatif",
        "olumsuz",
    ],
}

# Bu ifadeler basit olumsuzluklar icin koruyucu kontroldur.
# Genel bir dil veya mantik cozumleyicisi degildir.
NEGATION_WORDS = [
    "not",
    "no",
    "never",
    "degil",
    "olmayan",
]


def find_phrases(text, phrases):
    return [
        phrase
        for phrase in phrases
        if evidence.contains_phrase(text, phrase)
    ]


def has_simple_negation(text):
    normalized = evidence.normalize(text)

    for word in NEGATION_WORDS:
        pattern = r"(?<!\w)" + re.escape(word) + r"(?!\w)"

        if re.search(pattern, normalized):
            return True

    return False


def direction_gate(text, extraction):
    """
    Modelin yon etiketi icin metinsel dayanak arar.

    Hedef/degisken eslesmesini veya iliski turunu
    burada tekrar kontrol etmez.
    """
    expected = extraction.get("direction")

    positive_matches = find_phrases(
        text,
        DIRECTION_PHRASES["POSITIVE"],
    )
    negative_matches = find_phrases(
        text,
        DIRECTION_PHRASES["NEGATIVE"],
    )

    matches = {
        "POSITIVE": positive_matches,
        "NEGATIVE": negative_matches,
    }

    reasons = []

    if has_simple_negation(text):
        reasons.append("BASIT_OLUMSUZLUK_VAR")

    if positive_matches and negative_matches:
        reasons.append("IKI_YON_BIRDEN_VAR")

    if not positive_matches and not negative_matches:
        reasons.append("METINDE_YON_DAYANAGI_YOK")

    if expected == "POSITIVE" and not positive_matches:
        reasons.append("MODEL_YONU_METINLE_UYUSMUYOR")

    elif expected == "NEGATIVE" and not negative_matches:
        reasons.append("MODEL_YONU_METINLE_UYUSMUYOR")

    elif expected not in ("POSITIVE", "NEGATIVE"):
        reasons.append("DESTEKLENMEYEN_YON_ETIKETI")

    return {
        "status": "REVIEW" if reasons else "READY",
        "reasons": reasons,
        "direction_matches": matches,
    }


def combined_gate(text, raw):
    """
    1. Etiket bicimi
    2. Hedef ve degiskenin metin dayanagi
    3. Yonun metin dayanagi
    """
    previous = evidence.combined_gate(text, raw)

    if previous["status"] != "READY":
        return {
            "status": "REVIEW",
            "reasons": previous["reasons"],
            "direction_matches": {},
        }

    extraction = {
        "target": raw[0]["target"],
        "variable": raw[1]["variable"],
        "relation": raw[2]["relation"],
        "direction": raw[2]["direction"],
    }

    return direction_gate(text, extraction)


def raw_answers(direction):
    return [
        {"target": "LONG_TERM_BTC_VOL"},
        {"variable": "SP500_REALIZED_VOL"},
        {
            "relation": "EFFECT",
            "direction": direction,
        },
    ]


CASES = [
    {
        "name": "Ingilizce negatif yon, dogru etiket",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility."
        ),
        "raw": raw_answers("NEGATIVE"),
        "expected": "READY",
    },
    {
        "name": "Ingilizce negatif metin, yanlis pozitif etiket",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility."
        ),
        "raw": raw_answers("POSITIVE"),
        "expected": "REVIEW",
    },
    {
        "name": "Turkce pozitif yon, dogru etiket",
        "text": (
            "S&P 500 gerceklesen oynakliginin uzun vadeli "
            "Bitcoin oynakligi uzerinde pozitif etkisi var."
        ),
        "raw": raw_answers("POSITIVE"),
        "expected": "READY",
    },
    {
        "name": "Turkce pozitif metin, yanlis negatif etiket",
        "text": (
            "S&P 500 gerceklesen oynakliginin uzun vadeli "
            "Bitcoin oynakligi uzerinde pozitif etkisi var."
        ),
        "raw": raw_answers("NEGATIVE"),
        "expected": "REVIEW",
    },
    {
        "name": "Iki degisken var, yon ifadesi yok",
        "text": (
            "S&P 500 realized volatility is related to "
            "long-term Bitcoin volatility."
        ),
        "raw": raw_answers("POSITIVE"),
        "expected": "REVIEW",
    },
    {
        "name": "Iki yon ifadesi birden var",
        "text": (
            "S&P 500 realized volatility has a positive "
            "or negative effect on long-term Bitcoin "
            "volatility."
        ),
        "raw": raw_answers("POSITIVE"),
        "expected": "REVIEW",
    },
    {
        "name": "Basit olumsuzluk: not negative",
        "text": (
            "S&P 500 realized volatility does not have "
            "a negative effect on long-term Bitcoin "
            "volatility."
        ),
        "raw": raw_answers("NEGATIVE"),
        "expected": "REVIEW",
    },
    {
        "name": "Kapsam disi metin, sahte izinli etiketler",
        "text": "AT narrows spreads.",
        "raw": raw_answers("NEGATIVE"),
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - YON DAYANAGI KAPISI")
    print("=" * 60)
    print("Model cagrisi: YOK - kontrollu test girdileri")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0

    for index, case in enumerate(CASES, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {index}: {case['name']}")
        print("Metin:", case["text"])
        print("Modelin yon etiketi:", case["raw"][2]["direction"])

        result = combined_gate(case["text"], case["raw"])

        print("Kapi sonucu:", result["status"])
        print("Gerekceler:", result["reasons"])
        print(
            "Yon ifadeleri:",
            result["direction_matches"],
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
            "Uc kapi bu kontrollu orneklerde "
            "beklenen sonuclari verdi."
        )
    else:
        print("Beklenmeyen sonuc var; kurallari incele.")

    print(
        "UYARI: READY, iliskinin dogrulugu veya "
        "nedensellik kaniti degildir."
    )
    print(
        "Iliski turu ve karmasik dil yapilari "
        "bu testte dogrulanmadi."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()