import multi_relation_guard_test as guard


RAW = guard.raw_answers(
    target="LONG_TERM_BTC_VOL",
    variable="SP500_REALIZED_VOL",
    relation_type="EFFECT",
    direction="NEGATIVE",
)


CASES = [
    {
        "name": "Kontrol: gercekten ayni iliski",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Acik: ayni cumlede baska degiskenlerin etkisi",
        "text": (
            "S&P 500 realized volatility and long-term "
            "Bitcoin volatility were measured, and gold "
            "has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Acik: while ile baglanan farkli iliski",
        "text": (
            "S&P 500 realized volatility and long-term "
            "Bitcoin volatility were measured while gold "
            "has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - AYNI CUMLE YANILTMA TESTI")
    print("=" * 60)
    print("Model cagrisi: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")
    print("Amac: Mevcut korumanin acigini tespit etmek.")

    passed = 0

    for index, case in enumerate(CASES, start=1):
        result = guard.guarded_check(
            case["text"],
            RAW,
        )

        actual = result["status"]
        expected = case["expected"]
        ok = actual == expected

        print("\n" + "-" * 60)
        print(f"TEST {index}: {case['name']}")
        print("Metin:", case["text"])
        print("Mevcut koruma:", actual)
        print("Guvenli beklenen:", expected)
        print("Gerekceler:", result["reasons"])
        print("Test:", "PASS" if ok else "FAIL - ACIK")

        if ok:
            passed += 1

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")

    if passed < len(CASES):
        print(
            "BEKLENEN BULGU: Mevcut koruma, ayni "
            "cumledeki farkli iliskileri karistirabiliyor."
        )
        print(
            "Bu bir guvenlik testidir; FAIL sonucunu "
            "basari gibi saymiyoruz."
        )

    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()