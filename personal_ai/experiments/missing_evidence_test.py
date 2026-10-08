import json
import re
import urllib.request

MODEL = "qwen2.5:7b"
URL = "http://127.0.0.1:11434/api/generate"

TESTS = [
    {
        "name": "Olumsuz ifade ve eksik başarı oranı",
        "source": (
            "Çalışmada 85 katılımcı vardı. "
            "LSTM yöntemi kullanılmadı. "
            "Başarı oranı raporlanmadı."
        ),
        "expected": {
            "participant_count": 85,
            "uses_lstm": False,
            "success_rate": None,
        },
    },
    {
        "name": "Olumlu ifade ve belirtilen başarı oranı",
        "source": (
            "Çalışmada 120 katılımcı vardı. "
            "LSTM yöntemi kullanıldı. "
            "Test verisinde başarı oranı %72 olarak raporlandı."
        ),
        "expected": {
            "participant_count": 120,
            "uses_lstm": True,
            "success_rate": 72,
        },
    },
    {
        "name": "Üç alan da belirtilmemiş",
        "source": (
            "Araştırma, kripto para piyasalarındaki fiyat hareketlerini "
            "incelemektedir. Bulguların farklı piyasalarda sınanması önerildi."
        ),
        "expected": {
            "participant_count": None,
            "uses_lstm": None,
            "success_rate": None,
        },
    },
]

FIELDS = ("participant_count", "uses_lstm", "success_rate")


def ask_model(source):
    prompt = f"""
Aşağıdaki KURGUSAL kaynak metinden yalnızca belirtilen alanları çıkar.

Kurallar:
- Sadece kaynak metni kullan. Tahmin etme.
- Katılımcı sayısı belirtilmişse participant_count.value alanına sayıyı JSON sayısı olarak yaz; kanıt cümlesini bulduysan değeri null bırakma.
- Bilgi belirtilmemişse value ve quote alanlarına JSON null yaz.
- Bilgi belirtilmişse quote, kaynak metindeki ilgili TAM cümle olsun.
- LSTM kullanılmadıysa uses_lstm false; kullanıldıysa true.
- Başarı oranını yüzde işareti olmadan sayı olarak yaz.
- Yalnızca geçerli JSON döndür; açıklama veya Markdown ekleme.

Şema:
{{
  "participant_count": {{"value": null, "quote": null}},
  "uses_lstm": {{"value": null, "quote": null}},
  "success_rate": {{"value": null, "quote": null}}
}}

Kaynak:
{source}
""".strip()

    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode("utf-8")

    request = urllib.request.Request(
        URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)

    return json.loads(result["response"])


def check_field(source, answer, expected):
    if not isinstance(answer, dict):
        return False, "Alan JSON nesnesi değil."

    value = answer.get("value")
    quote = answer.get("quote")

    if type(value) is not type(expected) or value != expected:
        return False, f"Değer hatalı: beklenen={expected!r}, gelen={value!r}"

    if expected is None:
        if quote is not None:
            return False, "Eksik bilgi için kanıt da null olmalı."
        return True, "Eksik bilgi doğru işaretlendi."

    if not isinstance(quote, str) or not quote.strip():
        return False, "Mevcut bilgi için kanıt cümlesi eksik."

    # Tam cümle şartı: yalnızca kaynaktaki cümlelerden biri kabul edilir.
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", source.strip())
        if part.strip()
    ]
    if quote not in sentences:
        return False, "Kanıt, kaynakta birebir geçen tam cümle değil."

    return True, "Değer ve birebir kanıt cümlesi eşleşti."


def main():
    passed = 0
    total = len(TESTS) * len(FIELDS)

    print("PERSONAL AI - EKSIK KANIT TESTI")
    print("=" * 40)

    for test in TESTS:
        print(f"\nTEST: {test['name']}")

        try:
            result = ask_model(test["source"])
        except Exception as exc:
            print(f"MODEL HATASI: {exc}")
            continue

        for field in FIELDS:
            ok, reason = check_field(
                test["source"],
                result.get(field),
                test["expected"][field],
            )
            passed += int(ok)
            print(f"{field}: {'GECTI' if ok else 'KALDI'} | {reason}")
            print(f"  Gelen: {result.get(field)!r}")

    print("\n" + "=" * 40)
    print(f"SONUC: {passed}/{total} kontrol gecti.")
    print("NOT: Kurgusal testtir; bilimsel dogrulama degildir.")
    print("Veritabanina yazilmadi. Islem tetiklenmedi.")


if __name__ == "__main__":
    main()