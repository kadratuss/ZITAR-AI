import pair_binding_refinement_test as refined
import multi_relation_guard_test as guard


# Bilerek hazirlanmis, bicim olarak izinli model cevaplari.
# Bunlar gercek Ollama ciktisi DEGIL.
WRONG_BUT_ALLOWED = guard.raw_answers(
    target="LONG_TERM_BTC_VOL",
    variable="SP500_REALIZED_VOL",
    relation_type="EFFECT",
    direction="NEGATIVE",
)


CASES = [
    {
        "name": "Kontrol: gercek negatif etki",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Yanlis etiket: and ile baglanan altin-tahvil etkisi",
        "text": (
            "S&P 500 realized volatility and long-term "
            "Bitcoin volatility were measured, and gold "
            "has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Yanlis etiket: while ile baglanan altin-tahvil etkisi",
        "text": (
            "S&P 500 realized volatility and long-term "
            "Bitcoin volatility were measured while gold "
            "has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Yanlis etiket: iki ayri etki",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility. "
            "Gold has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Kontrol: gercek kaynak cumlesi",
        "text": (
            "We find that S&P 500 realized volatility "
            "has a negative and highly significant effect "
            "on long-term Bitcoin volatility."
        ),
        "expected": "READY",
    },
]


def main():
    print("PERSONAL AI - IZINLI AMA YANLIS ETIKET TESTI")
    print("=" * 60)
    print("Model cagrisi: YOK - sentetik ham cevaplar")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0

    for number, case in enumerate(CASES, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {number}: {case['name']}")
        print("Metin:", case["text"])
        print("Verilen etiketler:", WRONG_BUT_ALLOWED)

        old_result = guard.guarded_check(
            case["text"],
            WRONG_BUT_ALLOWED,
        )

        new_result = refined.refined_check(
            case["text"],
            WRONG_BUT_ALLOWED,
        )

        print("Onceki koruma:", old_result["status"])
        print("Iyilestirilmis koruma:", new_result["status"])
        print("Gerekceler:", new_result["reasons"])
        print("Beklenen:", case["expected"])

        ok = new_result["status"] == case["expected"]
        print("Test:", "PASS" if ok else "FAIL")

        if ok:
            passed += 1

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")
    print(
        "UYARI: Bu test gercek modelin hata oranini olcmez."
    )
    print(
        "READY yalnizca taninan acik metin kalibina uyumdur."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()