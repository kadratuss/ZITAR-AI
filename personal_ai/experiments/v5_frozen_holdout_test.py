import real_model_v2_bridge_test as bridge
import bridge_v5_test as v5


# Bu dosyadaki beklenen kararlar testten ONCE sabitlenmistir.
# Sonuca bakarak V5 veya beklenen etiketler degistirilmeyecek.
#
# READY: V5'in destekledigi tam metin kalibi.
# REVIEW: Dar kapsam disi veya ek/ters/belirsiz iliski.
#
# REVIEW, metindeki bilimsel iddianin yanlis oldugu anlamina gelmez.

CASES = [
    {
        "name": "Buyuk harfli Ingilizce temiz kalip",
        "text": (
            "RESEARCHERS FOUND THAT long-term Bitcoin volatility "
            "is negatively affected by S&P 500 realized volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Ingilizce temiz kalip - son nokta yok",
        "text": (
            "Researchers found that long-term Bitcoin volatility "
            "is negatively affected by S&P 500 realized volatility"
        ),
        "expected": "READY",
    },
    {
        "name": "Buyuk harfli Turkce temiz kalip",
        "text": (
            "ARASTIRMAYA GORE S&P 500 gerceklesen oynakligi, "
            "uzun vadeli Bitcoin oynakligini negatif etkiliyor."
        ),
        "expected": "READY",
    },
    {
        "name": "Turkce temiz kalip - son nokta yok",
        "text": (
            "Arastirmaya gore S&P 500 gerceklesen oynakligi, "
            "uzun vadeli Bitcoin oynakligini negatif etkiliyor"
        ),
        "expected": "READY",
    },
    {
        "name": "Ingilizce ikinci iliski - raises",
        "text": (
            "Researchers found that long-term Bitcoin volatility "
            "is negatively affected by S&P 500 realized volatility, "
            "while copper demand raises transport costs."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ingilizce ikinci iliski - correlates",
        "text": (
            "Researchers found that long-term Bitcoin volatility "
            "is negatively affected by S&P 500 realized volatility; "
            "gold correlates with bond yields."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Turkce ikinci iliski - artiriyor",
        "text": (
            "Arastirmaya gore S&P 500 gerceklesen oynakligi, "
            "uzun vadeli Bitcoin oynakligini negatif etkiliyor "
            "ve enerji maliyetleri tasima fiyatlarini artiriyor."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ingilizce olasilik",
        "text": (
            "Researchers found that long-term Bitcoin volatility "
            "could be negatively affected by S&P 500 realized volatility."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Turkce olasilik",
        "text": (
            "Arastirmaya gore S&P 500 gerceklesen oynakligi, "
            "uzun vadeli Bitcoin oynakligini negatif etkiliyor olabilir."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ingilizce ters iliski - raporlama girisi",
        "text": (
            "Researchers found that S&P 500 realized volatility "
            "is negatively affected by long-term Bitcoin volatility."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ingilizce farkli raporlama girisi",
        "text": (
            "According to the researchers, long-term Bitcoin volatility "
            "is negatively affected by S&P 500 realized volatility."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ingilizce acik ret",
        "text": (
            "Researchers found that the claim that long-term Bitcoin "
            "volatility is negatively affected by S&P 500 realized "
            "volatility is false."
        ),
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - V5 SABIT / YENI TEST KUMESI")
    print("=" * 65)
    print("V5 kodunda degisiklik: YOK")
    print("Beklenen kararlar testten once sabit.")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0
    missed_ready = 0
    failures = []

    for number, case in enumerate(CASES, 1):
        print("\n" + "-" * 65)
        print(f"TEST {number}/{len(CASES)}: {case['name']}")
        print("Metin:", case["text"])
        print("Beklenen:", case["expected"])

        # Her yeni cumle icin gercek Ollama cagrisi.
        model_result = bridge.e2e.extract_real_model(case["text"])
        result = v5.check_v5(case["text"], model_result)

        actual = result["status"]
        expected = case["expected"]
        ok = actual == expected

        passed += int(ok)

        if actual == "READY" and expected == "REVIEW":
            false_ready += 1

        if actual == "REVIEW" and expected == "READY":
            missed_ready += 1

        if not ok:
            failures.append((number, case["name"], expected, actual))

        print("Ham model cevaplari:", model_result["raw"])
        print("Ilk dort kapi:", model_result["status"])
        print("Ilk kapi gerekceleri:", model_result["reasons"])
        print("V5 karar:", actual)
        print("V5 asama:", result["stage"])
        print("V5 gerekceler:", result["reasons"])
        print("TEST:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 65)
    print(f"TOPLAM: {passed}/{len(CASES)}")
    print("Yanlis READY:", false_ready)
    print("Desteklenen kaliba REVIEW:", missed_ready)
    print("Basarisiz test sayisi:", len(failures))

    for number, name, expected, actual in failures:
        print(
            f"  TEST {number} - {name}: "
            f"beklenen={expected}, gerceklesen={actual}"
        )

    print("\nBu testte V5 veya beklenen etiketler degistirilmedi.")
    print("Bu, sinirli ve onceden belirlenmis bir test kumesidir;")
    print("genel guvenilirlik veya bilimsel nedensellik kaniti degildir.")
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()