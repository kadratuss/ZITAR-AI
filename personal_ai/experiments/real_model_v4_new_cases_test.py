import real_model_v2_bridge_test as bridge
import bridge_v4_test as v4


# Bu dosya yeni sinama orneklerini tanimlar.
# Beklenen kararlar model calistirilmadan once sabitlenmistir.
CASES = [
    {
        "name": "Ingilizce raporlama girisi - temiz iliski",
        "text": (
            "Researchers found that long-term Bitcoin volatility "
            "is negatively affected by S&P 500 realized volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Turkce raporlama girisi - temiz iliski",
        "text": (
            "Arastirmaya gore S&P 500 gerceklesen oynakligi, "
            "uzun vadeli Bitcoin oynakligini negatif etkiliyor."
        ),
        "expected": "READY",
    },
    {
        "name": "Ingilizce giristen sonra ikinci iliski",
        "text": (
            "Researchers found that long-term Bitcoin volatility "
            "is negatively affected by S&P 500 realized volatility, "
            "and copper prices influence shipping costs."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Turkce giristen sonra ikinci iliski",
        "text": (
            "Arastirmaya gore S&P 500 gerceklesen oynakligi, "
            "uzun vadeli Bitcoin oynakligini negatif etkiliyor "
            "ve bakir fiyatlari tasima maliyetlerini degistiriyor."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ingilizce raporlama girisinde belirsizlik",
        "text": (
            "Researchers are unsure whether long-term Bitcoin "
            "volatility is negatively affected by "
            "S&P 500 realized volatility."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Turkce raporlama girisinde belirsizlik",
        "text": (
            "Arastirmaya gore S&P 500 gerceklesen oynakligi, "
            "uzun vadeli Bitcoin oynakligini negatif "
            "etkiliyor olabilir."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ingilizce ters degisken yonu",
        "text": (
            "Researchers found that S&P 500 realized volatility "
            "is negatively affected by long-term Bitcoin volatility."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Turkce ters degisken yonu",
        "text": (
            "Arastirmaya gore uzun vadeli Bitcoin oynakligi, "
            "S&P 500 gerceklesen oynakligini negatif etkiliyor."
        ),
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - GERCEK OLLAMA + V4 YENI SINAMA")
    print("=" * 60)
    print("V4 kodunda degisiklik: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0
    missed_ready = 0

    for number, case in enumerate(CASES, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {number}: {case['name']}")
        print("Metin:", case["text"])
        print("Beklenen:", case["expected"])

        # Gercek yerel Ollama cagrisi.
        model_result = bridge.e2e.extract_real_model(
            case["text"]
        )

        # Modelin gercek ham cevabi V4'e aktarilir.
        result = v4.check_v4(
            case["text"],
            model_result,
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

        print("Ilk dort kapi:", model_result["status"])
        print("Ilk kapi gerekceleri:", model_result["reasons"])
        print("Ham model cevaplari:", model_result["raw"])
        print("V4 son karar:", actual)
        print("Karar asamasi:", result["stage"])
        print("Son gerekceler:", result["reasons"])
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")
    print("Yanlis READY:", false_ready)
    print("Gecerli metne REVIEW:", missed_ready)
    print(
        "NOT: Bunlar yeni secilmis sinama cumleleridir; "
        "genel model guvenilirligini olcmez."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()