import bridge_v3_test as v3
import bridge_wrong_label_adversarial_test as attacks
import bridge_v3_new_cases_test as new_cases
import pair_binding_v2_test as v2


# Yalnizca bu iki raporlama girisi destekleniyor.
EN_PREFIX = "researchers found that "
TR_PREFIX = "arastirmaya gore "


def check_v4(text, model_result):
    # Once V3'u calistir. Eski READY kararlarini koru.
    result = v3.check_v3(text, model_result)

    if result["status"] == "READY":
        return result

    # V4 sadece V3'un tam cumle kontrolune takilan
    # dar gecis adaylarini yeniden degerlendirir.
    if (
        result["stage"] != "V3_TAM_CUMLE_KONTROLU"
        or result["reasons"] != ["V3_KALIP_DISINDA_METIN_VAR"]
    ):
        return result

    normalized = v2.ascii_lower(text).strip()

    # Yalnizca sondaki tek noktayi kaldir.
    if normalized.endswith("."):
        normalized = normalized[:-1].strip()

    if normalized.startswith(EN_PREFIX):
        remaining = normalized[len(EN_PREFIX):]

        # Giristen sonraki metnin TAMAMI dogru
        # degisken cifti ve iliski kalibi olmali.
        matched = v2.EN_PASSIVE.fullmatch(remaining)

    elif normalized.startswith(TR_PREFIX):
        remaining = normalized[len(TR_PREFIX):]
        matched = v2.TR_ACTIVE.fullmatch(remaining)

    else:
        return result

    if not matched:
        return {
            "status": "REVIEW",
            "stage": "V4_GIRIS_SONRASI_TAM_ESLESME",
            "reasons": ["V4_KALIP_DISINDA_METIN_VAR"],
        }

    return {
        "status": "READY",
        "stage": "V4_DAR_RAPORLAMA_GIRISI",
        "reasons": [],
    }


def run_group(group_name, cases):
    print("\n" + "=" * 60)
    print(group_name)
    print("=" * 60)

    passed = 0
    false_ready = 0
    missed_ready = 0

    for number, case in enumerate(cases, start=1):
        # Model ve ilk-kapi gerekceleri sentetiktir.
        model_result = v3.fake_model_result(
            case["reasons"]
        )

        result = check_v4(
            case["text"],
            model_result,
        )

        actual = result["status"]
        expected = case["expected"]
        ok = actual == expected

        passed += int(ok)

        if actual == "READY" and expected == "REVIEW":
            false_ready += 1

        if actual == "REVIEW" and expected == "READY":
            missed_ready += 1

        print("\n" + "-" * 60)
        print(f"TEST {number}: {case['name']}")
        print("Beklenen:", expected)
        print("Gerceklesen:", actual)
        print("Asama:", result["stage"])
        print("Gerekceler:", result["reasons"])
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "-" * 60)
    print(f"GRUP SONUCU: {passed}/{len(cases)}")
    print("Yanlis READY:", false_ready)
    print("Gecerli metne REVIEW:", missed_ready)

    return passed, false_ready, missed_ready


def main():
    print("PERSONAL AI - KOPRU V4 REGRESYON TESTI")
    print("=" * 60)
    print("Ollama cagrisi: YOK")
    print("Etiketler ve ilk-kapi gerekceleri: SENTETIK")
    print("Eski dosyalarda degisiklik: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    old_passed, old_false, old_missed = run_group(
        "ESKI 8 SALDIRI ORNEGI",
        attacks.CASES,
    )

    new_passed, new_false, new_missed = run_group(
        "SONRAKI 8 CUMLE",
        new_cases.CASES,
    )

    total = len(attacks.CASES) + len(new_cases.CASES)

    print("\n" + "=" * 60)
    print(f"TOPLAM: {old_passed + new_passed}/{total}")
    print("Yanlis READY:", old_false + new_false)
    print("Gecerli metne REVIEW:", old_missed + new_missed)
    print(
        "NOT: Bunlar gelistirmede kullanilan eski "
        "16 ornegin tekrar testidir."
    )
    print("Bagimsiz dogrulama veya genel guvenlik kaniti degildir.")
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()