
import json
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

SOURCE_ID = 9
MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Yalnizca okuma ve test.
# Veritabanina yazma, strateji ve islem yok.


def load_source_sentence():
    backend = Path(__file__).resolve().parents[2]
    database = backend / "research.db"

    if not database.is_file():
        raise RuntimeError(f"Veritabani bulunamadi: {database}")

    connection = sqlite3.connect(
        f"file:{database.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        source = connection.execute(
            "SELECT title FROM sources WHERE id = ?",
            (SOURCE_ID,),
        ).fetchone()

        if source is None:
            raise RuntimeError("Kaynak bulunamadi.")

        rows = connection.execute(
            """
            SELECT id, topic, content
            FROM knowledge
            WHERE source_id = ?
              AND content IS NOT NULL
              AND TRIM(content) != ''
            ORDER BY id
            """,
            (SOURCE_ID,),
        ).fetchall()
    finally:
        connection.close()

    if len(rows) != 1:
        raise RuntimeError(
            f"Kaynak icin {len(rows)} bilgi kaydi var. "
            "Yanlis metni secmemek icin durduruldu."
        )

    knowledge_id, topic, content = rows[0]

    if not any(
        word in (topic or "").casefold()
        for word in ("özet", "ozet", "abstract")
    ):
        raise RuntimeError(
            "Bilgi kaydi yazar ozeti olarak etiketlenmemis."
        )

    sentences = [
        sentence.strip()
        for sentence in re.split(
            r"(?<=[.!?])\s+", content.strip()
        )
        if sentence.strip()
    ]

    # Onceki canli testte incelenen 5. cumle.
    if len(sentences) < 5:
        raise RuntimeError("Beklenen 5. cumle bulunamadi.")

    sentence = sentences[4]

    expected_sentence = (
        "Adaptive parameters are then proposed by "
        "incorporating the nonstationarity of "
        "financial time series into SVM."
    )

    if sentence != expected_sentence:
        raise RuntimeError(
            "Kaynak 5. cumlesi onceki testten farkli. "
            "Yanlis kaynagi sinamamak icin durduruldu."
        )

    return source[0], knowledge_id, sentence


def ask_judge(source_sentence, explanation):
    prompt = f"""
Bir Turkce aciklamayi, yalnizca verilen Ingilizce
kaynak cumlesine gore denetle.

Makalenin tam metnini bildigini varsayma.
Aciklamanin bilimsel olarak kanitlandigini soyleme.

Etiketler:
CONSISTENT: Kaynak cumlesinin dar kapsamli anlami.
CONTRADICTION: Kaynak cumlesinin soylediginin tersi.
UNSUPPORTED: Kaynakta bulunmayan somut iddia,
sayi, basari orani veya alim-satim sonucu.
UNCERTAIN: Yalnizca bu cumleyle karar verilemiyor.

ZORUNLU:
- Gerekcede kaynak cumlesinden ilgili Ingilizce
  ifadeyi aynen alinti yap.
- Aciklamadaki ilgili Turkce ifadeyi de belirt.
- Neden uyumlu veya uyumsuz olduklarini acikla.
- Gerekceyi "Kisa ve somut gerekce" gibi
  sablon bir ifadeyle doldurma.
- Kaynakta olmayan bir iddiayi desteklenmis sayma.

Yalnizca JSON nesnesi dondur:
{{
  "verdict": "UNCERTAIN",
  "source_phrase": "Kaynak cumlesinden birebir ifade",
  "explanation_phrase": "Aciklamadan birebir ifade",
  "reason_tr": "Iki ifadenin iliskisini aciklayan gerekce"
}}

KAYNAK CUMLESI:
{source_sentence}

ACIKLAMA:
{explanation}
""".strip()

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=180
        ) as response:
            envelope = json.loads(
                response.read().decode("utf-8")
            )
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(
            f"Ollama yanit vermedi: {error}"
        ) from error

    raw = envelope.get("response")

    if not isinstance(raw, str):
        raise RuntimeError("Ollama metin yaniti donmedi.")

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Gecersiz JSON: {raw[:300]}"
        ) from error

    if not isinstance(result, dict):
        raise RuntimeError("JSON nesnesi bekleniyordu.")

    return result


