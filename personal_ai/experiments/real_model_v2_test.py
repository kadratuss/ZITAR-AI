import end_to_end_gate_test as e2e
import pair_binding_v2_test as v2


# Beklentiler calistirmadan once sabitlendi.
# Bunlar modelin gercekte ne cevap vereceginin garantisi degildir.
CASES = [
    {
        "name": "Ingilizce pasif - acik negatif etki",
        "text": (
            "Long-term Bitcoin volatility is negatively "
            "affected by S&P 500 realized volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Turkce aktif - acik negatif etki",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor."
        ),
        "expected": "READY",
    },
    {
        "name": "Ters yonlu degisken cifti",
        "text": (
            "Long-term Bitcoin volatility has a negative "
            "effect on S&P 500 realized volatility."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ilgisiz altin-tahvil etkisi",
        "text": (
            "S&P 500 realized volatility and long-term "
            "Bitcoin volatility were recorded, but gold "
            "has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Pasif cumlede ikinci etki",
        "text": (
            "Long-term Bitcoin volatility is negatively "
            "affected by S&P 500 realized volatility, "
            "and gold has a positive effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Pasif ifade acikca reddediliyor",
        "text": (
            "It is not true that long-term Bitcoin volatility "
            "is negatively affected by S&P 500 realized volatility."
        ),
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - GERCEK OLLAMA + V2 TESTI")
    print("=" * 60)
    print("Model: Yerel Ollama - uc asamali cikarma")
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

        # Gercek modeli cagirir ve ham uc cevabi yakalar.
        model_result = e2e.extract_real_model(case["text"])

        print("Model / ilk dort kapi:", model_result["status"])
        print("Model gerekceleri:", model_result.get("reasons", []))
        print("Model cikarimi:", model_result.get("extraction"))
        print("Ham model cevaplari:", model_result.get("raw"))

        # Ilk kapilar REVIEW dediyse V2 ile bunu asmayiz.
        if model_result["status"] != "READY":
            actual = "REVIEW"
            stage = "MODEL_VEYA_ILK_DORT_KAPI"
            reasons = model_result.get("reasons", [])
        else:
            raw = model_result.get("raw")

            if not isinstance(raw, list) or len(raw) != 3:
                actual = "REVIEW"
                stage = "HAM_CEVAP_EKSIK"
                reasons = ["UC_HAM_CEVAP_ALINAMADI"]
            else:
                result = v2.check_v2(case["text"], raw)
                actual = result["status"]
                stage = "V2_CIFT_BAGLAMA"
                reasons = result.get("reasons", [])

        expected = case["expected"]
        ok = actual == expected

        passed += int(ok)
        false_ready += int(
            actual == "READY" and expected == "REVIEW"
        )
        missed_ready += int(
            actual == "REVIEW" and expected == "READY"
        )

        print("Son karar:", actual)
        print("Karar asamasi:", stage)
        print("Son gerekceler:", reasons)
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")
    print("Yanlis READY:", false_ready)
    print("Gecerli metne REVIEW:", missed_ready)
    print(
        "NOT: Bu kucuk test, modelin genel hata oranini "
        "veya bilimsel nedenselligi olcmez."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()