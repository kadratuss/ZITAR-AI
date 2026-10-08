import json
import random
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path


DB_PATH = Path("research.db")
SOURCE_ID = 14
KNOWLEDGE_ID = 3

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:7b"

# Bunlar yalnızca kaynak özetine ilişkin dar kapsamlı test iddialarıdır.
# Beklenen cümle numaraları, karıştırılmamış kaynak metnine göredir.
TESTS = [
    {
        "name": "Fiyat etkinliği",
        "claim": (
            "Yazarlar, algoritmik işlemlerin fiyat etkinliğinin iki "
            "ölçüsünde iyileşmeye neden olduğunu bildiriyor."
        ),
        "expected": "CONSISTENT",
        "original_sentence": 2,
    },
    {
        "name": "Likidite sağlayan bilgisayarlar",
        "claim": (
            "Özete göre arbitraj fırsatlarındaki azalma, esas olarak "
            "bilgisayarların likidite sağlamasıyla ilişkilidir."
        ),
        "expected": "CONSISTENT",
        "original_sentence": 3,
    },
    {
        "name": "Yavaş işlem yapanların maliyeti",
        "claim": (
            "Yazarlar, fiyat keşfinin hızlanmasının daha yavaş işlem "
            "yapanlar için ters seçim maliyetlerini artırabileceğini belirtiyor."
        ),
        "expected": "CONSISTENT",
        "original_sentence": 4,
    },
    {
        "name": "Uydurma başarı yüzdesi",
        "claim": (
            "Araştırma, algoritmik işlemlerin tahmin başarısını yüzde 95 "
            "olarak ölçmüştür."
        ),
        "expected": "UNSUPPORTED",
        "original_sentence": None,
    },
    {
        "name": "Kaynağa aykırı piyasa kalitesi iddiası",
        "claim": (
            "Yazarlar, algoritmik işlemlerin ortalama piyasa kalitesinde "
            "bozulmaya neden olduğunu bulmuştur."
        ),
        "expected": "CONTRADICTION",
        "original_sentence": 7,
    },
]


