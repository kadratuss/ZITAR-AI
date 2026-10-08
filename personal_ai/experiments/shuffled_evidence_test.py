import json
import random
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path


SOURCE_ID = 9
MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://localhost:11434/api/chat"

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATABASE = PROJECT_DIR / "research.db"

# Beklenen numaralar, kaynagin ORIJINAL cumle numaralaridir.
TESTS = [
    {
        "name": "Yontem - farkli ifade",
        "claim": (
            "Yazarlar, finansal serilerin zamanla degisen yapisini "
            "SVM parametrelerine yansitmayi oneriyor."
        ),
        "expected_verdict": "CONSISTENT",
        "expected_original_id": 5,
    },
    {
        "name": "Veri seti - farkli ifade",
        "claim": (
            "Deneylerde Chicago Mercantile Market kaynakli "
            "bes vadeli islem kontrati kullanilmis."
        ),
        "expected_verdict": "CONSISTENT",
        "expected_original_id": 6,
    },
    {
        "name": "Karsilastirma - farkli ifade",
        "claim": (
            "Ozet, finansal tahmin deneyinde SVM'nin BP sinir "
            "agindan daha iyi sonuc verdigini bildiriyor."
        ),
        "expected_verdict": "CONSISTENT",
        "expected_original_id": 7,
    },
    {
        "name": "Uydurma yuzde",
        "claim": "Arastirmada SVM icin yuzde 95 basari olculmus.",
        "expected_verdict": "UNSUPPORTED",
        "expected_original_id": None,
    },
    {
        "name": "Kaynak disi tavsiye",
        "claim": "Yazarlar bugun Bitcoin satin alinmasini tavsiye ediyor.",
        "expected_verdict": "UNSUPPORTED",
        "expected_original_id": None,
    },
]


def load_source():
    if not DATABASE.exists():
        raise FileNotFoundError(f"Veritabani bulunamadi: {DATABASE}")

    connection = sqlite3.connect(
        f"file:{DATABASE.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        rows = connection.execute(
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

    if len(rows) != 1:
        raise RuntimeError(
            f"Kaynak {SOURCE_ID} icin tam bir metin kaydi "
            f"bekleniyordu; bulunan: {len(rows)}"
        )

    title, knowledge_id, topic, content = rows[0]

    normalized_topic = (topic or "").lower()
    if "özet" not in normalized_topic and "ozet" not in normalized_topic:
        raise RuntimeError(
            f"Bilgi kaydi ozet olarak etiketlenmemis: {topic!r}"
        )

    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z])", content.strip())
        if part.strip()
    ]

    if len(sentences) != 9:
        raise RuntimeError(
            f"Bu test 9 cumlelik kaynak icin hazirlandi; "
            f"bulunan: {len(sentences)}. Kaynak degismis olabilir."
        )

    return title, knowledge_id, sentences


def ask_model(numbered_sentences, claim):
    source_text = "\n".join(
        f"{shown_id}. {sentence}"
        for shown_id, sentence in numbered_sentences
    )

    system_prompt = """
Compare the claim ONLY with the numbered source excerpt.

Return ONLY a JSON object:
{
  "verdict": "CONSISTENT or CONTRADICTION or UNSUPPORTED",
  "sentence_id": integer or null,
  "reason_tr": "Brief explanation in Turkish"
}

Rules:
- Sentence numbers refer to the numbers in THIS prompt.
- CONSISTENT: a source sentence directly supports the claim.
- CONTRADICTION: a source sentence directly states the opposite.
- UNSUPPORTED: the excerpt does not establish the claim.
- For CONSISTENT or CONTRADICTION, choose one relevant sentence_id.
- For UNSUPPORTED, sentence_id must be null.
- Do not invent source sentences, success percentages or trading advice.
- The excerpt is an abstract, not independent scientific verification.
""".strip()

    payload = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"SOURCE:\n{source_text}\n\n"
                    f"CLAIM:\n{claim}\n\n"
                    "Return JSON only."
                ),
            },
        ],
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))

    return result.get("message", {}).get("content", "")


