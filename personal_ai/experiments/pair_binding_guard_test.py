import re

import multi_relation_guard_test as old_guard
import text_evidence_gate_test as evidence


RAW = old_guard.raw_answers(
    target="LONG_TERM_BTC_VOL",
    variable="SP500_REALIZED_VOL",
    relation_type="EFFECT",
    direction="NEGATIVE",
)


def normalize(text):
    return evidence.normalize(text)


def explicit_pair_binding(text):
    """
    Yalnizca dar, acik etki kaliplarini kabul eder.
    Genel bir dil anlama veya nedensellik testi degildir.
    """
    t = normalize(text)

    variable = r"s&p\s*500\s+realized\s+volatility"
    target = r"long-term\s+bitcoin\s+volatility"

    english = (
        variable
        + r"\s+has\s+a\s+negative\s+effect\s+on\s+"
        + target
    )

    # Turkce karakterler normalize() ile sadeleşir.
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


def guarded_check(text, raw):
    # Mevcut koruma once calisir.
    previous = old_guard.guarded_check(text, raw)

    if previous["status"] != "READY":
        return previous

    # Bu ilk surum yalnizca sabitlenen negatif etki
    # iliskisi icin tasarlandi. Diger etiketlere READY yok.
    expected = {
        "target": "LONG_TERM_BTC_VOL",
        "variable": "SP500_REALIZED_VOL",
        "relation": "EFFECT",
        "direction": "NEGATIVE",
    }

    actual = {
        "target": raw[0].get("target"),
        "variable": raw[1].get("variable"),
        "relation": raw[2].get("relation"),
        "direction": raw[2].get("direction"),
    }

    if actual != expected:
        return {
            "status": "REVIEW",
            "reasons": ["BU_SURUMDE_DESTEKLENMEYEN_ETIKETLER"],
        }

    bound, reason = explicit_pair_binding(text)

    if not bound:
        return {
            "status": "REVIEW",
            "reasons": [reason],
        }

    return {
        "status": "READY",
        "reasons": [],
        "binding_evidence": reason,
    }


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
        "name": "Acik Turkce negatif etki",
        "text": (
            "S&P 500 gerceklesen oynakliginin uzun vadeli "
            "Bitcoin oynakligi uzerinde negatif etkisi var."
        ),
        "expected": "READY",
    },
    {
        "name": "Kaynak cumlesindeki araya giren vurgu",
        "text": (
            "We find that S&P 500 realized volatility "
            "has a negative and highly significant effect "
            "on long-term Bitcoin volatility."
        ),
        "expected": "REVIEW",
    },
]


def main():
    print("PERSONAL AI - DEGISKEN CIFTI BAGLAMA TESTI")
    print("=" * 60)
    print("Model cagrisi: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0

    for i, case in enumerate(CASES, 1):
        result = guarded_check(case["text"], RAW)
        ok = result["status"] == case["expected"]

        print("\n" + "-" * 60)
        print(f"TEST {i}: {case['name']}")
        print("Metin:", case["text"])
        print("Sonuc:", result["status"])
        print("Gerekceler:", result["reasons"])
        print("Beklenen:", case["expected"])
        print("Test:", "PASS" if ok else "FAIL")

        if ok:
            passed += 1

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(CASES)}")
    print(
        "UYARI: READY yalnizca taninan acik kaliba "
        "uyumu gosterir; bilimsel dogruluk kaniti degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()