import real_model_v2_test as real_v2
import real_model_v2_bridge_test as bridge
import bridge_v4_test as v4


def main():
    print("PERSONAL AI - GERCEK OLLAMA + V4 TESTI")
    print("=" * 60)
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0
    missed_ready = 0

    for number, case in enumerate(real_v2.CASES, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {number}: {case['name']}")
        print("Metin:", case["text"])
        print("Beklenen:", case["expected"])

        model_result = bridge.e2e.extract_real_model(case["text"])
        result = v4.check_v4(case["text"], model_result)

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

        print("Model / ilk dort kapi:", model_result["status"])
        print("Model gerekceleri:", model_result["reasons"])
        print("V4 son karar:", actual)
        print("Karar asamasi:", result["stage"])
        print("Son gerekceler:", result["reasons"])
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(real_v2.CASES)}")
    print("Yanlis READY:", false_ready)
    print("Gecerli metne REVIEW:", missed_ready)
    print(
        "NOT: Bu alti ornek daha once kullanildi; "
        "bagimsiz dogrulama degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()