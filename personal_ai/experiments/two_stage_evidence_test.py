import json
import re
import urllib.request

MODEL = "qwen2.5:7b"
URL = "http://127.0.0.1:11434/api/generate"

FIELDS = ("participant_count", "uses_lstm", "success_rate")

TESTS = [
    {
        "name": "Olumsuz LSTM, başarı oranı yok",
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
        "name": "Olumlu LSTM, başarı oranı var",
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


def ask_model(prompt):
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


def sentences_of(source):
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", source.strip())
        if part.strip()
    ]


def field_is_relevant(field, sentence):
    """Yalnızca bu deneyin dar kapsamlı cümlelerini tanır."""
    text = sentence.lower()

    if field == "participant_count":
        return bool(re.search(r"\bkatılımcı\b", text))

    if field == "uses_lstm":
        return bool(re.search(r"\blstm\b", text))

    if field == "success_rate":
        return "başarı oranı" in text

    return False


def select_quotes(source):
    prompt = f"""
Aşağıdaki KURGUSAL kaynak metinden üç alan için kanıt cümlesi seç.

Kurallar:
- Yalnızca kaynakta BİREBİR geçen TAM cümleleri kopyala.
- Katılımcı sayısına ilişkin cümleyi participant_count alanına yaz.
- LSTM kullanımına ilişkin cümleyi uses_lstm alanına yaz.
- Başarı oranına ilişkin cümleyi success_rate alanına yaz.
- İlgili konu hiç geçmiyorsa JSON null yaz.
- "Kullanılmadı" ve "raporlanmadı" cümleleri de ilgili konuya ait kanıttır.
- Bu aşamada sayı, boolean veya sonuç çıkarma.
- Yalnızca geçerli JSON döndür.

Şema:
{{
  "participant_count": null,
  "uses_lstm": null,
  "success_rate": null
}}

Kaynak:
{source}
""".strip()

    return ask_model(prompt)


def extract_value(field, quote):
    prompt = f"""
Yalnızca aşağıdaki TEK cümleden istenen değeri çıkar.

Alan: {field}
Cümle: {quote}

Kurallar:
- participant_count: Katılımcı sayısını JSON sayısı olarak yaz.
- uses_lstm: LSTM kullanıldıysa true, kullanılmadıysa false yaz.
- success_rate: Sayısal başarı oranı varsa yüzde işareti olmadan sayı yaz.
- Başarı oranı raporlanmadıysa veya değer yoksa null yaz.
- Bilgi uydurma; yalnızca geçerli JSON döndür.

Şema:
{{"value": null}}
""".strip()

    answer = ask_model(prompt)
    return answer.get("value")


def expected_from_quote(field, quote):
    """
    Modelin çıkardığı değeri kontrol eden dar kapsamlı kurallar.
    Genel amaçlı bilimsel metin çözücüsü değildir.
    """
    text = quote.lower()

    if field == "participant_count":
        match = re.search(r"\b(\d+)\s+katılımcı\b", text)
        return int(match.group(1)) if match else None

    if field == "uses_lstm":
        if re.search(r"\blstm\b.*\bkullanılmadı\b", text):
            return False
        if re.search(r"\blstm\b.*\bkullanıldı\b", text):
            return True
        return None

    if field == "success_rate":
        match = re.search(r"başarı oranı\s*%?\s*(\d+)", text)
        if not match:
            match = re.search(r"başarı oranı\s+%(\d+)", text)
        return int(match.group(1)) if match else None

    return None


def same_value(actual, expected):
    return type(actual) is type(expected) and actual == expected


def main():
    passed = 0
    total = len(TESTS) * len(FIELDS)

    print("PERSONAL AI - IKI ASAMALI KANIT TESTI")
    print("=" * 45)

    for test in TESTS:
        source = test["source"]
        sentences = sentences_of(source)

        print(f"\nTEST: {test['name']}")

        try:
            quotes = select_quotes(source)
            if not isinstance(quotes, dict):
                raise ValueError("Kanıt yanıtı JSON nesnesi değil.")
        except Exception as exc:
            print(f"KANIT SECIM HATASI: {exc}")
            continue

        for field in FIELDS:
            quote = quotes.get(field)
            expected = test["expected"][field]

            print(f"\nAlan: {field}")
            print(f"Secilen kanit: {quote!r}")

            relevant_sentences = [
                sentence
                for sentence in sentences
                if field_is_relevant(field, sentence)
            ]

            if quote is None:
                if relevant_sentences:
                    print("KALDI | Kaynakta ilgili cumle var ama secilmedi.")
                elif expected is None:
                    passed += 1
                    print("GECTI | Kaynakta ilgili konu yok; null dogru.")
                else:
                    print("KALDI | Beklenen bilgi icin kanit bulunamadi.")
                continue

            if not isinstance(quote, str) or quote not in sentences:
                print("KALDI | Kanit kaynakta birebir gecen tam cumle degil.")
                continue

            if not field_is_relevant(field, quote):
                print("KALDI | Kanit bu alanla ilgili degil.")
                continue

            try:
                value = extract_value(field, quote)
            except Exception as exc:
                print(f"KALDI | DEGER CIKARMA HATASI: {exc}")
                continue

            check_value = expected_from_quote(field, quote)

            print(f"Modelin degeri: {value!r}")
            print(f"Kural kontrolu: {check_value!r}")
            print(f"Test beklentisi: {expected!r}")

            if (
                same_value(value, check_value)
                and same_value(value, expected)
            ):
                passed += 1
                print("GECTI | Kanit ve deger eslesti.")
            else:
                print("KALDI | Kanit, deger veya beklenti uyusmuyor.")

    print("\n" + "=" * 45)
    print(f"SONUC: {passed}/{total} kontrol gecti.")
    print("NOT: Yalnizca kurgusal ve dar kapsamli bir testtir.")
    print("Veritabanina yazilmadi. Islem tetiklenmedi.")


if __name__ == "__main__":
    main()