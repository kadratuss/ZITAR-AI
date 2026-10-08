
import json
import urllib.request
import urllib.error

MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Tamamen kurgusal test kaynagi.
SOURCE = (
    "Makale 2024 yilinda yayimlandi. "
    "Calismada 85 katilimci vardi. "
    "LSTM yontemi kullanilmadi. "
    "Makalenin basari orani belirtilmedi."
)

PROMPT = f"""
Asagidaki metinden bilgi cikar. Yalnizca metinde acikca yazanlari kullan.

KAYNAK:
{SOURCE}

Kurallar:
- Katilimci sayisini basari orani olarak yorumlama.
- "Kullanilmadi" ifadesini "kullanildi" diye degistirme.
- Basari orani belirtilmemisse sayi uydurma.
- Her bilgi icin kaynak metninden birebir bir kanit cumlesi ver.
- Yalnizca gecerli JSON nesnesi dondur. Aciklama veya Markdown ekleme.

JSON bicimi:
{{
  "facts": [
    {{
      "subject": "makale veya calisma",
      "property": "publication_year veya participant_count veya uses_lstm veya success_rate",
      "value": "metindeki deger; bilinmiyorsa null",
      "evidence": "kaynak metninden birebir cumle"
    }}
  ]
}}
"""


def ask_ollama():
    payload = json.dumps({
        "model": MODEL,
        "prompt": PROMPT,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0}
    }).encode("utf-8")

    request = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)

    return json.loads(result["response"])


def main():
    print("PERSONAL AI - KAYNAKTAN BILGI CIKARMA DENEYI")
    print("------------------------------------------")

    try:
        data = ask_ollama()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        print("Model yaniti alinamadi veya JSON okunamadi:", exc)
        return

    facts = data.get("facts")
    if not isinstance(facts, list):
        print("HATA: 'facts' listesi bulunamadi.")
        return

    for number, fact in enumerate(facts, start=1):
        if not isinstance(fact, dict):
            print(f"\n{number}. Gecersiz bilgi bicimi.")
            continue

        evidence = fact.get("evidence")
        evidence_found = (
            isinstance(evidence, str)
            and bool(evidence.strip())
            and evidence in SOURCE
        )

        print(f"\n{number}. Alan: {fact.get('property')}")
        print("Deger:", fact.get("value"))
        print("Kanit:", evidence)
        print(
            "Kanit metinde:",
            "EVET" if evidence_found else "HAYIR"
        )
        print("Durum: REVIEW_REQUIRED")

    print("\nSONUC: Hicbir bilgi otomatik dogrulanmadi.")
    print("Veritabanina yazilmadi.")


if __name__ == "__main__":
    main()