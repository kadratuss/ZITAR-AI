import bridge_v3_test as v3
import bridge_wrong_label_adversarial_test as attacks


# Gercek Ollama ciktisi DEGIL.
# Onceki deneydeki izinli etiketler ve sentetik
# ilk-kapi gerekceleri kullaniliyor.
CASES = [
    {
        "name": "Ingilizce temiz kalip - noktasiz",
        "text": (
            "Long-term Bitcoin volatility is negatively "
            "affected by S&P 500 realized volatility"
        ),
        "reasons": attacks.EN_FIRST_GATE,
        "expected": "READY",
    },
    {
        "name": "Turkce temiz kalip - noktasiz",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor"
        ),
        "reasons": attacks.TR_FIRST_GATE,
        "expected": "READY",
    },
    {
        "name": "Gecerli Ingilizce arastirmaci girisi",
        "text": (
            "Researchers found that long-term Bitcoin "
            "volatility is negatively affected by "
            "S&P 500 realized volatility."
        ),
        "reasons": attacks.EN_FIRST_GATE,
        "expected": "READY",
    },
    {
        "name": "Gecerli Turkce arastirma girisi",
        "text": (
            "Arastirmaya gore S&P 500 gerceklesen "
            "oynakligi, uzun vadeli Bitcoin "
            "oynakligini negatif etkiliyor."
        ),
        "reasons": attacks.TR_FIRST_GATE,
        "expected": "READY",
    },
    {
        "name": "Ingilizce ikinci iliski - reduces",
        "text": (
            "Long-term Bitcoin volatility is negatively "
            "affected by S&P 500 realized volatility, "
            "and oil reduces transport costs."
        ),
        "reasons": attacks.EN_FIRST_GATE,
        "expected": "REVIEW",
    },
    {
        "name": "Turkce ikinci iliski - azaltiyor",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor ve "
            "petrol tasima maliyetlerini azaltiyor."
        ),
        "reasons": attacks.TR_FIRST_GATE,
        "expected": "REVIEW",
    },
    {
        "name": "Ingilizce suphe belirten ifade",
        "text": (
            "It is unclear whether long-term Bitcoin "
            "volatility is negatively affected by "
            "S&P 500 realized volatility."
        ),
        "reasons": attacks.EN_FIRST_GATE,
        "expected": "REVIEW",
    },
    {
        "name": "Turkce suphe belirten ifade",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor "
            "olabilir."
        ),
        "reasons": attacks.TR_FIRST_GATE,
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - V3 YENI CUMLE SINAMASI")
    print("=" * 60)
    print("Ollama cagrisi: YOK")
    print("Etiketler ve ilk-kapi gerekceleri: SENTETIK")
    print("V3 kodunda degisiklik: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0
    missed_ready = 0

    for number, case in enumerate(CASES, start=1):
        result = v3.check_v3(
            case["text"],
            v3.fake_model_result(case["reasons"]),
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
        print(f"TEST {number}: {case['name']}")
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
        "Bu sinama gercek modelin hata oranini "
        "veya bilimsel nedenselligi olcmez."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()