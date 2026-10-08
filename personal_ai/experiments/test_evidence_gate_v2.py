
from evidence_gate_v2 import check_claim

source = {
    "id": "TEST-002",
    "text": (
        "Makale 2024 yılında yayımlandı. "
        "Çalışmada 85 katılımcı vardı. "
        "LSTM yöntemi kullanılmadı."
    ),
}

claims = [
    "Makalenin başarı oranı %85'tir.",
    "Makale LSTM yöntemini kullandı.",
    "Makale 2024 yılında yayımlandı.",
]

print("PERSONAL AI - V2 YANILTMA TESTI")
print("-------------------------------")

for claim in claims:
    result = check_claim(claim, source)
    print("\nIddia:", claim)
    print("Durum:", result["status"])
    print("Gerekce:", result["reason"])

print("\nNOT: Bu testte kaynak metni de kurgusaldir.")