import json
import random
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path


# Bu dosya:
# - research.db veritabanini yalnizca okur.
# - Ollama'ya yerel istek gonderir.
# - Veritabanina yazmaz.
# - Strateji veya alim-satim islemi yapmaz.

SOURCE_ID = 14
KNOWLEDGE_ID = 3
MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
SEEDS = (17, 42, 99)

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "research.db"


def load_source():
    if not DB_PATH.is_file():
        raise RuntimeError(f"Veritabani bulunamadi: {DB_PATH}")

    connection = sqlite3.connect(
        f"file:{DB_PATH.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        row = connection.execute(
            """
            SELECT s.title, k.content
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
            f"Kaynak/bilgi kaydi bulunamadi: {SOURCE_ID}/{KNOWLEDGE_ID}"
        )

    title, content = row

    if not content or not content.strip():
        raise RuntimeError("Kaynak metni bos.")

    text = content.strip()

    if text.upper().startswith("ABSTRACT "):
        text = text[9:].strip()

    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        if part.strip()
    ]

    if len(sentences) != 7:
        raise RuntimeError(
            "Bu test, kaynak 14'teki 7 cumlelik ozete ozel. "
            f"Bulunan cumle sayisi: {len(sentences)}. "
            "Kaynak metni degismisse testi tahmin ederek surdurmeyelim."
        )

    expected_fragments = {
        2: "AT causes an improvement in two measures of price efficiency",
        3: "computers taking liquidity",
        4: "higher adverse selection costs on slower traders",
        5: "algorithmic provision of liquidity",
        7: "does not appear to cause a degradation in market quality",
    }

    for number, fragment in expected_fragments.items():
        if fragment.casefold() not in sentences[number - 1].casefold():
            raise RuntimeError(
                f"Kaynak cumlesi {number} beklenen metinle uyusmuyor. "
                "Testin cevap anahtarini otomatik tahmin etmiyoruz."
            )

    return title, sentences


def ask_ollama(numbered_sentences, claim):
    system_prompt = """
Sen yalnizca verilen kaynak cumlelerine gore bir iddiayi denetliyorsun.

Etiketler:
CONSISTENT: Iddia kaynak cumlesi tarafindan destekleniyor.
CONTRADICTION: Kaynak, iddianin tersini veya onunla celisen bir durumu soyluyor.
UNSUPPORTED: Kaynak iddiayi ne destekliyor ne de acikca celistiriyor.

Ozellikle dikkat et:
- "taking liquidity" = likidite ALMAK.
- "provision of liquidity" = likidite SAGLAMAK.
- Arbitraj firsatlarindaki azalma ile getirilerin otokorelasyonundaki
  azalmayi birbirine karistirma.
- Kaynaktaki "at least not on average" sinirini koru.
- Kaynakta olmayan sayi, basari orani veya yatirim tavsiyesi uydurma.

Yalnizca JSON dondur:
{
  "verdict": "CONSISTENT veya CONTRADICTION veya UNSUPPORTED",
  "sentence_id": 1,
  "reason_tr": "Kisa gerekce"
}

CONSISTENT ve CONTRADICTION icin en dogrudan kanit cumlesinin
gosterilen numarasini sec.
UNSUPPORTED icin sentence_id null olsun.
Cumle numaralarini sen uydurma; yalnizca listede olanlari kullan.
"""

    user_prompt = (
        "KAYNAK CUMLELERI:\n"
        + numbered_sentences
        + "\n\nDENETLENECEK IDDIA:\n"
        + claim
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
            raw_response = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(
            "Ollama yanit vermedi. Ollama'nin calistigini ve "
            f"{MODEL} modelinin yuklu oldugunu kontrol et. Ayrinti: {exc}"
        ) from exc

    content = raw_response.get("message", {}).get("content", "")

    try:
        result = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(
            f"Model gecerli JSON dondurmedi:\n{content}"
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError(f"Beklenmeyen model yaniti: {result!r}")

    return result


def main():
    title, sentences = load_source()

    # Beklenen cumle numaralari ORIJINAL kaynak sirasina aittir.
    # "Likidite saglama arbitraji azaltir" iddiasi yanlistir:
    # kaynak cumle 3, arbitraj icin likidite ALMAYI bildirir.
    tests = [
        {
            "name": "Arbitraj - likidite alma",
            "claim": (
                "Yazarlara gore arbitraj firsatlarindaki azalma "
                "esas olarak bilgisayarlarin likidite almasiyla iliskilidir."
            ),
            "verdict": "CONSISTENT",
            "original_sentence": 3,
        },
        {
            "name": "Arbitraj - likidite saglama karisikligi",
            "claim": (
                "Yazarlara gore arbitraj firsatlarindaki azalma "
                "esas olarak bilgisayarlarin likidite saglamasiyla iliskilidir."
            ),
            "verdict": "CONTRADICTION",
            "original_sentence": 3,
        },
        {
            "name": "Otokorelasyon - likidite saglama",
            "claim": (
                "Yazarlara gore getirilerin otokorelasyonundaki azalma "
                "daha cok algoritmik likidite saglanmasindan kaynaklanir."
            ),
            "verdict": "CONSISTENT",
            "original_sentence": 5,
        },
        {
            "name": "Otokorelasyon - likidite alma karisikligi",
            "claim": (
                "Yazarlara gore getirilerin otokorelasyonundaki azalma "
                "daha cok bilgisayarlarin likidite almasindan kaynaklanir."
            ),
            "verdict": "CONTRADICTION",
            "original_sentence": 5,
        },
        {
            "name": "Uydurma basari yuzdesi",
            "claim": (
                "Arastirma, algoritmik islemlerin tahmin basarisini "
                "yuzde 95 olarak olcmustur."
            ),
            "verdict": "UNSUPPORTED",
            "original_sentence": None,
        },
        {
            "name": "Ortalama piyasa kalitesi",
            "claim": (
                "Yazarlar, algoritmik islem stratejileri arasindaki "
                "korelasyonun ortalama piyasa kalitesini bozdugunu bulmustur."
            ),
            "verdict": "CONTRADICTION",
            "original_sentence": 7,
        },
    ]

    print("PERSONAL AI - LIKIDITE AYRIMI / DUZELTILMIS TEST")
    print("=" * 64)
    print("Veritabani: yalnizca okuma | Strateji ve islem: kapali")
    print(f"Kaynak ID: {SOURCE_ID} | Bilgi kaydi ID: {KNOWLEDGE_ID}")
    print(f"Baslik: {title}")
    print(f"Model: {MODEL}")
    print()

    print("ORIJINAL KAYNAK CUMLELERI")
    print("-" * 64)
    for number, sentence in enumerate(sentences, start=1):
        print(f"{number}. {sentence}")

    passed = 0
    total = 0

    for round_number, seed in enumerate(SEEDS, start=1):
        shuffled = list(enumerate(sentences, start=1))
        random.Random(seed).shuffle(shuffled)

        # Gosterilen yeni numara -> orijinal kaynak numarasi
        mapping = {
            new_number: original_number
            for new_number, (original_number, _) in enumerate(
                shuffled, start=1
            )
        }

        numbered_sentences = "\n".join(
            f"{new_number}. {sentence}"
            for new_number, (_, sentence) in enumerate(
                shuffled, start=1
            )
        )

        print()
        print("=" * 64)
        print(f"TUR {round_number} | Karistirma tohumu: {seed}")
        print(f"Yeni numara -> orijinal numara: {mapping}")

        for test_number, test in enumerate(tests, start=1):
            total += 1
            print()
            print(f"TEST {round_number}.{test_number}: {test['name']}")
            print("-" * 64)
            print(f"Iddia: {test['claim']}")
            print(
                f"Beklenen: {test['verdict']} | "
                f"orijinal cumle={test['original_sentence']}"
            )
            print("Ollama yaniti bekleniyor...")

            try:
                result = ask_ollama(
                    numbered_sentences,
                    test["claim"],
                )
            except RuntimeError as exc:
                print(f"SONUC: HATA - {exc}")
                continue

            print("HAM MODEL YANITI:")
            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            verdict = result.get("verdict")
            selected_new = result.get("sentence_id")

            # bool, Python'da int alt turudur; True/False'u
            # yanlislikla cumle numarasi kabul etmeyelim.
            if type(selected_new) is int:
                selected_original = mapping.get(selected_new)
            else:
                selected_original = None

            verdict_ok = verdict == test["verdict"]

            if test["original_sentence"] is None:
                sentence_ok = selected_new is None
            else:
                sentence_ok = (
                    type(selected_new) is int
                    and selected_original
                    == test["original_sentence"]
                )

            if verdict_ok and sentence_ok:
                passed += 1
                print("SONUC: GECTI")
            else:
                print("SONUC: KALDI")
                if not verdict_ok:
                    print(
                        "Karar uyusmadi: "
                        f"beklenen={test['verdict']}, gelen={verdict!r}"
                    )
                if not sentence_ok:
                    print(
                        "Kanit cumlesi uyusmadi: "
                        f"beklenen orijinal={test['original_sentence']}, "
                        f"secilen yeni={selected_new!r}, "
                        f"secilen orijinal={selected_original!r}"
                    )

    print()
    print("=" * 64)
    print(f"GENEL SONUC: {passed}/{total} kontrol gecti.")
    print(
        "NOT: Bu, tek bir yazar ozeti uzerindeki dar kapsamli "
        "bir testtir; bilimsel dogrulama veya genel guvenilirlik "
        "kaniti degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji olusturulmadi veya degistirilmedi.")
    print("Alim-satim islemi tetiklenmedi.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"DURDURULDU: {error}")