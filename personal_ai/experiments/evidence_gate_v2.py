
import re


# Bu deneydeki kaynak, gerçek bir makale değil:
# kaynak kontrolünü sınamak için hazırlanmış örnek metin.
SOURCE = {
    "id": "TEST-001",
    "text": (
        "Bu çalışma, kripto para fiyatlarını tahmin etmek "
        "için makine öğrenmesi yöntemlerini inceler."
    ),
}


def check_claim(claim, source):
    source_text = source["text"].casefold()
    claim_text = claim.casefold()

    # İlk kontrol: iddia kaynakta aynen bulunuyor mu?
    if claim_text in source_text:
        return {
            "status": "SOURCE_TEXT_MATCH",
            "reason": "İddia kaynak metninde aynen bulunuyor.",
            "source_id": source["id"],
        }

    # Sayısal iddia için kaynakta aynı sayı var mı?
    numbers = re.findall(
        r"\d+(?:[.,]\d+)?",
        claim_text
    )

    if numbers:
        missing = [
            number
            for number in numbers
            if number not in source_text
        ]

        if missing:
            return {
                "status": "REVIEW_REQUIRED",
                "reason": (
                    "İddiadaki sayısal değer kaynakta "
                    "bulunamadı: " + ", ".join(missing)
                ),
                "source_id": source["id"],
            }

    return {
        "status": "REVIEW_REQUIRED",
        "reason": (
            "İddia kaynakta aynen bulunamadı. "
            "Anlamsal doğrulama henüz yapılmadı."
        ),
        "source_id": source["id"],
    }


def main():
    claims = [
        "Bu çalışma, kripto para fiyatlarını tahmin etmek için makine öğrenmesi yöntemlerini inceler.",
        "Makalenin başarı oranı %85'tir.",
        "Makale LSTM algoritmasını kullanmıştır.",
        "Makale 2024 yılında yayımlanmıştır.",
    ]

    print("PERSONAL AI - KANIT KAPISI V2")
    print("-----------------------------")
    print("Kaynak:", SOURCE["id"])

    for claim in claims:
        result = check_claim(claim, SOURCE)

        print("\nİddia:", claim)
        print("Durum:", result["status"])
        print("Gerekçe:", result["reason"])

    print("\nNOT: SOURCE_TEXT_MATCH, doğrulanmış bilimsel")
    print("sonuç anlamına gelmez; yalnızca metin eşleşmesidir.")


if __name__ == "__main__":
    main()