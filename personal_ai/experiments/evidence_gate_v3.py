
# PERSONAL AI - KANIT KAPISI V3
# Yalnizca bellek ici deney. Veritabanina yazmaz.

SOURCE = {
    "id": "TEST-002",
    "facts": [
        {
            "subject": "makale",
            "property": "publication_year",
            "value": 2024,
            "evidence": "Makale 2024 yilinda yayimlandi.",
        },
        {
            "subject": "calisma",
            "property": "participant_count",
            "value": 85,
            "evidence": "Calismada 85 katilimci vardi.",
        },
        {
            "subject": "calisma",
            "property": "uses_lstm",
            "value": False,
            "evidence": "LSTM yontemi kullanilmadi.",
        },
    ],
}


def check_claim(claim, source):
    for fact in source["facts"]:
        same_subject = claim["subject"] == fact["subject"]
        same_property = claim["property"] == fact["property"]

        if same_subject and same_property:
            if claim["value"] == fact["value"]:
                return {
                    "status": "SOURCE_SUPPORT",
                    "reason": "Yapilandirilmis kaynak bilgisi iddiayi destekliyor.",
                    "evidence": fact["evidence"],
                }

            return {
                "status": "CONTRADICTION",
                "reason": "Kaynak ayni konu hakkinda farkli bilgi veriyor.",
                "evidence": fact["evidence"],
            }

    return {
        "status": "INSUFFICIENT_EVIDENCE",
        "reason": "Kaynakta bu iddiaya ait bilgi bulunamadi.",
        "evidence": None,
    }


def main():
    tests = [
        (
            "Basari orani %85",
            {"subject": "calisma", "property": "success_rate", "value": 85},
            "INSUFFICIENT_EVIDENCE",
        ),
        (
            "LSTM kullanildi",
            {"subject": "calisma", "property": "uses_lstm", "value": True},
            "CONTRADICTION",
        ),
        (
            "Makale 2024 yilinda yayimlandi",
            {"subject": "makale", "property": "publication_year", "value": 2024},
            "SOURCE_SUPPORT",
        ),
        (
            "Calismada 85 katilimci vardi",
            {"subject": "calisma", "property": "participant_count", "value": 85},
            "SOURCE_SUPPORT",
        ),
    ]

    print("PERSONAL AI - KANIT KAPISI V3")
    print("-----------------------------")

    passed = 0

    for title, claim, expected in tests:
        result = check_claim(claim, SOURCE)
        actual = result["status"]
        ok = actual == expected
        passed += int(ok)

        print("\nIddia:", title)
        print("Sonuc:", actual)
        print("Test:", "GECTI" if ok else "KACIRDI")
        print("Gerekce:", result["reason"])
        print("Kaynak cumlesi:", result["evidence"])

    print("\n-----------------------------")
    print(f"SONUC: {passed}/{len(tests)} test gecti.")
    print("NOT: Kaynak kurgusaldir; SOURCE_SUPPORT bilimsel dogrulama degildir.")


if __name__ == "__main__":
    main()