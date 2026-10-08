import real_model_v2_bridge_test as bridge


RAW = [
    {"target": "LONG_TERM_BTC_VOL"},
    {"variable": "SP500_REALIZED_VOL"},
    {"relation": "EFFECT", "direction": "NEGATIVE"},
]

# Gercek model ciktisi DEGIL.
# Ilk kapilarin yalnizca tanidigimiz eksikligi bildirdigini
# varsayan sentetik sonuc.
EN_FIRST_GATE = [
    "METINDE_ILISKI_TURU_DAYANAGI_YOK",
    "MODEL_ILISKI_TURU_METINLE_UYUSMUYOR",
]

TR_FIRST_GATE = [
    "METINDE_DAYANAK_YOK:target=LONG_TERM_BTC_VOL",
]


# Beklentiler test calistirilmadan once sabitlendi.
CASES = [
    {
        "name": "Ingilizce temiz kontrol",
        "text": (
            "Long-term Bitcoin volatility is negatively "
            "affected by S&P 500 realized volatility."
        ),
        "reasons": EN_FIRST_GATE,
        "expected": "READY",
    },
    {
        "name": "Turkce temiz kontrol",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor."
        ),
        "reasons": TR_FIRST_GATE,
        "expected": "READY",
    },
    {
        "name": "Pasif kalip ve ikinci effect on",
        "text": (
            "Long-term Bitcoin volatility is negatively "
            "affected by S&P 500 realized volatility, "
            "while gold has a negative effect on bond prices."
        ),
        "reasons": EN_FIRST_GATE,
        "expected": "REVIEW",
    },
    {
        "name": "Turkce kalip ve ikinci etkiliyor",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor ve "
            "altin tahvil fiyatlarini negatif etkiliyor."
        ),
        "reasons": TR_FIRST_GATE,
        "expected": "REVIEW",
    },
    {
        "name": "Pasif kalip acikca reddediliyor",
        "text": (
            "It is not true that long-term Bitcoin volatility "
            "is negatively affected by S&P 500 realized volatility."
        ),
        "reasons": EN_FIRST_GATE,
        "expected": "REVIEW",
    },
    {
        "name": "Turkce kalip acikca reddediliyor",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor degil."
        ),
        "reasons": TR_FIRST_GATE,
        "expected": "REVIEW",
    },
    {
        "name": "Pasif kalip ve farkli fiille ikinci iliski",
        "text": (
            "Long-term Bitcoin volatility is negatively "
            "affected by S&P 500 realized volatility, "
            "and gold influences bond prices."
        ),
        "reasons": EN_FIRST_GATE,
        "expected": "REVIEW",
    },
    {
        "name": "Turkce kalip ve farkli fiille ikinci iliski",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor ve "
            "altin tahvil fiyatlarini degistiriyor."
        ),
        "reasons": TR_FIRST_GATE,
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - KOPRU YANLIS ETIKET SALDIRI TESTI")
    print("=" * 60)
    print("Ollama cagrisi: YOK")
    print("Etiketler: SENTETIK, bilerek sabit tutuldu")
    print("Koruma kodunda degisiklik: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0
    missed_ready = 0

    for index, case in enumerate(CASES, start=1):
        # Model gercekte calistirilmiyor.
        # Kopruye, izinli etiketli ama ilk kapilarda
        # belirli gerekcelerle REVIEW olmus bir sonuc veriyoruz.
        fake_model_result = {
            "status": "REVIEW",
            "reasons": list(case["reasons"]),
            "raw": [
                {"target": RAW[0]["target"]},
                {"variable": RAW[1]["variable"]},
                {
                    "relation": RAW[2]["relation"],
                    "direction": RAW[2]["direction"],
                },
            ],
        }

        result = bridge.check_with_bridge(
            case["text"],
            fake_model_result,
        )

        actual = result["status"]
        expected = case["expected"]
        ok = actual == expected

        passed += int(ok)
        false_ready += int(
            actual == "READY" and expected == "REVIEW"
        )
        missed_ready += int(
            actual == "REVIEW" and expected == "READY"
        )

        print("\n" + "-" * 60)
        print(f"TEST {index}: {case['name']}")
        print("Metin:", case["text"])
        print("Beklenen:", expected)
        print("Gerceklesen:", actual)
        print("Asama:", result["stage"])
        print("Gerekceler:", result["reasons"])
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")
    print("Yanlis READY:", false_ready)
    print("Gecerli metne REVIEW:", missed_ready)
    print(
        "NOT: Ilk kapi gerekceleri de sentetiktir; "
        "bu test gercek model davranisini olcmez."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()