def check_response(result, source_sentence, explanation):
    allowed = {
        "CONSISTENT",
        "CONTRADICTION",
        "UNSUPPORTED",
        "UNCERTAIN",
    }

    verdict = result.get("verdict")
    source_phrase = result.get("source_phrase")
    explanation_phrase = result.get("explanation_phrase")
    reason = result.get("reason_tr")

    if verdict not in allowed:
        return False, "Gecersiz karar etiketi."

    values = (
        source_phrase,
        explanation_phrase,
        reason,
    )

    if not all(
        isinstance(value, str) and value.strip()
        for value in values
    ):
        return False, "Alinti veya gerekce eksik."

    if source_phrase not in source_sentence:
        return False, (
            "Kaynak ifadesi kaynak cumlesinde "
            "birebir bulunmuyor."
        )

    if explanation_phrase not in explanation:
        return False, (
            "Aciklama ifadesi aciklamada "
            "birebir bulunmuyor."
        )

    generic_reasons = {
        "kısa ve somut gerekçe",
        "kisa ve somut gerekce",
        "uyumludur",
        "uyumlu",
        "çelişiyor",
        "celisiyor",
        "kaynakta yok",
    }

    if reason.strip().casefold().rstrip(".") in generic_reasons:
        return False, "Gerekce sablon veya yetersiz."

    if len(reason.strip()) < 35:
        return False, "Gerekce cok kisa."

    return True, "Yapisal kontroller gecti."


def main():
    title, knowledge_id, sentence = load_source_sentence()

    cases = [
        {
            "name": "Kaynaga yakin aciklama",
            "explanation": (
                "Calisma, finansal zaman serilerinin "
                "duragan olmama ozelligini SVM'ye dahil "
                "ederek uyarlamali parametreler oneriyor."
            ),
            "expected": "CONSISTENT",
        },
        {
            "name": "Tersine cevrilmis aciklama",
            "explanation": (
                "Calisma, finansal zaman serilerinin "
                "duragan olmama ozelligini SVM'ye "
                "dahil etmeyi reddediyor."
            ),
            "expected": "CONTRADICTION",
        },
        {
            "name": "Uydurma basari orani",
            "explanation": (
                "Calisma, uyarlamali SVM'nin tahmin "
                "basarisini yuzde 95 olarak kanitladi."
            ),
            "expected": "UNSUPPORTED",
        },
        {
            "name": "Kaynak disi islem cikarimi",
            "explanation": (
                "Bu bulgu, bugun Bitcoin almak "
                "gerektigini gosteriyor."
            ),
            "expected": "UNSUPPORTED",
        },
    ]

    print("PERSONAL AI - ANLAM DENETLEYICISI SINAVI")
    print("=" * 50)
    print(f"Kaynak ID: {SOURCE_ID}")
    print(f"Baslik: {title}")
    print(f"Bilgi kaydi ID: {knowledge_id}")
    print(f"Model: {MODEL}")
    print(f"Kaynak cumlesi: {sentence}")

    passed = 0

    for number, case in enumerate(cases, start=1):
        print(f"\nTEST {number}: {case['name']}")
        print("-" * 50)
        print(f"Aciklama: {case['explanation']}")
        print(f"Beklenen: {case['expected']}")
        print("Ollama yaniti bekleniyor...")

        try:
            result = ask_judge(
                sentence, case["explanation"]
            )
            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            structure_ok, structure_reason = check_response(
                result,
                sentence,
                case["explanation"],
            )

            label_ok = (
                result.get("verdict") == case["expected"]
            )

            test_ok = structure_ok and label_ok

            print(f"Etiket dogru: {label_ok}")
            print(f"Yapi kontrolu: {structure_reason}")
            print(
                "TEST SONUCU: "
                + ("GECTI" if test_ok else "KALDI")
            )

            if test_ok:
                passed += 1

        except Exception as error:
            print(f"TEST SONUCU: KALDI - {error}")

    print("\nGENEL SONUC")
    print("=" * 50)
    print(f"{passed}/{len(cases)} test gecti.")

    if passed == len(cases):
        print(
            "Bu dort kurgusal ornekte etiketler ve "
            "yapisal gerekce kontrolleri uyustu."
        )
    else:
        print(
            "Denetleyici bu orneklerde guvenilir "
            "bir sonuc vermedi; otomatik onay yok."
        )

    print(
        "\nNOT: Testleri gecmek anlamsal veya "
        "bilimsel dogrulama degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji olusturulmadi veya degistirilmedi.")
    print("Alim-satim islemi tetiklenmedi.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nDURDURULDU: {error}")
        print("Veritabanina yazilmadi.")
        print("Alim-satim islemi tetiklenmedi.")