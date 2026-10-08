import pair_binding_v2_test as v2


RAW = v2.RAW

# Beklentiler calistirmadan once sabitlendi.
# Gercek Ollama ciktisi degil; sentetik etiket kullaniliyor.
CASES = [
    {
        "name": "Ingilizce pasif - temiz kontrol",
        "text": (
            "Long-term Bitcoin volatility is negatively "
            "affected by S&P 500 realized volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Turkce aktif - temiz kontrol",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor."
        ),
        "expected": "READY",
    },
    {
        "name": "Pasif cumlede ikinci effect on",
        "text": (
            "Long-term Bitcoin volatility is negatively "
            "affected by S&P 500 realized volatility, "
            "and gold has a positive effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Turkce cumlede ikinci etkiliyor",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor ve "
            "altin tahvil fiyatlarini pozitif etkiliyor."
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
    {
        "name": "Turkce ifade acikca reddediliyor",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor degil."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Pasif cumlede iki ayri ifade",
        "text": (
            "Long-term Bitcoin volatility is negatively "
            "affected by S&P 500 realized volatility. "
            "Gold prices increased."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Turkce cumlede iki ayri ifade",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor. "
            "Altin fiyatlari artti."
        ),
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - V2 YENI SALDIRI TESTI")
    print("=" * 60)
    print("Model cagrisi: YOK - sentetik etiketler")
    print("Koruma kodunda degisiklik: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0
    false_review = 0

    for index, case in enumerate(CASES, start=1):
        result = v2.check_v2(case["text"], RAW)
        actual = result["status"]
        expected = case["expected"]

        ok = actual == expected
        passed += int(ok)
        false_ready += int(
            actual == "READY" and expected == "REVIEW"
        )
        false_review += int(
            actual == "REVIEW" and expected == "READY"
        )

        print("\n" + "-" * 60)
        print(f"TEST {index}: {case['name']}")
        print("Metin:", case["text"])
        print("Beklenen:", expected)
        print("Gerceklesen:", actual)
        print("Gerekceler:", result.get("reasons", []))
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")
    print("Yanlis READY:", false_ready)
    print("Gecerli metne REVIEW:", false_review)
    print(
        "Bu test gercek modelin hata oranini veya "
        "bilimsel nedenselligi olcmez."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()