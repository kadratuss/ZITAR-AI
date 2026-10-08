
# PERSONAL AI - CIKARIM KURALLARI DENEYI
# Kurgusal metin; veritabanina yazmaz.

def check_fact(fact):
    prop = fact["property"]
    value = fact["value"]
    evidence = fact["evidence"].casefold()

    if prop == "uses_lstm":
        if "lstm" not in evidence:
            return "REVIEW_REQUIRED"

        if "kullanilmadi" in evidence:
            return "PASS" if value is False else "CONTRADICTION"

        if "kullanildi" in evidence:
            return "PASS" if value is True else "CONTRADICTION"

        return "REVIEW_REQUIRED"

    return "REVIEW_REQUIRED"


tests = [
    {
        "property": "uses_lstm",
        "value": None,
        "evidence": "LSTM yontemi kullanilmadi.",
        "expected": "CONTRADICTION",
    },
    {
        "property": "uses_lstm",
        "value": False,
        "evidence": "LSTM yontemi kullanilmadi.",
        "expected": "PASS",
    },
    {
        "property": "uses_lstm",
        "value": True,
        "evidence": "LSTM yontemi kullanilmadi.",
        "expected": "CONTRADICTION",
    },
    {
        "property": "uses_lstm",
        "value": None,
        "evidence": "LSTM hakkinda bilgi verilmedi.",
        "expected": "REVIEW_REQUIRED",
    },
]

passed = 0

print("PERSONAL AI - CIKARIM KURALLARI TESTI")
print("------------------------------------")

for index, fact in enumerate(tests, start=1):
    actual = check_fact(fact)
    expected = fact["expected"]
    ok = actual == expected
    passed += int(ok)

    print(
        f"{index}. {'GECTI' if ok else 'KACIRDI'} "
        f"| Beklenen: {expected} | Gercek: {actual}"
    )

print("------------------------------------")
print(f"SONUC: {passed}/{len(tests)} test gecti.")
print("NOT: PASS yalnizca bu dar kuralin test sonucudur.")
print("Kaynak veya bilimsel sonuc dogrulanmis sayilmaz.")