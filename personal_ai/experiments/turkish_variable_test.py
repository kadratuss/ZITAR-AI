import json
import urllib.error
import urllib.request


MODEL = "qwen2.5:7b"
URL = "http://127.0.0.1:11434/api/chat"

ALLOWED = {
    "SP500_REALIZED_VOL",
    "SP500_VOL_RISK_PREMIUM",
    "BITCOIN_PRICE",
    "UNKNOWN",
}

# Dogru cevaplar Ollama calistirilmadan once sabitlendi.
TESTS = [
    (
        "Kisa ifade: gerceklesen oynaklik",
        "S&P 500 gerceklesen oynakligi",
        "SP500_REALIZED_VOL",
    ),
    (
        "Kisa ifade: oynaklik risk primi",
        "S&P 500 oynaklik risk primi",
        "SP500_VOL_RISK_PREMIUM",
    ),
    (
        "Kisa ifade: Bitcoin fiyati",
        "Bitcoin fiyati",
        "BITCOIN_PRICE",
    ),
    (
        "Tam iddia: gerceklesen oynaklik",
        "S&P 500 gerceklesen oynakliginin uzun vadeli "
        "Bitcoin oynakligi uzerinde negatif etkisi var.",
        "SP500_REALIZED_VOL",
    ),
    (
        "Tam iddia: risk primi - pozitif etki",
        "S&P 500 oynaklik risk priminin uzun vadeli "
        "Bitcoin oynakligi uzerinde pozitif etkisi var.",
        "SP500_VOL_RISK_PREMIUM",
    ),
    (
        "Tam iddia: risk primi - ters yon",
        "S&P 500 oynaklik risk priminin uzun vadeli "
        "Bitcoin oynakligi uzerinde negatif etkisi var.",
        "SP500_VOL_RISK_PREMIUM",
    ),
    (
        "Tam iddia: Bitcoin fiyati",
        "Bitcoin fiyati uzun vadeli Bitcoin oynakligini etkiliyor.",
        "BITCOIN_PRICE",
    ),
]


def ask_ollama(text):
    system = """
Identify only the EXPLANATORY variable in the user's text.

Return ONLY a JSON object with exactly one field:
{"variable": "..."}

Allowed values:
SP500_REALIZED_VOL
SP500_VOL_RISK_PREMIUM
BITCOIN_PRICE
UNKNOWN

The explanatory variable is the factor described as
affecting or being related to another quantity.

Distinguish the explanatory variable from the target.
Use UNKNOWN if the explanatory variable is unclear.
Do not evaluate the claim or provide trading advice.
""".strip()

    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
    }

    request = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        outer = json.loads(response.read().decode("utf-8"))

    raw = json.loads(outer["message"]["content"])

    if not isinstance(raw, dict):
        return None

    if set(raw) != {"variable"}:
        return None

    if raw["variable"] not in ALLOWED:
        return None

    return raw["variable"]


def main():
    print("PERSONAL AI - ACIKLAYICI DEGISKEN TESTI")
    print("=" * 60)
    print("Model:", MODEL)
    print("Veritabani: kullanilmiyor")
    print("Strateji ve alim-satim: kapali")

    passed = 0

    for index, (name, text, expected) in enumerate(TESTS, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {index}: {name}")
        print("Metin:", text)
        print("Beklenen:", expected)

        try:
            actual = ask_ollama(text)
        except (
            urllib.error.URLError,
            TimeoutError,
            ValueError,
            KeyError,
            TypeError,
        ) as error:
            print("Model hatasi:", error)
            actual = None

        print("Modelin cikardigi:", actual)

        success = actual == expected
        passed += int(success)

        print("SONUC:", "GECTI" if success else "KALDI")

    print("\n" + "=" * 60)
    print(f"GENEL SONUC: {passed}/{len(TESTS)}")
    print(
        "Bu test yalnizca aciklayici degisken "
        "etiketlemesini olcer."
    )
    print("Iddialarin dogrulugunu veya modelin genel")
    print("guvenilirligini olcmez.")
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()