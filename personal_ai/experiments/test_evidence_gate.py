
from evidence_gate import evidence_gate


tests = [
    ("Model %70-90 dogruluk elde eder.", "REVIEW_REQUIRED"),
    ("Modelin basari orani %85.", "REVIEW_REQUIRED"),
    ("Modelin basari orani 85%.", "REVIEW_REQUIRED"),
    ("Modelin basari orani yuzde 85.", "REVIEW_REQUIRED"),
    ("Modelin basari orani 0,85.", "REVIEW_REQUIRED"),
    ("Makale 2024 yilinda yayimlandi.", "REVIEW_REQUIRED"),
    ("Bu makalenin basari orani bilinmiyor.", "DRAFT"),
]

print("PERSONAL AI - KANIT KAPISI SINAVI")
print("--------------------------------")

passed = 0

for number, (text, expected) in enumerate(tests, start=1):
    result = evidence_gate(text)
    actual = result["status"]
    ok = actual == expected

    if ok:
        passed += 1

    print(
        f"{number}. {'GECTI' if ok else 'KACIRDI'} "
        f"| Beklenen: {expected} "
        f"| Gercek: {actual}"
    )
    print("   Metin:", text)

print("--------------------------------")
print(f"SONUC: {passed}/{len(tests)} test gecti.")
print("NOT: Bu testler kaynak dogrulamasi yapmaz.")