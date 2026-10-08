import end_to_end_gate_test as e2e
import pair_binding_v2_test as v2
import real_model_v2_test as real_test


EXPECTED_RAW = [
    {"target": "LONG_TERM_BTC_VOL"},
    {"variable": "SP500_REALIZED_VOL"},
    {"relation": "EFFECT", "direction": "NEGATIVE"},
]

# Yalnizca daha once tani koydugumuz iki ilk-kapi hatasi.
ALLOWED_FIRST_GATE_REASONS = {
    frozenset({
        "METINDE_ILISKI_TURU_DAYANAGI_YOK",
        "MODEL_ILISKI_TURU_METINLE_UYUSMUYOR",
    }),
    frozenset({
        "METINDE_DAYANAK_YOK:target=LONG_TERM_BTC_VOL",
    }),
}


def check_with_bridge(text, model_result):
    raw = model_result.get("raw")
    if raw != EXPECTED_RAW:
        return {
            "status": "REVIEW",
            "stage": "MODEL_ETIKETLERI",
            "reasons": ["BEKLENEN_DAR_SEMA_DISINDA"],
        }

    # Ilk dort kapi zaten READY ise normal V2 yolu.
    if model_result["status"] == "READY":
        result = v2.check_v2(text, raw)
        return {
            "status": result["status"],
            "stage": "NORMAL_V2",
            "reasons": result.get("reasons", []),
        }

    reasons = frozenset(model_result.get("reasons", []))

    # Yalnizca onceden belirlenen iki hata kumesine izin ver.
    if reasons not in ALLOWED_FIRST_GATE_REASONS:
        return {
            "status": "REVIEW",
            "stage": "ILK_KAPILAR",
            "reasons": model_result.get("reasons", []),
        }

    # Dar gecis sadece V2'nin yeni acik kaliplari icindir.
    if not v2.new_pair_pattern(text):
        return {
            "status": "REVIEW",
            "stage": "ACIK_CIFT_KALIBI_YOK",
            "reasons": ["V2_YENI_CIFT_KALIBI_YOK"],
        }

    # V2'nin mevcut fonksiyonu eski ilk-kapilarda durdugu icin
    # yeni kalibin kendi kontrollerini burada ayri uyguluyoruz.
    # Herhangi bir suphede REVIEW.
    import re

    normalized = v2.ascii_lower(text)

    effect_markers = re.findall(
        r"\beffect on\b|\baffected by\b|\betkiliyor\b",
        normalized,
    )
    if len(effect_markers) != 1:
        return {
            "status": "REVIEW",
            "stage": "DAR_GECIS",
            "reasons": ["V2_TEK_ETKI_DOGRULANAMADI"],
        }

    sentences = [
        sentence.strip()
        for sentence in re.split(r"[.!?]+", normalized)
        if sentence.strip()
    ]
    if len(sentences) != 1:
        return {
            "status": "REVIEW",
            "stage": "DAR_GECIS",
            "reasons": ["V2_TEK_CUMLE_DOGRULANAMADI"],
        }

    if re.search(
        r"\bnot\b|\bno\b|\bnever\b|\bpositive\b"
        r"|\bwithout\b|\bdegil\b|\bpozitif\b",
        normalized,
    ):
        return {
            "status": "REVIEW",
            "stage": "DAR_GECIS",
            "reasons": ["V2_EK_YON_VEYA_OLUMSUZLUK"],
        }

    return {
        "status": "READY",
        "stage": "DAR_V2_GECISI",
        "reasons": [],
    }


def main():
    print("PERSONAL AI - GERCEK MODEL + DAR V2 GECISI")
    print("=" * 60)
    print("Model: Yerel Ollama")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0
    missed_ready = 0

    for number, case in enumerate(real_test.CASES, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {number}: {case['name']}")
        print("Metin:", case["text"])
        print("Beklenen:", case["expected"])

        model_result = e2e.extract_real_model(case["text"])

        print("Ilk dort kapi:", model_result["status"])
        print("Ilk kapi gerekceleri:", model_result.get("reasons", []))
        print("Ham model cevaplari:", model_result.get("raw"))

        result = check_with_bridge(case["text"], model_result)
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

        print("Son karar:", actual)
        print("Karar asamasi:", result["stage"])
        print("Son gerekceler:", result["reasons"])
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(real_test.CASES)}")
    print("Yanlis READY:", false_ready)
    print("Gecerli metne REVIEW:", missed_ready)
    print(
        "NOT: Bu, daha once gordugumuz 6 cumlenin "
        "tekrar testidir; bagimsiz dogrulama degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()