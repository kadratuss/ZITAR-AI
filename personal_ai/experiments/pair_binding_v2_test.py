import re
import unicodedata

import holdout_pair_guard_test as holdout
import pair_binding_refinement_test as previous
import multi_relation_guard_test as multi


RAW = holdout.RAW

# Bu kaliplar yalnizca sabit SP500 -> uzun vadeli BTC,
# NEGATIVE EFFECT semasi icindir.
EN_PASSIVE = re.compile(
    r"\blong-term bitcoin volatility"
    r"\s+is\s+negatively\s+affected\s+by\s+"
    r"s&p 500 realized volatility\b",
    re.IGNORECASE,
)

TR_ACTIVE = re.compile(
    r"\bs&p 500 gerceklesen oynakligi"
    r"\s*,?\s*uzun vadeli bitcoin oynakligini"
    r"\s+negatif etkiliyor\b",
    re.IGNORECASE,
)


def ascii_lower(text):
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(
        char for char in decomposed
        if not unicodedata.combining(char)
    ).lower()


def expected_raw(raw):
    return raw == [
        {"target": "LONG_TERM_BTC_VOL"},
        {"variable": "SP500_REALIZED_VOL"},
        {"relation": "EFFECT", "direction": "NEGATIVE"},
    ]


def new_pair_pattern(text):
    normalized = ascii_lower(text)
    return bool(
        EN_PASSIVE.search(normalized)
        or TR_ACTIVE.search(normalized)
    )


def check_v2(text, raw):
    old = previous.refined_check(text, raw)

    # Eski READY kararlarini degistirmiyoruz.
    if old["status"] == "READY":
        return old

    # Baska bir semaya genislemiyoruz.
    if not expected_raw(raw):
        return old

    # Yeni acik cift baglama kalibi yoksa eski REVIEW korunur.
    if not new_pair_pattern(text):
        return old

    # Birden fazla etki ifadesi veya birden fazla cumle icin
    # yeni kalipla READY acmiyoruz.
    normalized = ascii_lower(text)
    effect_markers = re.findall(
        r"\beffect on\b|\baffected by\b|\betkiliyor\b",
        normalized,
    )
    if len(effect_markers) != 1:
        return {
            "status": "REVIEW",
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
            "reasons": ["V2_TEK_CUMLE_DOGRULANAMADI"],
        }

    # Acik kalibin disinda baska bir yon/olumsuzlama
    # varsa bu dar genisletmeyle karar vermiyoruz.
    if re.search(
        r"\bnot\b|\bno\b|\bnever\b|\bpositive\b"
        r"|\bwithout\b|\bdegil\b|\bpozitif\b",
        normalized,
    ):
        return {
            "status": "REVIEW",
            "reasons": ["V2_EK_YON_VEYA_OLUMSUZLUK"],
        }

    return {
        "status": "READY",
        "reasons": [],
    }


def main():
    print("PERSONAL AI - CIFT BAGLAMA V2")
    print("=" * 60)
    print("Model cagrisi: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    passed = 0
    false_ready = 0
    false_review = 0

    for number, case in enumerate(holdout.CASES, start=1):
        result = check_v2(case["text"], RAW)
        actual = result["status"]
        expected = case["expected"]
        ok = actual == expected

        passed += int(ok)
        false_ready += int(
            actual == "READY" and expected == "REVIEW"
        )
        false_review += int(
            actual == "REVIEW" and expected == "READY"
        )

        print("\n" + "-" * 60)
        print(f"TEST {number}: {case['name']}")
        print("Beklenen:", expected)
        print("Gerceklesen:", actual)
        print("Gerekceler:", result["reasons"])
        print("Test:", "PASS" if ok else "FAIL")

    print("\n" + "=" * 60)
    print(f"SONUC: {passed}/{len(holdout.CASES)}")
    print("Yanlis READY:", false_ready)
    print("Gecerli metne REVIEW:", false_review)
    print(
        "NOT: Bu, artik gelistirme icin kullanilan eski "
        "10 ornegin tekrar testidir; bagimsiz dogrulama degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()