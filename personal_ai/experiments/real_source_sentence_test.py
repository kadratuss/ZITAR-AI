import json
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path


# AYARLAR
SOURCE_ID = 9
MODEL = "qwen2.5:7b"

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATABASE = PROJECT_DIR / "research.db"
OLLAMA_URL = "http://localhost:11434/api/chat"


TESTS = [
    {
        "name": "Yontem",
        "claim": (
            "Calisma, duragan olmayan finansal zaman serilerini "
            "SVM'ye dahil ederek uyarlamali parametreler oneriyor."
        ),
        "expected": "CONSISTENT",
        "expected_sentence": 5,
    },
    {
        "name": "Veri seti",
        "claim": (
            "Calismada Chicago Mercantile Market'ten bes gercek "
            "vadeli islem sozlesmesi veri seti olarak kullaniliyor."
        ),
        "expected": "CONSISTENT",
        "expected_sentence": 6,
    },
    {
        "name": "Karsilastirma",
        "claim": (
            "Yazarlar, SVM'nin finansal tahminde BP sinir agindan "
            "daha iyi sonuc verdigini raporluyor."
        ),
        "expected": "CONSISTENT",
        "expected_sentence": 7,
    },
    {
        "name": "Uydurma oran",
        "claim": "Makale SVM'nin tahmin basarisini yuzde 95 raporluyor.",
        "expected": "UNSUPPORTED",
        "expected_sentence": None,
    },
    {
        "name": "Kaynak disi islem",
        "claim": "Bu makale bugun Bitcoin alinmasini oneriyor.",
        "expected": "UNSUPPORTED",
        "expected_sentence": None,
    },
]


def get_source_text():
    if not DATABASE.exists():
        raise FileNotFoundError(f"Veritabani bulunamadi: {DATABASE}")

    connection = sqlite3.connect(
        f"file:{DATABASE.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        row = connection.execute(
            """
            SELECT s.title, k.id, k.topic, k.content
            FROM knowledge AS k
            JOIN sources AS s ON s.id = k.source_id
            WHERE s.id = ?
              AND k.content IS NOT NULL
              AND TRIM(k.content) != ''
            ORDER BY k.id
            """,
            (SOURCE_ID,),
        ).fetchall()
    finally:
        connection.close()

    if not row:
        raise RuntimeError(
            f"Kaynak {SOURCE_ID} icin knowledge tablosunda metin bulunamadi."
        )

    # Yanlislikla birden fazla farkli metni birlestirmiyoruz.
    if len(row) != 1:
        raise RuntimeError(
            f"Kaynak {SOURCE_ID} icin {len(row)} bilgi kaydi var. "
            "Hangi metnin kullanilacagi belirsiz; islem durduruldu."
        )

    title, knowledge_id, topic, content = row[0]

    if not topic or "özet" not in topic.lower() and "ozet" not in topic.lower():
        raise RuntimeError(
            f"Bilgi kaydi {knowledge_id} acikca ozet olarak "
            f"etiketlenmemis. Konu: {topic!r}"
        )

    return title, knowledge_id, content.strip()


def split_sentences(text):
    # Bu kaynak ozeti icin basit cumle ayirma.
    # Genel amacli akademik PDF cumle ayirici degildir.
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def ask_ollama(sentences, claim):
    numbered_text = "\n".join(
        f"{number}. {sentence}"
        for number, sentence in enumerate(sentences, start=1)
    )

    system_prompt = """
You compare a claim against a supplied source excerpt.

Return ONLY a JSON object with exactly these fields:
{
  "verdict": "CONSISTENT or CONTRADICTION or UNSUPPORTED",
  "sentence_id": integer or null,
  "reason_tr": "Brief explanation in Turkish"
}

Rules:
- Use ONLY the numbered source sentences.
- CONSISTENT: the source directly supports the claim.
- CONTRADICTION: the source directly states the opposite.
- UNSUPPORTED: the source does not establish the claim.
- sentence_id MUST be an integer from the supplied numbered sentences.
- For UNSUPPORTED, use sentence_id: null.
- Never invent a sentence number.
- Never infer a trading recommendation or a success percentage.
- The source is an abstract, not independent scientific verification.
""".strip()

    user_prompt = (
        f"SOURCE:\n{numbered_text}\n\n"
        f"CLAIM:\n{claim}\n\n"
        "Return the JSON object."
    )

    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        outer = json.loads(response.read().decode("utf-8"))

    raw_answer = outer.get("message", {}).get("content", "")
    return raw_answer


