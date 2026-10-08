import json

import end_to_end_gate_test as e2e
import pair_binding_refinement_test as refined


SOURCE = (
    "We find that S&P 500 realized volatility has a "
    "negative and highly significant effect on "
    "long-term Bitcoin volatility."
)

CASES = [
    {
        "name": "Ayni yonlu Ingilizce iddia",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility."
        ),
        "expected": "CONSISTENT",
    },
    {
        "name": "Ters yonlu iddia - bu korumada desteklenmiyor",
        "text": (
            "S&P 500 realized volatility has a positive "
            "effect on long-term Bitcoin volatility."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ayni cumlede ilgisiz altin-tahvil etkisi",
        "text": (
            "S&P 500 realized volatility and long-term "
            "Bitcoin volatility were measured, and gold "
            "has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "While ile baglanan ilgisiz etki",
        "text": (
            "S&P 500 realized volatility and long-term "
            "Bitcoin volatility were measured while gold "
            "has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Ayni yonlu Turkce iddia",
        "text": (
            "S&P 500 gerceklesen oynakliginin uzun vadeli "
            "Bitcoin oynakligi uzerinde negatif etkisi var."
        ),
        "expected": "CONSISTENT",
    },
]


def show(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def extract_and_check(text):
    # Gercek Ollama cagrisi ve mevcut dort kapi.
    model_result = e2e.extract_real_model(text)

    if model_result["status"] != "READY":
        return {
            "status": "REVIEW",
            "reasons": model_result["reasons"],
            "extraction": model_result["extraction"],
        }

    # Mevcut dort kapi gectikten sonra coklu iliski
    # ve iyilestirilmis degisken-cifti korumasi.
    pair_result = refined.refined_check(
        text,
        model_result["raw"],
    )

    return {
        "status": pair_result["status"],
        "reasons": pair_result["reasons"],
        "extraction": model_result["extraction"],
    }


def compare(source, claim):
    if source["status"] != "READY":
        return "REVIEW", "KAYNAK_KORUMADAN_GECMEDI"

    if claim["status"] != "READY":
        return "REVIEW", "IDDIA_KORUMADAN_GECMEDI"

    verdict = e2e.base.decide(
        source["extraction"],
        claim["extraction"],
    )

    return verdict, "IKI_METIN_DE_KORUMADAN_GECTI"


def main():
    print("PERSONAL AI - GERCEK MODEL + CIFTLENDIRME KORUMASI")
    print("=" * 60)
    print("Model:", e2e.base.MODEL)
    print("Veritabani yazma: YOK")
    print("Strateji ve alim-satim: KAPALI")

    print("\nKAYNAK")
    print(SOURCE)

    source = extract_and_check(SOURCE)
    print("Kaynak sonucu:", source["status"])
    print("Kaynak gerekceleri:", show(source["reasons"]))

    source_gold = {
        "target": "LONG_TERM_BTC_VOL",
        "variable": "SP500_REALIZED_VOL",
        "relation": "EFFECT",
        "direction": "NEGATIVE",
    }

    if (
        source["status"] == "READY"
        and source["extraction"] != source_gold
    ):
        source["status"] = "REVIEW"
        source["reasons"] = [
            "KAYNAK_BEKLENEN_ETIKETLERLE_UYUSMUYOR"
        ]
        print("Kaynak ek kontrolu:", show(source["reasons"]))

    passed = 0

    for number, case in enumerate(CASES, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {number}: {case['name']}")
        print("Iddia:", case["text"])

        claim = extract_and_check(case["text"])

        print("Iddia sonucu:", claim["status"])
        print("Iddia gerekceleri:", show(claim["reasons"]))
        print("Model etiketleri:", show(claim["extraction"]))

        verdict, reason = compare(source, claim)

        print("Python karari:", verdict)
        print("Karar gerekcesi:", reason)
        print("Beklenen:", case["expected"])

        ok = verdict == case["expected"]
        print("Test:", "PASS" if ok else "FAIL")
        passed += int(ok)

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")
    print(
        "Bu sonuc yalnizca bu kaynak, bu iddialar "
        "ve bu calistirma icin gecerlidir."
    )
    print(
        "READY, bilimsel dogruluk veya nedensellik "
        "kaniti degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()