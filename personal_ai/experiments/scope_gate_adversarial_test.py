import json

import scope_gate_test as gate


# Bilerek olusturulmus ham model cevaplari.
# Bunlar Ollama'nin gercek cevaplari DEGIL.
CASES = [
    {
        "name": "Kapsam disi metin, gecersiz etiket",
        "text": "AT narrows spreads.",
        "raw": [
            {"target": "UNKNOWN"},
            {"variable": "AT"},
            {"relation": "EFFECT", "direction": "NEGATIVE"},
        ],
        "expected": "REVIEW",
    },
    {
        "name": "Kapsam disi metin, sahte ama izinli etiketler",
        "text": "AT narrows spreads.",
        "raw": [
            {"target": "LONG_TERM_BTC_VOL"},
            {"variable": "SP500_REALIZED_VOL"},
            {"relation": "EFFECT", "direction": "NEGATIVE"},
        ],
        "expected": "READY",
    },
    {
        "name": "Eksik alan",
        "text": "AT narrows spreads.",
        "raw": [
            {},
            {"variable": "SP500_REALIZED_VOL"},
            {"relation": "EFFECT", "direction": "NEGATIVE"},
        ],
        "expected": "REVIEW",
    },
    {
        "name": "Yanlis veri tipi",
        "text": "AT narrows spreads.",
        "raw": [
            {"target": 123},
            {"variable": "SP500_REALIZED_VOL"},
            {"relation": "EFFECT", "direction": "NEGATIVE"},
        ],
        "expected": "REVIEW",
    },
]


def check_raw_responses(raw_responses):
    """
    Mevcut kapsam kapisinin alan/etiket kurallarini
    ham cevaplar uzerinde uygular.

    Bu fonksiyon metnin anlamini kontrol ETMEZ.
    """
    expected_keys = [
        {"target"},
        {"variable"},
        {"relation", "direction"},
    ]

    combined = {}
    reasons = []

    for index, (raw, keys) in enumerate(
        zip(raw_responses, expected_keys),
        start=1,
    ):
        if not isinstance(raw, dict):
            reasons.append(
                f"GECERSIZ_JSON_YAPISI:ASAMA_{index}"
            )
            continue

        if set(raw) != keys:
            reasons.append(
                f"EKSIK_VEYA_FAZLA_ANAHTAR:ASAMA_{index}"
            )
            continue

        for field in keys:
            value = raw[field]
            combined[field] = value

            problem = gate.check_field(field, value)
            if problem is not None:
                reasons.append(problem)

    if set(combined) != set(gate.SCHEMA):
        reasons.append("TAMAMLANMAMIS_CIKARIM")

    return {
        "status": "REVIEW" if reasons else "READY",
        "reasons": reasons,
        "extraction": combined,
    }


def main():
    print("PERSONAL AI - KAPSAM KAPISI SINIR TESTI")
    print("=" * 60)
    print("Model cagrisi: YOK - cevaplar kontrollu taklit")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0

    for index, case in enumerate(CASES, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {index}: {case['name']}")
        print("Metin:", case["text"])

        result = check_raw_responses(case["raw"])

        print(
            "Ham cevaplar:",
            json.dumps(case["raw"], ensure_ascii=False),
        )
        print("Kapi sonucu:", result["status"])
        print(
            "Gerekceler:",
            json.dumps(result["reasons"], ensure_ascii=False),
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
            "Kapinin mevcut kurallari beklenen sekilde "
            "calisti."
        )
        print(
            "KRITIK BULGU: Gecerli gorunen yanlis "
            "etiketler READY gecebilir."
        )
    else:
        print(
            "Beklenmeyen sonuc var; kapi mantigi "
            "incelenmeli."
        )

    print("Bu test model dogrulugu olcmez.")
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()