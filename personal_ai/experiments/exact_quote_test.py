
import json
import urllib.error
import urllib.request

MODEL = "qwen2.5:7b"
URL = "http://127.0.0.1:11434/api/generate"

# Beklenen cevaplar modele gonderilmez.
TESTS = [
    {
        "name": "Olumsuzluk ve katilimci sayisi",
        "source": (
            "Calismada 85 katilimci vardi. "
            "LSTM yontemi kullanilmadi. "
            "Basari orani raporlanmadi."
        ),
        "expected": {
            "participant_count": 85,
            "uses_lstm": False,
            "success_rate": None,
        },
    },
    {
        "name": "Olumlu ifade ve basari orani",
        "source": (
            "Calismada 120 katilimci vardi. "
            "LSTM yontemi kullanildi. "
            "Test verisinde basari orani %72 olarak raporlandi."
        ),
        "expected": {
            "participant_count": 120,
            "uses_lstm": True,
            "success_rate": 72,
        },
    },
    {
        "name": "Eksik bilgi",
        "source": (
            "Arastirma kripto para piyasalarini inceliyor. "
            "Katilimci sayisi, kullanilan algoritma ve "
            "basari orani belirtilmedi."
        ),
        "expected": {
            "participant_count": None,
            "uses_lstm": None,
            "success_rate": None,
        },
    },
]

PROMPT = """
Asagidaki KAYNAK metninden uc alani cikar.

KAYNAK:
{source}

Kurallar:
- Yalnizca kaynakta acikca bulunan bilgileri kullan.
- Bilgi belirtilmiyorsa value alanina null yaz.
- evidence alanina kaynakta gecen TAM CUMLEYI
  HIC DEGISTIRMEDEN kopyala.
- Kanit cumlesini kisaltma, yeniden yazma veya cevirme.
- Bir cumle birden fazla alanla ilgiliyse ayni tam
  cumleyi her ilgili alan icin tekrar kullanabilirsin.
- Yalnizca gecerli JSON dondur.

JSON bicimi:
{{
  "facts": [
    {{"property": "participant_count", "value": null, "evidence": ""}},
    {{"property": "uses_lstm", "value": null, "evidence": ""}},
    {{"property": "success_rate", "value": null, "evidence": ""}}
  ]
}}
"""


def ask_model(source):
    payload = json.dumps({
        "model": MODEL,
        "prompt": PROMPT.format(source=source),
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


def exact_sentence_found(evidence, source):
    if not isinstance(evidence, str) or not evidence:
        return False

    # Bu deneyde kaynak cumleleri noktayla ayriliyor.
    sentences = [
        part.strip() + "."
        for part in source.split(".")
        if part.strip()
    ]

    return evidence in sentences


def main():
    print("PERSONAL AI - BIREBIR KANIT TESTI")
    print("--------------------------------")

    passed = 0
    total = 0

    for test in TESTS:
        print("\nTEST:", test["name"])

        try:
            result = ask_model(test["source"])
            facts = result.get("facts")

            if not isinstance(facts, list):
                print("HATA: facts listesi yok.")
                total += 3
                continue

            for prop, expected in test["expected"].items():
                total += 1

                matches = [
                    fact for fact in facts
                    if isinstance(fact, dict)
                    and fact.get("property") == prop
                ]

                if len(matches) != 1:
                    print(prop, "-> KACIRDI: Alan eksik veya tekrarli.")
                    continue

                fact = matches[0]
                actual = fact.get("value")
                evidence = fact.get("evidence")

                value_ok = (
                    type(actual) is type(expected)
                    and actual == expected
                )
                quote_ok = exact_sentence_found(
                    evidence, test["source"]
                )

                ok = value_ok and quote_ok
                passed += int(ok)

                print(
                    f"{prop}: {'GECTI' if ok else 'KACIRDI'}"
                )
                print("  Beklenen:", expected)
                print("  Qwen:", actual)
                print("  Tam cumle eslesmesi:", quote_ok)
                print("  Kanit:", evidence)

        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
        ) as exc:
            total += 3
            print("Model hatasi:", exc)

    print("\n--------------------------------")
    print(f"SONUC: {passed}/{total} kontrol gecti.")
    print("Bu test kurgusal kaynaklarla yapildi.")
    print("Kanit eslesmesi, anlamsal veya bilimsel dogrulama degildir.")
    print("Veritabanina yazilmadi.")


if __name__ == "__main__":
    main()