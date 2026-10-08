import re

import relation_evidence_gate_test as relation


def raw_answers(
    target="LONG_TERM_BTC_VOL",
    variable="SP500_REALIZED_VOL",
    relation_type="EFFECT",
    direction="NEGATIVE",
):
    return [
        {"target": target},
        {"variable": variable},
        {
            "relation": relation_type,
            "direction": direction,
        },
    ]


def split_sentences(text):
    """
    Bu deneyde yalnizca nokta, noktalivirgul,
    soru ve unlem isaretleriyle ayiriyoruz.
    Karmasik dil yapilari icin genel cozum degil.
    """
    return [
        part.strip()
        for part in re.split(r"[.;!?]+", text)
        if part.strip()
    ]


def relation_mentions(text):
    """
    Metindeki iliski ifadelerinin toplam tekrarini say.
    Ayni turde iki ayri etki de coklu iliski sayilir.
    """
    total = 0

    for phrases in relation.RELATION_PHRASES.values():
        for phrase in phrases:
            normalized_text = relation.evidence.normalize(text)
            normalized_phrase = relation.evidence.normalize(phrase)

            pattern = (
                r"(?<!\w)"
                + re.escape(normalized_phrase)
                + r"(?!\w)"
            )

            total += len(
                re.findall(pattern, normalized_text)
            )

    return total


def guarded_check(text, raw):
    # Once mevcut dort kapiyi calistir.
    original = relation.combined_gate(text, raw)

    if original["status"] != "READY":
        return {
            "status": "REVIEW",
            "reasons": original["reasons"],
        }

    # Birden fazla iliski ifadesi varsa tek iliskiye
    # indirgemiyoruz.
    if relation_mentions(text) != 1:
        return {
            "status": "REVIEW",
            "reasons": ["TEK_ILISKI_OLDUGU_DOGRULANAMADI"],
        }

    sentences = split_sentences(text)

    # Tum dort kapinin ayni cumlede READY vermesi gerek.
    matching_sentences = []

    for sentence in sentences:
        result = relation.combined_gate(sentence, raw)

        if result["status"] == "READY":
            matching_sentences.append(sentence)

    if len(matching_sentences) != 1:
        return {
            "status": "REVIEW",
            "reasons": ["AYNI_CUMLEDE_TAM_DAYANAK_YOK"],
        }

    return {
        "status": "READY",
        "reasons": [],
    }


CASES = [
    {
        "name": "Tek cumlede acik negatif etki",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Degiskenler ve etki farkli cumlelerde",
        "text": (
            "S&P 500 realized volatility and long-term "
            "Bitcoin volatility were measured. "
            "Gold has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ayni metinde iki negatif etki",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility. "
            "Gold has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ayni cumlede iki negatif etki",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility, "
            "and gold has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Iki farkli iliski turu",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility, "
            "and an association between them is reported."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Turkce tek cumlede negatif etki",
        "text": (
            "S&P 500 gerceklesen oynakliginin uzun vadeli "
            "Bitcoin oynakligi uzerinde negatif etkisi var."
        ),
        "expected": "READY",
    },
]


def main():
    print("PERSONAL AI - COKLU ILISKI KORUMASI")
    print("=" * 60)
    print("Model cagrisi: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0

    for index, case in enumerate(CASES, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {index}: {case['name']}")
        print("Metin:", case["text"])

        raw = raw_answers()
        original = relation.combined_gate(
            case["text"],
            raw,
        )
        guarded = guarded_check(
            case["text"],
            raw,
        )

        print("Eski dort kapi:", original["status"])
        print("Yeni korumali sonuc:", guarded["status"])
        print("Gerekceler:", guarded["reasons"])
        print("Beklenen:", case["expected"])

        ok = guarded["status"] == case["expected"]
        print("Test:", "PASS" if ok else "FAIL")

        if ok:
            passed += 1

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")
    print(
        "UYARI: Bu kontrollu test, gercek model "
        "dogrulugunu olcmez."
    )
    print(
        "Cumle ayirma ve kelime eslestirme "
        "karmasik metinlerde yetersiz kalabilir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()