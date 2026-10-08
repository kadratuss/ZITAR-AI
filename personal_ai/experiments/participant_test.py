import json
import urllib.request

texts = [
    "Çalışmada 85 katılımcı vardı.",
    "Çalışmada 120 katılımcı vardı.",
    "Katılımcı sayısı belirtilmedi.",
]

for text in texts:
    prompt = f"""
Yalnızca aşağıdaki kaynak cümlesine dayanarak katılımcı sayısını çıkar.
Sayı varsa JSON sayısı olarak yaz; yoksa null yaz.
Sadece JSON döndür.

Şema: {{"participant_count": null}}

Kaynak: {text}
""".strip()

    payload = json.dumps({
        "model": "qwen2.5:7b",
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode("utf-8")

    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)

    print("Kaynak:", text)
    print("Cevap:", result["response"])
    print("-" * 40)