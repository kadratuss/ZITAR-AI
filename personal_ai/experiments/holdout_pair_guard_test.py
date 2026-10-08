import pair_binding_refinement_test as refined
import multi_relation_guard_test as guard


# Sabit, sentetik model etiketleri.
# Gercek Ollama ciktisi DEGIL.
RAW = guard.raw_answers(
    target="LONG_TERM_BTC_VOL",
    variable="SP500_REALIZED_VOL",
    relation_type="EFFECT",
    direction="NEGATIVE",
)


# Beklenen kararlar test calistirilmadan once belirlendi.
# Bu dosyadaki beklentileri sonuca bakarak degistirmeyin.
CASES = [
    {
        "name": "Acik etki - farkli giris ifadesi",
        "text": (
            "Our analysis indicates that S&P 500 realized "
            "volatility has a negative effect on long-term "
            "Bitcoin volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Acik etki - farkli raporlama ifadesi",
        "text": (
            "The researchers report that S&P 500 realized "
            "volatility has a negative and highly significant "
            "effect on long-term Bitcoin volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Degiskenlerin yeri ters",
        "text": (
            "Long-term Bitcoin volatility has a negative "
            "effect on S&P 500 realized volatility."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ilgisiz etki ayni cumlede",
        "text": (
            "S&P 500 realized volatility and long-term "
            "Bitcoin volatility were recorded, but oil "
            "has a negative effect on shipping costs."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Pozitif etki, negatif etiket verilmis",
        "text": (
            "S&P 500 realized volatility has a positive "
            "effect on long-term Bitcoin volatility."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Olumsuzlanan negatif etki",
        "text": (
            "S&P 500 realized volatility does not have "
            "a negative effect on long-term Bitcoin "
            "volatility."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Etki yerine iliski anlatiliyor",
        "text": (
            "There is a negative association between "
            "S&P 500 realized volatility and long-term "
            "Bitcoin volatility."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ayni metinde ikinci etki",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility. "
            "Oil has a negative effect on shipping costs."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Gecerli anlam, farkli Ingilizce kalip",
        "text": (
            "Long-term Bitcoin volatility is negatively "
            "affected by S&P 500 realized volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Gecerli anlam, farkli Turkce kalip",
        "text": (
            "S&P 500 gerceklesen oynakligi, uzun vadeli "
            "Bitcoin oynakligini negatif etkiliyor."
        ),
        "expected": "READY",
    },
]


def main():
    print("PERSONAL AI - YENI CUMLELERLE SABIT SINAMA")
    print("=" * 60)
    print("Model cagrisi: YOK - sentetik etiketler")
    print("Koruma kodunda degisiklik: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0
    false_review = 0

    for number, case in enumerate(CASES, start=1):
        result = refined.refined_check(
            case["text"],
            RAW,
        )

        actual = result["status"]
        expected = case["expected"]
        ok = actual == expected

        passed += int(ok)

        if actual == "READY" and expected == "REVIEW":
            false_ready += 1

        if actual == "REVIEW" and expected == "READY":
            false_review += 1

        print("\n" + "-" * 60)
        print(f"TEST {number}: {case['name']}")
        print("Metin:", case["text"])
        print("Beklenen:", expected)
        print("Gerceklesen:", actual)
        print("Gerekceler:", result["reasons"])
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")
    print("Yanlis READY:", false_ready)
    print("Gecerli metne REVIEW:", false_review)

    if false_ready:
        print(
            "DIKKAT: En az bir yaniltici metin "
            "yanlislikla READY oldu."
        )

    if false_review:
        print(
            "DIKKAT: En az bir gecerli ifade "
            "dar kalip nedeniyle REVIEW oldu."
        )

    print(
        "Bu sonuc gercek modelin dogrulugunu "
        "veya bilimsel nedenselligi olcmez."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()