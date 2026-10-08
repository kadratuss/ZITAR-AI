import real_model_v2_test as old_cases
import real_model_v4_new_cases_test as new_cases
import real_model_v2_bridge_test as bridge
import bridge_v4_test as v4
import bridge_v5_test as v5


CASES = [
    ("ONCEKI_6", case)
    for case in old_cases.CASES
] + [
    ("SONRAKI_8", case)
    for case in new_cases.CASES
]


def main():
    print("PERSONAL AI - GERCEK OLLAMA / V4 - V5 REGRESYON")
    print("=" * 65)
    print("V4 ve V5 kodunda degisiklik: YOK")
    print("Her cumle icin TEK model ciktisi iki surume verilir.")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    v4_passed = 0
    v5_passed = 0
    v5_false_ready = 0
    v5_missed_ready = 0
    changed = []

    for number, (group, case) in enumerate(CASES, start=1):
        text = case["text"]
        expected = case["expected"]

        print("\n" + "-" * 65)
        print(f"TEST {number}/{len(CASES)} [{group}]: {case['name']}")
        print("Metin:", text)
        print("Beklenen:", expected)

        # Gercek Ollama bir kez cagrilir.
        model_result = bridge.e2e.extract_real_model(text)

        # Iki surum de ayni ham model cevabini kullanir.
        result_v4 = v4.check_v4(text, model_result)
        result_v5 = v5.check_v5(text, model_result)

        actual_v4 = result_v4["status"]
        actual_v5 = result_v5["status"]

        v4_ok = actual_v4 == expected
        v5_ok = actual_v5 == expected

        v4_passed += int(v4_ok)
        v5_passed += int(v5_ok)

        v5_false_ready += int(
            actual_v5 == "READY" and expected == "REVIEW"
        )
        v5_missed_ready += int(
            actual_v5 == "REVIEW" and expected == "READY"
        )

        if actual_v4 != actual_v5:
            changed.append(
                (number, case["name"], actual_v4, actual_v5)
            )

        print("Ham model cevaplari:", model_result["raw"])
        print("Ilk dort kapi:", model_result["status"])
        print("Ilk kapi gerekceleri:", model_result["reasons"])
        print("V4:", actual_v4, "| Asama:", result_v4["stage"])
        print("V5:", actual_v5, "| Asama:", result_v5["stage"])
        print("V5 gerekceleri:", result_v5["reasons"])
        print("V4 test:", "PASS" if v4_ok else "FAIL")
        print("V5 test:", "PASS" if v5_ok else "FAIL")

    print("\n" + "=" * 65)
    print(f"V4 SONUC: {v4_passed}/{len(CASES)}")
    print(f"V5 SONUC: {v5_passed}/{len(CASES)}")
    print("V5 yanlis READY:", v5_false_ready)
    print("V5 gecerli metne REVIEW:", v5_missed_ready)
    print("V4 ile V5 arasinda karari degisen ornek:", len(changed))

    for number, name, before, after in changed:
        print(f"  TEST {number} - {name}: {before} -> {after}")

    print(
        "NOT: Bu 14 cumle daha once kullanildi; "
        "bagimsiz dogrulama degildir."
    )
    print(
        "Model yeniden cagrildigi icin sonuclar "
        "onceki calistirmalardan farkli olabilir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()