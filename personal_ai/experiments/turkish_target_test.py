import json
import urllib.error
import urllib.request


MODEL = "qwen2.5:7b"
URL = "http://127.0.0.1:11434/api/chat"

ALLOWED = {
    "LONG_TERM_BTC_VOL",
    "BITCOIN_PRICE",
    "UNKNOWN",
}

# Beklenen cevaplar model calistirilmadan once sabitlendi.
TESTS = [
    (
        "Kisa ifade: oynaklik",
        "uzun vadeli Bitcoin oynakligi",
        "LONG_TERM_BTC_VOL",
    ),
    (
        "Kisa ifade: fiyat",
        "Bitcoin fiyati",
        "BITCOIN_PRICE",
    ),
    (
        "Iddia 1",
        "S&P 500 gerceklesen oynakliginin uzun vadeli "
        "Bitcoin oynakligi uzerinde negatif etkisi var.",
        "LONG_TERM_BTC_VOL",
    ),
    (
        "Iddia 2",
        "S&P 500 oynaklik risk priminin uzun vadeli "
        "Bitcoin oynakligi uzerinde pozitif etkisi var.",
        "LONG_TERM_BTC_VOL",
    ),
    (
        "Iddia 3",
        "Baltic Dry Index ile uzun vadeli Bitcoin "
        "oynakligi arasinda pozitif iliski var.",
        "LONG_TERM_BTC_VOL",
    ),
    (
        "Iddia 4",
        "S&P 500 gerceklesen oynakliginin uzun vadeli "
        "Bitcoin oynakligi uzerinde pozitif etkisi var.",
        "LONG_TERM_BTC_VOL",
    ),
    (
        "Iddia 5",
        "Baltic Dry Index ile uzun vadeli Bitcoin "
        "oynakligi arasinda negatif iliski var.",
        "LONG_TERM_BTC_VOL",
    ),
]


def ask_ollama(text):
    system = """
Identify the TARGET variable described in the user's text.

Return ONLY a JSON object with exactly one field:
{"target": "..."}

Allowed values:
LONG_TERM_BTC_VOL
BITCOIN_PRICE
UNKNOWN

Read the entire phrase carefully.
Volatility and price are different quantities.
If the target is unclear, return UNKNOWN.

Do not evaluate whether the claim is true.
Do not provide trading advice.
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

    if set(raw) != {"target"}:
        return None

    if raw["target"] not in ALLOWED:
        return None

    return raw["target"]


def main():
    print("PERSONAL AI - TURKCE HEDEF DEGISKEN TESTI")
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
        "Bu test yalnizca hedef degisken etiketlemesini "
        "olcer; iddialarin dogrulugunu olcmez."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()