def inspect_answer(raw_answer, sentences, expected, expected_sentence):
    try:
        answer = json.loads(raw_answer)
    except json.JSONDecodeError as error:
        return False, f"Model gecerli JSON vermedi: {error}"

    if not isinstance(answer, dict):
        return False, "Modelin JSON yaniti bir nesne degil."

    verdict = answer.get("verdict")
    sentence_id = answer.get("sentence_id")

    print(f"Model karari: {verdict!r}")
    print(f"Model cumle numarasi: {sentence_id!r}")
    print(f"Model gerekcesi: {answer.get('reason_tr')!r}")

    if verdict not in {"CONSISTENT", "CONTRADICTION", "UNSUPPORTED"}:
        return False, "Gecersiz karar etiketi."

    if verdict != expected:
        return False, (
            f"Karar uyusmuyor: beklenen={expected}, gelen={verdict}"
        )

    if expected_sentence is None:
        if sentence_id is not None:
            return False, (
                "Desteklenmeyen iddia icin cumle numarasi null olmali; "
                f"gelen={sentence_id!r}"
            )
        return True, "Karar ve bos cumle numarasi uyustu."

    # bool, Python'da int alt turudur; True'yu 1 kabul etmiyoruz.
    if type(sentence_id) is not int:
        return False, (
            "Cumle numarasi tam sayi degil: "
            f"{sentence_id!r} (tip={type(sentence_id).__name__})"
        )

    if not 1 <= sentence_id <= len(sentences):
        return False, (
            f"Gecersiz cumle numarasi: {sentence_id!r}. "
            f"Gecerli aralik: 1-{len(sentences)}"
        )

    print(f"Secilen kaynak cumlesi: {sentences[sentence_id - 1]}")

    if sentence_id != expected_sentence:
        return False, (
            f"Cumle numarasi farkli: beklenen={expected_sentence}, "
            f"gelen={sentence_id}"
        )

    return True, "Karar ve cumle numarasi uyustu."


def main():
    print("PERSONAL AI - GERCEK KAYNAK CUMLE TESTI / TESHIS")
    print("=" * 58)
    print("Veritabani: sadece okuma | Strateji/islem: kapali")

    title, knowledge_id, text = get_source_text()
    sentences = split_sentences(text)

    print(f"\nKaynak ID: {SOURCE_ID}")
    print(f"Bilgi kaydi ID: {knowledge_id}")
    print(f"Baslik: {title}")
    print(f"Model: {MODEL}")
    print(f"Cumle sayisi: {len(sentences)}")

    print("\nKAYNAK CUMLELERI")
    print("-" * 58)
    for number, sentence in enumerate(sentences, start=1):
        print(f"{number}. {sentence}")

    passed = 0

    for index, test in enumerate(TESTS, start=1):
        print(f"\nTEST {index}: {test['name']}")
        print("-" * 58)
        print(f"Iddia: {test['claim']}")
        print(
            f"Beklenen: {test['expected']} / "
            f"cumle={test['expected_sentence']!r}"
        )

        print("Ollama yaniti bekleniyor...")

        try:
            raw_answer = ask_ollama(sentences, test["claim"])
        except urllib.error.URLError as error:
            print(f"BAGLANTI HATASI: {error}")
            print("Ollama calisiyor mu ve model yuklu mu kontrol et.")
            return
        except Exception as error:
            print(f"ISTEK HATASI: {type(error).__name__}: {error}")
            return

        print("\nHAM MODEL YANITI:")
        print(raw_answer)

        success, reason = inspect_answer(
            raw_answer,
            sentences,
            test["expected"],
            test["expected_sentence"],
        )

        print(f"\nSONUC: {'GECTI' if success else 'KALDI'}")
        print(f"Gerekce: {reason}")

        if success:
            passed += 1

    print("\n" + "=" * 58)
    print(f"GENEL SONUC: {passed}/{len(TESTS)} test gecti.")
    print("NOT: Bu, dar kapsamli bir kaynak eslestirme testidir.")
    print("Bilimsel dogrulama degildir.")
    print("Veritabanina yazilmadi.")
    print("Strateji olusturulmadi veya degistirilmedi.")
    print("Alim-satim islemi tetiklenmedi.")


if __name__ == "__main__":
    main()