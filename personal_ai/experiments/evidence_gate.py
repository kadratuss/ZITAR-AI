
import re

# İlk deney: yalnızca metni inceler.
# Veritabanına yazmaz, internete bağlanmaz.

def evidence_gate(text, source=None):
    percentage = re.search(
        r"%\s*\d+(?:[.,]\d+)?"
        r"(?:\s*[-–]\s*%?\s*\d+(?:[.,]\d+)?)?"
        r"|"
        r"\d+(?:[.,]\d+)?"
        r"\s*[-–]\s*"
        r"\d+(?:[.,]\d+)?\s*%",
        text
    )

    if percentage:
        return {
            "status": "REVIEW_REQUIRED",
            "claim": percentage.group(),
            "reason": (
                "Sayisal iddia tespit edildi. "
                "Kaynak ve deney sonucu dogrulanmadan "
                "onaylanamaz."
            )
        }

    return {
        "status": "DRAFT",
        "claim": None,
        "reason": (
            "Bu basit kontrolde yuzde ifadesi bulunamadi. "
            "Metin yine de dogrulanmis sayilmaz."
        )
    }


def main():
    samples = [
        "Model genellikle %70-90 dogruluk elde eder.",
        "Bu makalenin basari orani bilinmiyor."
    ]

    print("PERSONAL AI - KANIT KAPISI DENEYI")
    print("---------------------------------")

    for text in samples:
        result = evidence_gate(text)
        print("\nMetin:", text)
        print("Durum:", result["status"])
        print("Tespit:", result["claim"])
        print("Gerekce:", result["reason"])


if __name__ == "__main__":
    main()