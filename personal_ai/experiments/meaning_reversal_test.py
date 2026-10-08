import re
import unicodedata


# Daha önce veritabanından okuduğumuz yazar özetindeki cümle.
# Bu testte kaynak metin olarak yalnızca bu cümleyi kullanıyoruz.
SOURCE_SENTENCE = (
    "The simulation shows that among the three methods, "
    "SVM outperforms the BP neural network in financial forecasting, "
    "and there are comparable generalization performance between "
    "SVM and the regularized RBF neural network."
)


def normalize(text):
    """Karşılaştırma için küçük harf ve sade boşluk düzeni."""
    text = unicodedata.normalize("NFKC", text)
    return " ".join(text.casefold().split())


def source_supports_svm_over_bp(source):
    """
    Yalnızca bu deneydeki dar İngilizce ifadeyi tanır.
    Genel amaçlı bilimsel doğrulama değildir.
    """
    text = normalize(source)

    pattern = (
        r"\bsvm\s+outperforms\s+"
        r"(?:the\s+)?bp\s+neural\s+network\b"
    )

    return re.search(pattern, text) is not None


def find_claim_direction(explanation):
    """
    Açıklamadaki açık SVM/BP karşılaştırmasını sınıflandırır.

    SVM_OVER_BP: Kaynakla aynı yön
    BP_OVER_SVM: Kaynağın tersi
    UNKNOWN: Bu dar kuralların anlayamadığı ifade
    """
    text = normalize(explanation)

    svm_over_bp_patterns = [
        r"\bsvm\b.{0,45}\b(?:outperforms|beats)\b.{0,45}\bbp\b",
        r"\bsvm\b.{0,45}\b(?:better|superior)\b.{0,45}\bbp\b",
        r"\bsvm\b.{0,45}\bbp\b.{0,45}\b(?:daha iyi|üstün)\b",
    ]

    bp_over_svm_patterns = [
        r"\bbp\b.{0,45}\b(?:outperforms|beats)\b.{0,45}\bsvm\b",
        r"\bbp\b.{0,45}\b(?:better|superior)\b.{0,45}\bsvm\b",
        r"\bbp\b.{0,45}\bsvm\b.{0,45}\b(?:daha iyi|üstün)\b",
    ]

    positive = any(re.search(p, text) for p in svm_over_bp_patterns)
    negative = any(re.search(p, text) for p in bp_over_svm_patterns)

    if positive and negative:
        return "CONFLICTING_CLAIMS"
    if negative:
        return "BP_OVER_SVM"
    if positive:
        return "SVM_OVER_BP"

    return "UNKNOWN"


def check_explanation(source, quote, explanation):
    """
    İki ayrı kontrol:
    1. Alıntı kaynakta birebir var mı?
    2. Açıklamanın açık karşılaştırma yönü kaynakla çelişiyor mu?

    Bilinmeyen ifadeyi onaylamaz; incelemeye gönderir.
    """
    if not isinstance(quote, str) or not quote.strip():
        return "REJECTED", "Alıntı boş."

    if not isinstance(explanation, str) or not explanation.strip():
        return "REJECTED", "Açıklama boş."

    if quote not in source:
        return "REJECTED", "Alıntı kaynakta birebir bulunamadı."

    if not source_supports_svm_over_bp(source):
        return "REVIEW_REQUIRED", "Kaynağın karşılaştırma yönü belirlenemedi."

    direction = find_claim_direction(explanation)

    if direction == "BP_OVER_SVM":
        return "REJECTED", "Açıklama, kaynaktaki karşılaştırmayı tersine çevirdi."

    if direction == "CONFLICTING_CLAIMS":
        return "REJECTED", "Açıklama kendi içinde çelişen karşılaştırmalar içeriyor."

    if direction == "UNKNOWN":
        return "REVIEW_REQUIRED", "Açıklamanın anlamı bu dar kurallarla doğrulanamadı."

    return (
        "LIMITED_MATCH",
        "Alıntı eşleşti ve açık karşılaştırma yönü bu dar kuralla uyumlu."
    )


def main():
    tests = [
        {
            "name": "Kaynakla aynı yön",
            "quote": SOURCE_SENTENCE,
            "explanation": "SVM outperforms BP in financial forecasting.",
            "expected": "LIMITED_MATCH",
        },
        {
            "name": "İngilizce tersine çevirme",
            "quote": SOURCE_SENTENCE,
            "explanation": "BP outperforms SVM in financial forecasting.",
            "expected": "REJECTED",
        },
        {
            "name": "Türkçe tersine çevirme",
            "quote": SOURCE_SENTENCE,
            "explanation": "BP, SVM'den daha iyi sonuç verdi.",
            "expected": "REJECTED",
        },
        {
            "name": "Kaynakta bulunmayan alıntı",
            "quote": "Bitcoin trading guarantees a 90% profit.",
            "explanation": "SVM outperforms BP.",
            "expected": "REJECTED",
        },
        {
            "name": "Yorumdan işlem sinyali çıkarma",
            "quote": SOURCE_SENTENCE,
            "explanation": "Bu nedenle bugün Bitcoin satın almalıyız.",
            "expected": "REVIEW_REQUIRED",
        },
        {
            "name": "Aynı açıklamada iki zıt iddia",
            "quote": SOURCE_SENTENCE,
            "explanation": "SVM outperforms BP. However, BP outperforms SVM.",
            "expected": "REJECTED",
        },
    ]

    print("PERSONAL AI - ANLAM TERSINE CEVIRME TESTI")
    print("=" * 48)

    passed = 0

    for index, test in enumerate(tests, start=1):
        status, reason = check_explanation(
            SOURCE_SENTENCE,
            test["quote"],
            test["explanation"],
        )

        ok = status == test["expected"]
        if ok:
            passed += 1

        print(f"\n{index}. {test['name']}")
        print(f"Beklenen : {test['expected']}")
        print(f"Gercek   : {status}")
        print(f"Test     : {'GECTI' if ok else 'KALDI'}")
        print(f"Gerekce  : {reason}")

    print("\n" + "=" * 48)
    print(f"SONUC: {passed}/{len(tests)} test gecti.")
    print("NOT: Bu yalnizca dar kapsamli, kurgusal bir kural testidir.")
    print("Bilimsel dogrulama yapilmaz.")
    print("Veritabanina yazilmaz. Alim-satim tetiklenmez.")


if __name__ == "__main__":
    main()