def check_answer(raw, test, shown_to_original):
    try:
        answer = json.loads(raw)
    except json.JSONDecodeError as error:
        return False, f"Gecersiz JSON: {error}"

    if not isinstance(answer, dict):
        return False, "JSON nesnesi gelmedi."

    verdict = answer.get("verdict")
    shown_id = answer.get("sentence_id")

    print(f"Model karari: {verdict!r}")
    print(f"Modelin sectigi yeni numara: {shown_id!r}")
    print(f"Model gerekcesi: {answer.get('reason_tr')!r}")

    if verdict != test["expected_verdict"]:
        return False, (
            f"Karar hatali. Beklenen={test['expected_verdict']}, "
            f"gelen={verdict!r}"
        )

    expected_original_id = test["expected_original_id"]

    if expected_original_id is None:
        if shown_id is not None:
            return False, (
                "UNSUPPORTED iddiasinda cumle numarasi null olmali."
            )
        return True, "Desteklenmeyen iddia dogru ayrildi."

    if type(shown_id) is not int:
        return False, f"Cumle numarasi tam sayi degil: {shown_id!r}"

    original_id = shown_to_original.get(shown_id)
    print(f"Secilen cumlenin ORIJINAL numarasi: {original_id!r}")

    if original_id != expected_original_id:
        return False, (
            f"Yanlis kanit cumlesi. Beklenen orijinal "
            f"numara={expected_original_id}, gelen={original_id!r}"
        )

    return True, "Karar ve gercek kaynak cumlesi uyustu."


def main():
    print("PERSONAL AI - KARISTIRILMIS KANIT TESTI")
    print("=" * 58)
    print("Veritabani: sadece okuma | Strateji ve islem: kapali")

    title, knowledge_id, sentences = load_source()

    print(f"\nKaynak ID: {SOURCE_ID}")
    print(f"Bilgi kaydi ID: {knowledge_id}")
    print(f"Baslik: {title}")
    print(f"Model: {MODEL}")

    total = 0
    passed = 0

    # Uc farkli, tekrar uretilebilir karistirma.
    for round_number, seed in enumerate((17, 42, 99), start=1):
        rng = random.Random(seed)

        # (orijinal_numara, cumle)
        shuffled = list(enumerate(sentences, start=1))
        rng.shuffle(shuffled)

        # Modele verilen yeni numaralar 1'den baslar.
        numbered_sentences = [
            (new_id, sentence)
            for new_id, (_, sentence) in enumerate(shuffled, start=1)
        ]

        shown_to_original = {
            new_id: original_id
            for new_id, (original_id, _) in enumerate(shuffled, start=1)
        }

        print(f"\n{'=' * 58}")
        print(f"TUR {round_number} | Karistirma tohumu: {seed}")
        print("Yeni numara -> Orijinal numara:")
        print(shown_to_original)

        for index, test in enumerate(TESTS, start=1):
            total += 1

            print(f"\nTEST {round_number}.{index}: {test['name']}")
            print("-" * 58)
            print(f"Iddia: {test['claim']}")
            print(
                f"Beklenen: {test['expected_verdict']} | "
                f"orijinal cumle={test['expected_original_id']!r}"
            )
            print("Ollama yaniti bekleniyor...")

            try:
                raw = ask_model(numbered_sentences, test["claim"])
            except urllib.error.URLError as error:
                print(f"BAGLANTI HATASI: {error}")
                return
            except Exception as error:
                print(f"ISTEK HATASI: {type(error).__name__}: {error}")
                return

            print("\nHAM MODEL YANITI:")
            print(raw)

            success, reason = check_answer(
                raw,
                test,
                shown_to_original,
            )

            print(f"SONUC: {'GECTI' if success else 'KALDI'}")
            print(f"Gerekce: {reason}")

            if success:
                passed += 1

    print(f"\n{'=' * 58}")
    print(f"GENEL SONUC: {passed}/{total} kontrol gecti.")
    print("NOT: Tek bir ozet uzerindeki dar kapsamli testtir.")
    print("Bilimsel dogrulama veya genel guvenilirlik kaniti degildir.")
    print("Veritabanina yazilmadi.")
    print("Strateji olusturulmadi veya degistirilmedi.")
    print("Alim-satim islemi tetiklenmedi.")


if __name__ == "__main__":
    main()