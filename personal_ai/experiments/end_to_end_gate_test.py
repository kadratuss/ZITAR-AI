import json

import three_stage_relation_test as three
import scope_gate_adversarial_test as shape_gate
import text_evidence_gate_test as text_gate
import direction_evidence_gate_test as direction_gate
import relation_evidence_gate_test as relation_gate


base = three.base

SOURCE_TEXT = (
    "We find that S&P 500 realized volatility has a "
    "negative and highly significant effect on "
    "long-term Bitcoin volatility."
)

# Beklenen kararlar model calistirilmadan once sabitlendi.
# Bunlar kaynak metninin destekledigi dar iliskiye goredir.
CASES = [
    {
        "name": "Yeni Ingilizce ifade - ayni yon",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility."
        ),
        "expected": "CONSISTENT",
    },
    {
        "name": "Yeni Ingilizce ifade - ters yon",
        "text": (
            "S&P 500 realized volatility has a positive "
            "effect on long-term Bitcoin volatility."
        ),
        "expected": "CONTRADICTION",
    },
    {
        "name": "Turkce ifade - ayni yon",
        "text": (
            "S&P 500 gerceklesen oynakliginin uzun vadeli "
            "Bitcoin oynakligi uzerinde negatif etkisi var."
        ),
        "expected": "CONSISTENT",
    },
    {
        "name": "Yon belirtilmeyen ifade",
        "text": (
            "S&P 500 realized volatility has an effect on "
            "long-term Bitcoin volatility."
        ),
        "expected": "REVIEW",
    },
]


def show(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def extract_real_model(text):
    """
    Mevcut uc asamali model fonksiyonunu degistirmeden
    cagirir ve ham cevaplarini kaydeder.
    """
    captured = []
    original = base.ask_ollama

    def capture(system_prompt, user_text):
        raw = original(system_prompt, user_text)
        captured.append(raw)
        return raw

    base.ask_ollama = capture

    try:
        model_result = three.extract_three_stage(text)
    except Exception as error:
        return {
            "status": "REVIEW",
            "reasons": ["MODEL_HATASI:" + repr(error)],
            "extraction": None,
            "raw": captured,
        }
    finally:
        base.ask_ollama = original

    print("  Ham model cevaplari:", show(captured))
    print("  Modelin birlesik ciktisi:", show(model_result))

    if len(captured) != 3:
        return {
            "status": "REVIEW",
            "reasons": [
                "BEKLENEN_UC_ASAMA_TAMAMLANMADI"
            ],
            "extraction": model_result,
            "raw": captured,
        }

    # Birinci kapi: ham cevaplarin bicimi ve etiketleri.
    shape = shape_gate.check_raw_responses(captured)

    if shape["status"] != "READY":
        return {
            "status": "REVIEW",
            "reasons": shape["reasons"],
            "extraction": shape["extraction"],
            "raw": captured,
        }

    extraction = shape["extraction"]

    # Modelin kendi birlestirmesiyle ham cevaplardan
    # elde ettigimiz sonuc farkliysa devam etmiyoruz.
    if model_result != extraction:
        return {
            "status": "REVIEW",
            "reasons": ["BIRLESIK_CIKTI_HAM_CEVAPLARDAN_FARKLI"],
            "extraction": extraction,
            "raw": captured,
        }

    # Ikinci kapi: hedef ve degisken metinde var mi?
    text_result = text_gate.evidence_gate(text, extraction)

    if text_result["status"] != "READY":
        return {
            "status": "REVIEW",
            "reasons": text_result["reasons"],
            "extraction": extraction,
            "raw": captured,
        }

    # Ucuncu kapi: yonun metinsel dayanagi var mi?
    direction_result = direction_gate.direction_gate(
        text,
        extraction,
    )

    if direction_result["status"] != "READY":
        return {
            "status": "REVIEW",
            "reasons": direction_result["reasons"],
            "extraction": extraction,
            "raw": captured,
        }

    # Dorduncu kapi: iliski turunun dayanagi var mi?
    relation_result = relation_gate.relation_gate(
        text,
        extraction,
    )

    if relation_result["status"] != "READY":
        return {
            "status": "REVIEW",
            "reasons": relation_result["reasons"],
            "extraction": extraction,
            "raw": captured,
        }

    return {
        "status": "READY",
        "reasons": [],
        "extraction": extraction,
        "raw": captured,
    }


def compare(source, claim):
    if source["status"] != "READY":
        return "REVIEW", "KAYNAK_KAPILARDAN_GECMEDI"

    if claim["status"] != "READY":
        return "REVIEW", "IDDIA_KAPILARDAN_GECMEDI"

    verdict = base.decide(
        source["extraction"],
        claim["extraction"],
    )

    return verdict, "IKI_METIN_DE_KAPILARDAN_GECTI"


def main():
    print("PERSONAL AI - GERCEK MODEL + DORT KAPI")
    print("=" * 60)
    print("Model:", base.MODEL)
    print("Kaynak: 11 numarali calismadan bilinen cumle")
    print("Veritabani yazma: YOK")
    print("Strateji degisikligi ve alim-satim: KAPALI")

    print("\n" + "=" * 60)
    print("KAYNAK CUMLESI")
    print(SOURCE_TEXT)

    source = extract_real_model(SOURCE_TEXT)

    print("Kaynak kapi sonucu:", source["status"])
    print("Kaynak gerekceleri:", show(source["reasons"]))

    # Kaynagin onceki deneylerde elle kontrol edilmis
    # iliskisini de ayri bir sabit kontrolle dogrula.
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
            "KAYNAK_ONCEDEN_BELIRLENEN_CEVAPLA_UYUSMUYOR"
        ]
        print(
            "Kaynak ek kontrolu:",
            show(source["reasons"]),
        )

    passed = 0

    for index, case in enumerate(CASES, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {index}: {case['name']}")
        print("Iddia:", case["text"])

        claim = extract_real_model(case["text"])

        print("Iddia kapi sonucu:", claim["status"])
        print("Iddia gerekceleri:", show(claim["reasons"]))

        verdict, reason = compare(source, claim)

        print("Python karari:", verdict)
        print("Karar gerekcesi:", reason)
        print("Onceden belirlenen beklenen:", case["expected"])

        ok = verdict == case["expected"]
        print("Test:", "PASS" if ok else "FAIL")

        if ok:
            passed += 1

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")
    print(
        "Bu sonuc yalnizca bu kaynak ve bu iddialar "
        "icin gecerli bir deney sonucudur."
    )
    print(
        "READY bilimsel dogruluk veya nedensellik "
        "kaniti degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()