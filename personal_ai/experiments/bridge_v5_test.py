import bridge_v4_test as v4
import bridge_v3_test as v3
import real_model_v2_bridge_test as bridge
import pair_binding_v2_test as v2


PREFIX = "researchers found that "

# Bu istisna icin izin verilen ham model cevaplari.
# ASSOCIATION genel olarak EFFECT'e donusturulmuyor.
EXPECTED_RAW = [
    {"target": "LONG_TERM_BTC_VOL"},
    {"variable": "SP500_REALIZED_VOL"},
    {"relation": "ASSOCIATION", "direction": "NEGATIVE"},
]

EXPECTED_REASONS = {
    "METINDE_ILISKI_TURU_DAYANAGI_YOK",
    "MODEL_ILISKI_TURU_METINLE_UYUSMUYOR",
}


def check_v5(text, model_result):
    # Once mevcut V4 karari.
    result = v4.check_v4(text, model_result)

    if result["status"] == "READY":
        return result

    # Istisna yalnizca model etiketi nedeniyle duran
    # bu belirli duruma uygulanir.
    if (
        result["stage"] != "MODEL_ETIKETLERI"
        or result["reasons"] != ["BEKLENEN_DAR_SEMA_DISINDA"]
    ):
        return result

    if model_result.get("status") != "REVIEW":
        return result

    if model_result.get("raw") != EXPECTED_RAW:
        return result

    if set(model_result.get("reasons", [])) != EXPECTED_REASONS:
        return result

    normalized = v2.ascii_lower(text).strip()

    if normalized.endswith("."):
        normalized = normalized[:-1].strip()

    if not normalized.startswith(PREFIX):
        return result

    remaining = normalized[len(PREFIX):]

    # Giristen sonraki metnin TAMAMI eslesmeli.
    # Ek iliski, olumsuzluk veya belirsizlik eklenirse
    # bu istisna READY veremez.
    if not v2.EN_PASSIVE.fullmatch(remaining):
        return result

    return {
        "status": "READY",
        "stage": "V5_METIN_KANITLI_DAR_ISTISNA",
        "reasons": [],
    }


def synthetic_result():
    # Bunlar gercek model cevaplari DEGIL.
    return {
        "status": "REVIEW",
        "reasons": sorted(EXPECTED_REASONS),
        "raw": [
            {"target": "LONG_TERM_BTC_VOL"},
            {"variable": "SP500_REALIZED_VOL"},
            {"relation": "ASSOCIATION", "direction": "NEGATIVE"},
        ],
    }


CASES = [
    (
        "Temiz raporlama cumlesi",
        "Researchers found that long-term Bitcoin volatility "
        "is negatively affected by S&P 500 realized volatility.",
        "READY",
    ),
    (
        "Ikinci iliski - influences",
        "Researchers found that long-term Bitcoin volatility "
        "is negatively affected by S&P 500 realized volatility, "
        "and gold influences bond prices.",
        "REVIEW",
    ),
    (
        "Ikinci iliski - reduces",
        "Researchers found that long-term Bitcoin volatility "
        "is negatively affected by S&P 500 realized volatility, "
        "and oil reduces shipping costs.",
        "REVIEW",
    ),
    (
        "Acik olumsuzluk",
        "Researchers found that it is not true that "
        "long-term Bitcoin volatility is negatively affected "
        "by S&P 500 realized volatility.",
        "REVIEW",
    ),
    (
        "Belirsizlik",
        "Researchers found that long-term Bitcoin volatility "
        "may be negatively affected by S&P 500 realized volatility.",
        "REVIEW",
    ),
    (
        "Ters degisken yonu",
        "Researchers found that S&P 500 realized volatility "
        "is negatively affected by long-term Bitcoin volatility.",
        "REVIEW",
    ),
]


def main():
    print("PERSONAL AI - V5 DAR ISTISNA TESTI")
    print("=" * 60)
    print("V4 kodunda degisiklik: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0

    print("\nSENTETIK SALDIRI KONTROLLERI")

    for number, (name, text, expected) in enumerate(CASES, 1):
        result = check_v5(text, synthetic_result())
        actual = result["status"]
        ok = actual == expected

        passed += int(ok)
        false_ready += int(
            actual == "READY" and expected == "REVIEW"
        )

        print("\n" + "-" * 60)
        print(f"TEST {number}: {name}")
        print("Beklenen:", expected)
        print("Gerceklesen:", actual)
        print("Asama:", result["stage"])
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 60)
    print(f"SENTETIK SONUC: {passed}/{len(CASES)}")
    print("Yanlis READY:", false_ready)

    # Gercek modelle yalnizca sorunlu tek cumle.
    text = CASES[0][1]
    print("\nGERCEK OLLAMA - TEK CUMLE")
    model_result = bridge.e2e.extract_real_model(text)
    result = check_v5(text, model_result)

    print("Ham model cevaplari:", model_result["raw"])
    print("Ilk dort kapi:", model_result["status"])
    print("Ilk kapi gerekceleri:", model_result["reasons"])
    print("V5 son karar:", result["status"])
    print("Karar asamasi:", result["stage"])
    print("Beklenen: READY")
    print(
        "Test:",
        "PASS" if result["status"] == "READY" else "FAIL",
    )

    print("\nNOT: Bu testler V5 gelistirmesinin parcasidir.")
    print("Bagimsiz dogrulama veya genel guvenlik kaniti degildir.")
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()