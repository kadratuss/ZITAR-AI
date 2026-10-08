
import json
import urllib.error
import urllib.request

from test_extraction_rules import check_fact


MODEL = "qwen2.5:7b"
URL = "http://127.0.0.1:11434/api/generate"

SOURCE = (
    "Makale 2024 yilinda yayimlandi. "
    "Calismada 85 katilimci vardi. "
    "LSTM yontemi kullanilmadi. "
    "Makalenin basari orani belirtilmedi."
)

PROMPT = f"""
Asagidaki kurgusal metinden yalnizca acikca yazan bilgileri cikar.

KAYNAK:
{SOURCE}

Kurallar:
- 85 katilimci sayisidir, basari orani degildir.
- "LSTM kullanilmadi" icin uses_lstm degeri false olmali.
- Basari orani belirtilmemisse success_rate degeri null olmali.
- Her bilgi icin kaynaktan birebir kanit cumlesi yaz.
- Yalnizca gecerli JSON dondur.

JSON bicimi:
{{
  "facts": [
    {{
      "subject": "makale veya calisma",
      "property": "publication_year veya participant_count veya uses_lstm veya success_rate",
      "value": null,
      "evidence": "Kaynaktan birebir cumle"
    }}
  ]
}}
"""


def ask_model():
    payload = json.dumps({
        "model": MODEL,
        "prompt": PROMPT,
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


def main():
    print("PERSONAL AI - CANLI CIKARIM KONTROLU")
    print("----------------------------------")

    try:
        data = ask_model()
        facts = data.get("facts")

        if not isinstance(facts, list):
            print("HATA: facts listesi bulunamadi.")
            return

        for index, fact in enumerate(facts, start=1):
            if not isinstance(fact, dict):
                print(f"\n{index}. Gecersiz bilgi bicimi.")
                continue

            evidence = fact.get("evidence")
            evidence_found = (
                isinstance(evidence, str)
                and bool(evidence.strip())
                and evidence in SOURCE
            )

            print(f"\n{index}. Alan: {fact.get('property')}")
            print("Deger:", fact.get("value"))
            print("Kanit:", evidence)
            print("Kanit metinde:", "EVET" if evidence_found else "HAYIR")

            if not evidence_found:
                print("Kontrol: REVIEW_REQUIRED")
                continue

            if fact.get("property") == "uses_lstm":
                result = check_fact(fact)
                print("LSTM kural kontrolu:", result)
            else:
                print("Kontrol: REVIEW_REQUIRED")

        print("\nHicbir kayit otomatik dogrulanmadi.")
        print("Veritabanina yazilmadi.")

    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
    ) as exc:
        print("Model yaniti alinamadi veya okunamadi:", exc)


if __name__ == "__main__":
    main()