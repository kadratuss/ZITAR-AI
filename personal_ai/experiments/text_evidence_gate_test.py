import re
import unicodedata

import scope_gate_adversarial_test as adversarial


# Bu liste yalnizca mevcut dar kapsamimiz icindir.
# Tum es anlamlilari veya Turkce ekleri kapsamaz.
LABEL_PHRASES = {
    "LONG_TERM_BTC_VOL": [
        "long-term bitcoin volatility",
        "long term bitcoin volatility",
        "uzun vadeli bitcoin oynakligi",
        "uzun vadeli btc oynakligi",
    ],
    "BITCOIN_PRICE": [
        "bitcoin price",
        "btc price",
        "bitcoin fiyati",
        "btc fiyati",
    ],
    "SP500_REALIZED_VOL": [
        "s&p 500 realized volatility",
        "sp500 realized volatility",
        "s&p 500 gerceklesen oynakligi",
        "s&p 500 gerceklesen oynakliginin",
        "sp500 gerceklesen oynakligi",
        "sp500 gerceklesen oynakliginin",
    ],
    "SP500_VOL_RISK_PREMIUM": [
        "s&p 500 volatility risk premium",
        "sp500 volatility risk premium",
        "s&p 500 oynaklik risk primi",
        "sp500 oynaklik risk primi",
    ],
    "BALTIC_DRY_INDEX": [
        "baltic dry index",
        "baltik kuru yuk endeksi",
        "baltik kuru yuk tasimaciligi endeksi",
    ],
}


def normalize(text):
    text = text.casefold().replace("ı", "i")

    # Turkce aksanlari eslestirme amaciyla sadelestir.
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )

    return re.sub(r"\s+", " ", text).strip()


def contains_phrase(text, phrase):
    """
    Ifadenin daha uzun bir kelimenin icinde degil,
    bagimsiz bir metin parcasi olarak gecmesini denetler.
    """
    pattern = (
        r"(?<!\w)"
        + re.escape(normalize(phrase))
        + r"(?!\w)"
    )

    return re.search(pattern, normalize(text)) is not None


def evidence_gate(text, extraction):
    """
    Yalnizca hedef ve aciklayici degisken icin
    metinsel dayanak arar.

    Iliski turunu veya yonunu dogrulamaz.
    """
    reasons = []
    matches = {}

    for field in ("target", "variable"):
        label = extraction.get(field)
        phrases = LABEL_PHRASES.get(label, [])

        matched = next(
            (
                phrase
                for phrase in phrases
                if contains_phrase(text, phrase)
            ),
            None,
        )

        if matched is None:
            reasons.append(
                f"METINDE_DAYANAK_YOK:{field}={label}"
            )
        else:
            matches[field] = matched

    return {
        "status": "REVIEW" if reasons else "READY",
        "reasons": reasons,
        "matches": matches,
    }


def combined_gate(text, raw):
    """
    Once mevcut bicim kapisini, ardindan metin
    dayanagi kapisini calistirir.
    """
    shape = adversarial.check_raw_responses(raw)

    if shape["status"] != "READY":
        return {
            "status": "REVIEW",
            "reasons": shape["reasons"],
            "matches": {},
        }

    return evidence_gate(text, shape["extraction"])


CASES = [
    {
        "name": "Sahte ama izinli etiketler",
        "text": "AT narrows spreads.",
        "raw": [
            {"target": "LONG_TERM_BTC_VOL"},
            {"variable": "SP500_REALIZED_VOL"},
            {
                "relation": "EFFECT",
                "direction": "NEGATIVE",
            },
        ],
        "expected": "REVIEW",
    },
    {
        "name": "Gercek kapsam ici Ingilizce cumle",
        "text": (
            "We find that S&P 500 realized volatility has "
            "a negative and highly significant effect on "
            "long-term Bitcoin volatility."
        ),
        "raw": [
            {"target": "LONG_TERM_BTC_VOL"},
            {"variable": "SP500_REALIZED_VOL"},
            {
                "relation": "EFFECT",
                "direction": "NEGATIVE",
            },
        ],
        "expected": "READY",
    },
    {
        "name": "Gercek kapsam ici Turkce iddia",
        "text": (
            "S&P 500 gerceklesen oynakliginin uzun vadeli "
            "Bitcoin oynakligi uzerinde negatif etkisi var."
        ),
        "raw": [
            {"target": "LONG_TERM_BTC_VOL"},
            {"variable": "SP500_REALIZED_VOL"},
            {
                "relation": "EFFECT",
                "direction": "NEGATIVE",
            },
        ],
        "expected": "READY",
    },
    {
        "name": "Hedef var, aciklayici degisken yok",
        "text": "Long-term Bitcoin volatility is increasing.",
        "raw": [
            {"target": "LONG_TERM_BTC_VOL"},
            {"variable": "SP500_REALIZED_VOL"},
            {
                "relation": "EFFECT",
                "direction": "POSITIVE",
            },
        ],
        "expected": "REVIEW",
    },
    {
        "name": "Aciklayici degisken var, hedef yok",
        "text": "S&P 500 realized volatility increased.",
        "raw": [
            {"target": "LONG_TERM_BTC_VOL"},
            {"variable": "SP500_REALIZED_VOL"},
            {
                "relation": "EFFECT",
                "direction": "POSITIVE",
            },
        ],
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - METIN DAYANAGI KAPISI")
    print("=" * 60)
    print("Model cagrisi: YOK - kontrollu test girdileri")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0

    for index, case in enumerate(CASES, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {index}: {case['name']}")
        print("Metin:", case["text"])

        result = combined_gate(
            case["text"],
            case["raw"],
        )

        print("Kapi sonucu:", result["status"])
        print("Gerekceler:", result["reasons"])
        print("Bulunan ifadeler:", result["matches"])

        ok = result["status"] == case["expected"]

        print("Beklenen:", case["expected"])
        print("Test:", "PASS" if ok else "FAIL")

        if ok:
            passed += 1

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")

    if passed == len(CASES):
        print(
            "Kontrollu orneklerde iki kapi beklenen "
            "sonuclari verdi."
        )
    else:
        print("Beklenmeyen sonuc var; kurallari incele.")

    print(
        "UYARI: READY yalnizca etiket bicimi ve "
        "metindeki ifade eslesmesi anlamina gelir."
    )
    print(
        "Iliski turu, yon, nedensellik ve iddianin "
        "dogrulugu bu testte kontrol edilmedi."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()