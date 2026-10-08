import json
import urllib.error
import urllib.request


MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

# Bu testte kullanılan kaynak cümlesi sabittir.
# Modelden kaynak cümlesini veya alıntıyı yeniden yazması istenmez.
SOURCE_SENTENCE = (
    "Adaptive parameters are then proposed by incorporating "
    "the nonstationarity of financial time series into SVM."
)

TESTS = [
    {
        "name": "Kaynakla uyumlu açıklama",
        "explanation": (
            "Çalışma, finansal zaman serilerinin durağan olmama "
            "özelliğini SVM'ye dahil ederek uyarlamalı parametreler öneriyor."
        ),
        "expected": "CONSISTENT",
    },
    {
        "name": "Kaynağın tersini söyleyen açıklama",
        "explanation": (
            "Çalışma, finansal zaman serilerinin durağan olmama "
            "özelliğini SVM'ye dahil etmeyi reddediyor."
        ),
        "expected": "CONTRADICTION",
    },
    {
        "name": "Kaynakta bulunmayan başarı yüzdesi",
        "explanation": (
            "Çalışma, uyarlamalı SVM'nin tahmin başarısını "
            "yüzde 95 olarak kanıtladı."
        ),
        "expected": "UNSUPPORTED",
    },
    {
        "name": "Kaynak dışı alım sinyali",
        "explanation": (
            "Bu bulgu, bugün Bitcoin almak gerektiğini gösteriyor."
        ),
        "expected": "UNSUPPORTED",
    },
]

ALLOWED_VERDICTS = {
    "CONSISTENT",
    "CONTRADICTION",
    "UNSUPPORTED",
}


def ask_ollama(source_sentence, explanation):
    system_prompt = """
Sen dar kapsamlı bir kaynak-anlam denetleyicisisin.

Yalnızca verilen tek kaynak cümlesi ile açıklamayı karşılaştır.

Karar seçenekleri:
- CONSISTENT: Açıklamanın iddiası kaynak cümlesiyle uyumlu.
- CONTRADICTION: Açıklama kaynak cümlesindeki ifadeyle açıkça çelişiyor.
- UNSUPPORTED: Açıklama kaynakta bulunmayan bir bilgi, sayı, sonuç,
  finansal varlık veya alım-satım önerisi ekliyor.

Kurallar:
- Kaynakta bulunmayan bilgileri tahmin etme.
- Kaynağın tamamını okuduğunu iddia etme.
- Bir yöntemin önerilmesini başarı kanıtı sayma.
- Kaynak cümlesini veya açıklamayı yeniden yazma.
- Alıntı üretme.
- Yalnızca JSON nesnesi döndür.
- JSON içinde sadece "verdict" ve "reason_tr" alanları olsun.
- reason_tr kısa ve Türkçe olsun.
""".strip()

    user_prompt = (
        "KAYNAK CÜMLESİ:\n"
        f"{source_sentence}\n\n"
        "DENETLENECEK AÇIKLAMA:\n"
        f"{explanation}"
    )

    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
        },
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        outer = json.loads(response.read().decode("utf-8"))

    content = outer["message"]["content"]
    result = json.loads(content)

    if not isinstance(result, dict):
        raise ValueError("Model JSON nesnesi döndürmedi.")

    if set(result.keys()) != {"verdict", "reason_tr"}:
        raise ValueError(
            "Beklenmeyen JSON alanları: "
            + ", ".join(sorted(result.keys()))
        )

    verdict = result["verdict"]
    reason = result["reason_tr"]

    if verdict not in ALLOWED_VERDICTS:
        raise ValueError(f"Geçersiz karar: {verdict!r}")

    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Türkçe gerekçe boş veya geçersiz.")

    return {
        "verdict": verdict,
        "reason_tr": reason.strip(),
    }


def main():
    print("PERSONAL AI - ALINTISIZ ANLAM DENETIMI V2")
    print("=" * 48)
    print("Kaynak cümlesi Python tarafından sabit tutuluyor.")
    print("Modelden alıntı istenmiyor.")
    print("Veritabanına yazılmayacak; işlem yapılmayacak.\n")

    passed = 0

    for index, test in enumerate(TESTS, start=1):
        print(f"TEST {index}: {test['name']}")
        print("-" * 48)
        print("Kaynak:", SOURCE_SENTENCE)
        print("Açıklama:", test["explanation"])
        print("Beklenen:", test["expected"])

        try:
            result = ask_ollama(
                SOURCE_SENTENCE,
                test["explanation"],
            )

            actual = result["verdict"]
            print("Model kararı:", actual)
            print("Model gerekçesi:", result["reason_tr"])

            if actual == test["expected"]:
                passed += 1
                print("TEST SONUCU: GECTI")
            else:
                print("TEST SONUCU: KALDI")

        except (
            urllib.error.URLError,
            TimeoutError,
            KeyError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ) as error:
            print("TEST SONUCU: HATA")
            print("Hata:", error)

        print()

    print("=" * 48)
    print(f"SONUC: {passed}/{len(TESTS)} test gecti.")
    print(
        "NOT: Bunlar kurgusal ve dar kapsamli testlerdir; "
        "bilimsel dogrulama degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji olusturulmadi veya degistirilmedi.")
    print("Alim-satim islemi tetiklenmedi.")


if __name__ == "__main__":
    main()