def load_source():
    if not DB_PATH.is_file():
        raise RuntimeError(f"Veritabanı bulunamadı: {DB_PATH.resolve()}")

    connection = sqlite3.connect(
        f"file:{DB_PATH.resolve().as_posix()}?mode=ro",
        uri=True,
    )

    try:
        row = connection.execute(
            """
            SELECT s.title, k.topic, k.content
            FROM sources AS s
            JOIN knowledge AS k ON k.source_id = s.id
            WHERE s.id = ? AND k.id = ?
            """,
            (SOURCE_ID, KNOWLEDGE_ID),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise RuntimeError(
            f"Kaynak {SOURCE_ID} / bilgi kaydı {KNOWLEDGE_ID} bulunamadı."
        )

    title, topic, content = row

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Kaynak metni boş.")

    return title, topic, content.strip()


def split_sentences(content):
    # Bu testteki İngilizce özet için cümle sonlarını ayırır.
    # Genel amaçlı bilimsel PDF ayrıştırıcısı değildir.
    content = re.sub(r"^\s*ABSTRACT\s+", "", content, flags=re.I)
    content = re.sub(r"\s+", " ", content).strip()

    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", content)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def ask_ollama(claim, numbered_sentences):
    source_text = "\n".join(
        f"{number}. {sentence}"
        for number, sentence in numbered_sentences
    )

    system_prompt = (
        "You are a strict evidence checker. "
        "Evaluate a Turkish claim ONLY against the numbered English "
        "source sentences supplied by the user. "
        "Do not use outside knowledge. "
        "Return exactly one JSON object with these keys: "
        "verdict, sentence_id, reason_tr. "
        "verdict must be CONSISTENT, CONTRADICTION, or UNSUPPORTED. "
        "CONSISTENT means the source explicitly supports the claim. "
        "CONTRADICTION means the source explicitly states the opposite. "
        "UNSUPPORTED means neither support nor contradiction is explicit. "
        "For CONSISTENT or CONTRADICTION, sentence_id must be the number "
        "of the single strongest source sentence. "
        "For UNSUPPORTED, sentence_id must be null. "
        "Do not invent a sentence number. "
        "Do not treat absence of information as a contradiction. "
        "Keep reason_tr brief and in Turkish."
    )

    user_prompt = (
        "KAYNAK CÜMLELERİ:\n"
        f"{source_text}\n\n"
        "DEĞERLENDİRİLECEK İDDİA:\n"
        f"{claim}\n\n"
        "Yalnızca istenen JSON nesnesini döndür."
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
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            "Ollama bağlantısı kurulamadı. Ollama'nın açık ve "
            f"'{MODEL}' modelinin kurulu olduğunu kontrol et. "
            f"Ayrıntı: {exc}"
        ) from exc

    raw_content = result.get("message", {}).get("content", "")

    try:
        answer = json.loads(raw_content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Model geçerli JSON döndürmedi:\n{raw_content}"
        ) from exc

    if not isinstance(answer, dict):
        raise RuntimeError(f"JSON nesne değil: {answer!r}")

    return answer


def validate_answer(answer, numbered_sentences, test, mapping):
    verdict = answer.get("verdict")
    sentence_id = answer.get("sentence_id")

    if verdict not in {
        "CONSISTENT",
        "CONTRADICTION",
        "UNSUPPORTED",
    }:
        return False, "Geçersiz karar etiketi."

    # bool, Python'da int alt türüdür; True/False numara kabul edilmez.
    if sentence_id is not None and (
        type(sentence_id) is not int
        or sentence_id < 1
        or sentence_id > len(numbered_sentences)
    ):
        return False, "Geçersiz cümle numarası."

    if verdict == "UNSUPPORTED" and sentence_id is not None:
        return False, "UNSUPPORTED için cümle numarası boş olmalı."

    if verdict != "UNSUPPORTED" and sentence_id is None:
        return False, "Destek/çelişki kararı için cümle numarası gerekli."

    if verdict != test["expected"]:
        return (
            False,
            f"Karar uyuşmadı: beklenen={test['expected']}, gelen={verdict}.",
        )

    expected_original = test["original_sentence"]

    if expected_original is None:
        if sentence_id is not None:
            return False, "Desteklenmeyen iddiaya cümle bağlandı."
        return True, "Desteklenmeyen iddia doğru ayrıldı."

    selected_original = mapping.get(sentence_id)

    if selected_original != expected_original:
        return (
            False,
            "Kaynak cümlesi uyuşmadı: "
            f"beklenen orijinal={expected_original}, "
            f"seçilen orijinal={selected_original}.",
        )

    return True, "Karar ve kaynak cümlesi uyuştu."


def main():
    print("PERSONAL AI - İKİNCİ GERÇEK KAYNAK TESTİ")
    print("=" * 55)
    print("Veritabanı: yalnızca okuma | Strateji ve işlem: kapalı")
    print()

    title, topic, content = load_source()
    sentences = split_sentences(content)

    print(f"Kaynak ID: {SOURCE_ID}")
    print(f"Bilgi kaydı ID: {KNOWLEDGE_ID}")
    print(f"Başlık: {title}")
    print(f"Konu: {topic}")
    print(f"Model: {MODEL}")
    print(f"Cümle sayısı: {len(sentences)}")
    print()

    print("ORİJİNAL KAYNAK CÜMLELERİ")
    print("-" * 55)
    for number, sentence in enumerate(sentences, start=1):
        print(f"{number}. {sentence}")
    print()

    # Beklenen cümleler ancak metin tam beklenen biçimde ayrıldıysa
    # anlamlıdır. Farklı ayrıştırmada sessizce yanlış test yapmayız.
    if len(sentences) != 7:
        print(
            "DURDURULDU: Bu özet için 7 cümle bekleniyordu; "
            f"{len(sentences)} bulundu. Test beklentilerini "
            "tahmin ederek değiştirmiyoruz."
        )
        return

    checks = {
        2: "We find that AT causes an improvement in two measures",
        3: "We show that the reduction in arbitrage opportunities",
        4: "This result is consistent with the view",
        7: "This correlation, however, does not appear",
    }

    for number, expected_start in checks.items():
        if not sentences[number - 1].startswith(expected_start):
            print(
                "DURDURULDU: Kaynak cümlesi beklenen metinle "
                f"uyuşmuyor. Orijinal cümle: {number}"
            )
            return

    passed = 0
    total = 0

    for round_number, seed in enumerate((17, 42, 99), start=1):
        rng = random.Random(seed)
        shuffled = list(enumerate(sentences, start=1))
        rng.shuffle(shuffled)

        numbered_sentences = [
            (new_number, sentence)
            for new_number, (_, sentence) in enumerate(
                shuffled, start=1
            )
        ]

        # Yeni numara -> orijinal numara.
        mapping = {
            new_number: original_number
            for new_number, (original_number, _) in enumerate(
                shuffled, start=1
            )
        }

        print("=" * 55)
        print(f"TUR {round_number} | Karıştırma tohumu: {seed}")
        print("Yeni numara -> orijinal numara:")
        print(mapping)

        for test_number, test in enumerate(TESTS, start=1):
            total += 1
            print()
            print(
                f"TEST {round_number}.{test_number}: {test['name']}"
            )
            print(f"İddia: {test['claim']}")
            print(
                f"Beklenen: {test['expected']} | "
                f"orijinal cümle={test['original_sentence']}"
            )
            print("Ollama yanıtı bekleniyor...")

            try:
                answer = ask_ollama(
                    test["claim"],
                    numbered_sentences,
                )
            except RuntimeError as exc:
                print(f"DURDURULDU: {exc}")
                print(
                    "Veritabanına yazılmadı; strateji veya işlem "
                    "tetiklenmedi."
                )
                return

            print("HAM MODEL YANITI:")
            print(
                json.dumps(
                    answer,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            success, reason = validate_answer(
                answer,
                numbered_sentences,
                test,
                mapping,
            )

            if success:
                passed += 1

            print(f"SONUÇ: {'GEÇTİ' if success else 'KALDI'}")
            print(f"Gerekçe: {reason}")

    print()
    print("=" * 55)
    print(f"GENEL SONUÇ: {passed}/{total} kontrol geçti.")
    print(
        "NOT: Tek bir gerçek özet üzerinde dar kapsamlı bir "
        "kaynak eşleştirme testidir."
    )
    print("Bilimsel doğrulama veya genel güvenilirlik kanıtı değildir.")
    print("Veritabanına yazılmadı.")
    print("Strateji oluşturulmadı veya değiştirilmedi.")
    print("Alım-satım işlemi tetiklenmedi.")


if __name__ == "__main__":
    main()