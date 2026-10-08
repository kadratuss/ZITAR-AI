import re

import pair_binding_guard_test as old
import text_evidence_gate_test as evidence


def refined_pair_binding(text):
    """
    Yalnizca iki acik Ingilizce etki kalibini ve
    onceki Turkce kalibi kabul eder.
    Genel bir dil anlama sistemi degildir.
    """
    t = evidence.normalize(text)

    variable = r"s&p\s*500\s+realized\s+volatility"
    target = r"long-term\s+bitcoin\s+volatility"

    english = (
        variable
        + r"\s+has\s+a\s+negative"
        + r"(?:\s+and\s+highly\s+significant)?"
        + r"\s+effect\s+on\s+"
        + target
    )

    turkish = (
        r"s&p\s*500\s+gerceklesen\s+oynakliginin"
        + r"\s+uzun\s+vadeli\s+bitcoin\s+oynakligi"
        + r"\s+uzerinde\s+negatif\s+etkisi\s+var"
    )

    if re.search(english, t):
        return True, "ACIK_INGILIZCE_ETKI_KALIBI"

    if re.search(turkish, t):
        return True, "ACIK_TURKCE_ETKI_KALIBI"

    return False, "DEGISKEN_CIFTI_ILISKIYE_BAGLANAMADI"


def refined_check(text, raw):
    """
    Eski dort kapi ve coklu iliski korumasi
    old.guarded_check icinde calisir.

    Eski dar kalip REVIEW verdiginde, yalnizca
    bu yeni acik kalip icin yeniden degerlendiririz.
    """
    previous = old.guarded_check(text, raw)

    if previous["status"] == "READY":
        return previous

    # Baska bir kapinin reddini asla gecersiz kilma.
    if previous["reasons"] != [
        "DEGISKEN_CIFTI_ILISKIYE_BAGLANAMADI"
    ]:
        return previous

    bound, reason = refined_pair_binding(text)

    if not bound:
        return previous

    return {
        "status": "READY",
        "reasons": [],
        "binding_evidence": reason,
    }


RAW = old.RAW

CASES = [
    {
        "name": "Acik Ingilizce negatif etki",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Gercek kaynak cumlesindeki vurgu",
        "text": (
            "We find that S&P 500 realized volatility "
            "has a negative and highly significant effect "
            "on long-term Bitcoin volatility."
        ),
        "expected": "READY",
    },
    {
        "name": "Acik Turkce negatif etki",
        "text": (
            "S&P 500 gerceklesen oynakliginin uzun vadeli "
            "Bitcoin oynakligi uzerinde negatif etkisi var."
        ),
        "expected": "READY",
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
        "name": "Iki ayri etki",
        "text": (
            "S&P 500 realized volatility has a negative "
            "effect on long-term Bitcoin volatility. "
            "Gold has a negative effect on bond prices."
        ),
        "expected": "REVIEW",
    },
    {
        "name": "Kaynakta yon belirtilmiyor",
        "text": (
            "S&P 500 realized volatility has an effect "
            "on long-term Bitcoin volatility."
        ),
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - KALIP IYILESTIRME TESTI")
    print("=" * 60)
    print("Model cagrisi: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0

    for number, case in enumerate(CASES, start=1):
        before = old.guarded_check(case["text"], RAW)
        after = refined_check(case["text"], RAW)

        ok = after["status"] == case["expected"]
        passed += int(ok)

        print("\n" + "-" * 60)
        print(f"TEST {number}: {case['name']}")
        print("Eski sonuc:", before["status"])
        print("Yeni sonuc:", after["status"])
        print("Gerekceler:", after["reasons"])
        print("Beklenen:", case["expected"])
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")
    print(
        "READY yalnizca taninan metin kalibina uyumdur; "
        "bilimsel dogruluk kaniti degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()