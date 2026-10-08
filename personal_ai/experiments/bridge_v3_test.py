import re

import real_model_v2_bridge_test as bridge
import bridge_wrong_label_adversarial_test as attacks
import pair_binding_v2_test as v2


def check_v3(text, model_result):
    # Once mevcut koprunun kararini al.
    result = bridge.check_with_bridge(text, model_result)

    # Yalnizca yeni dar gecisin verdigi READY kararini
    # daha kati kontrol ediyoruz.
    if (
        result["status"] != "READY"
        or result["stage"] != "DAR_V2_GECISI"
    ):
        return result

    normalized = v2.ascii_lower(text).strip()

    # Sadece sondaki tek cumle noktasina izin ver.
    if normalized.endswith("."):
        normalized = normalized[:-1].strip()

    # Iliski kalibi tum metni kapsamak zorunda.
    # Boylece kalibin onune/arkasina eklenen ikinci
    # bir iliski veya baska bir ifade READY olamaz.
    en_match = v2.EN_PASSIVE.fullmatch(normalized)
    tr_match = v2.TR_ACTIVE.fullmatch(normalized)

    if not (en_match or tr_match):
        return {
            "status": "REVIEW",
            "stage": "V3_TAM_CUMLE_KONTROLU",
            "reasons": ["V3_KALIP_DISINDA_METIN_VAR"],
        }

    return result


def fake_model_result(reasons):
    # Gercek Ollama ciktisi DEGIL.
    # Onceki saldiri testindeki sentetik girdiyi koruyoruz.
    return {
        "status": "REVIEW",
        "reasons": list(reasons),
        "raw": [
            {"target": "LONG_TERM_BTC_VOL"},
            {"variable": "SP500_REALIZED_VOL"},
            {"relation": "EFFECT", "direction": "NEGATIVE"},
        ],
    }


def main():
    print("PERSONAL AI - KOPRU V3 REGRESYON TESTI")
    print("=" * 60)
    print("Ollama cagrisi: YOK")
    print("Etiketler ve ilk kapi gerekceleri: SENTETIK")
    print("Eski dosyalarda degisiklik: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0
    missed_ready = 0

    for number, case in enumerate(attacks.CASES, start=1):
        result = check_v3(
            case["text"],
            fake_model_result(case["reasons"]),
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

        print("\n" + "-" * 60)
        print(f"TEST {number}: {case['name']}")
        print("Beklenen:", expected)
        print("Gerceklesen:", actual)
        print("Asama:", result["stage"])
        print("Gerekceler:", result["reasons"])
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(attacks.CASES)}")
    print("Yanlis READY:", false_ready)
    print("Gecerli metne REVIEW:", missed_ready)
    print(
        "NOT: Bu, onceki 8 saldiri orneginin "
        "tekrar testidir; bagimsiz dogrulama degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()