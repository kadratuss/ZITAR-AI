
import json
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

SOURCE_ID = 9
MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


def get_source():
    backend = Path(__file__).resolve().parents[2]
    db = backend / "research.db"

    if not db.is_file():
        raise RuntimeError(f"Veritabani bulunamadi: {db}")

    connection = sqlite3.connect(
        f"file:{db.as_posix()}?mode=ro",
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
            f"Kaynak icin {len(rows)} bilgi kaydi bulundu; "
            "yanlis metni secmemek icin durduruldu."
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
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+", content.strip())
        if item.strip()
    ]

    if not sentences:
        raise RuntimeError("Kaynak cumleleri bulunamadi.")

    return source[0], knowledge_id, sentences


def ollama_json(prompt):
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
            f"Ollama gecersiz JSON dondu: {raw[:300]}"
        ) from error

    if not isinstance(result, dict):
        raise RuntimeError("Ollama JSON nesnesi donmedi.")

    return result


def generate_explanation(title, sentences):
    numbered = "\n".join(
        f"{number}. {sentence}"
        for number, sentence in enumerate(sentences, 1)
    )

    prompt = f"""
Asagidaki metin bir makalenin yalnizca yazar ozetidir.
Tam metni okudugunu iddia etme.

Tek bir cumle sec ve yalnizca o cumleyi Turkce acikla.
Kaynakta olmayan sayi, basari orani, deney sonucu,
kripto para yorumu veya alim-satim tavsiyesi ekleme.

Yalnizca su JSON nesnesini dondur:
{{
  "sentence_id": 1,
  "quote": "Secilen cumlenin birebir TAMAMI",
  "explanation_tr": "Dar kapsamli Turkce aciklama",
  "limitations_tr": "Bu bilginin yalnizca ozete dayandigi sinir"
}}

Baslik: {title}

Kaynak cumleleri:
{numbered}
""".strip()

    return ollama_json(prompt)


def quote_check(result, sentences):
    required = (
        "sentence_id",
        "quote",
        "explanation_tr",
        "limitations_tr",
    )

    if any(field not in result for field in required):
        return None, "JSON alanlari eksik."

    sentence_id = result["sentence_id"]

    if type(sentence_id) is not int:
        return None, "Cumle numarasi tam sayi degil."

    if not 1 <= sentence_id <= len(sentences):
        return None, "Cumle numarasi kaynakta yok."

    for field in (
        "quote",
        "explanation_tr",
        "limitations_tr",
    ):
        value = result[field]
        if not isinstance(value, str) or not value.strip():
            return None, f"{field} bos veya metin degil."

    original = sentences[sentence_id - 1]

    if result["quote"] != original:
        return None, "Alinti kaynak cumlesiyle birebir eslesmiyor."

    return original, None


def obvious_risk_check(explanation):
    text = explanation.casefold()

    trade_phrases = (
        "bitcoin al",
        "bitcoin sat",
        "btc al",
        "btc sat",
        "long aç",
        "short aç",
        "alım sinyali",
        "satım sinyali",
        "buy bitcoin",
        "sell bitcoin",
        "buy signal",
        "sell signal",
    )

    if any(phrase in text for phrase in trade_phrases):
        return "Acik islem yonlendirmesi tespit edildi."

    return None


def judge_meaning(source_sentence, explanation):
    prompt = f"""
Gorevin, bir aciklamanin kaynak cumlesine sadik
kalip kalmadigini ihtiyatli bicimde incelemektir.

Yalnizca verilen TEK kaynak cumlesini kullan.
Makalenin tam metnini bildigini varsayma.
Kaynakta olmayan deney, sayi, basari orani,
kripto getirisi veya alim-satim sonucu eklenmis mi bak.

Kurallar:
- Aciklama kaynakla celisiyorsa: CONTRADICTION
- Aciklama kaynakta olmayan somut iddia ekliyorsa:
  UNSUPPORTED
- Aciklama kaynakla uyumlu gorunuyor ama anlam
  esdegerligini kesin belirleyemiyorsan: UNCERTAIN
- Aciklama yalnizca kaynak cumlesini dar kapsamda
  ifade ediyorsa: CONSISTENT
- CONSISTENT bilimsel dogrulama anlamina gelmez.

Yalnizca su JSON nesnesini dondur:
{{
  "verdict": "CONSISTENT",
  "reason_tr": "Kisa ve somut gerekce",
  "unsupported_claim_tr": null
}}

verdict yalnizca CONSISTENT, CONTRADICTION,
UNSUPPORTED veya UNCERTAIN olabilir.
Desteklenmeyen iddia yoksa unsupported_claim_tr null olsun.

KAYNAK CUMLESI:
{source_sentence}

KONTROL EDILECEK ACIKLAMA:
{explanation}
""".strip()

    return ollama_json(prompt)


def evaluate(result, sentences):
    source_sentence, quote_error = quote_check(
        result, sentences
    )

    if quote_error:
        return {
            "status": "REJECTED",
            "reason": quote_error,
            "judge": None,
        }

    explanation = result["explanation_tr"]

    obvious_risk = obvious_risk_check(explanation)

    if obvious_risk:
        return {
            "status": "REJECTED",
            "reason": obvious_risk,
            "judge": None,
        }

    judge = judge_meaning(
        source_sentence, explanation
    )

    verdict = judge.get("verdict")
    reason = judge.get("reason_tr")

    if verdict not in (
        "CONSISTENT",
        "CONTRADICTION",
        "UNSUPPORTED",
        "UNCERTAIN",
    ):
        return {
            "status": "REVIEW_REQUIRED",
            "reason": "Anlam denetleyicisi gecerli karar donmedi.",
            "judge": judge,
        }

    if not isinstance(reason, str) or not reason.strip():
        return {
            "status": "REVIEW_REQUIRED",
            "reason": "Anlam denetleyicisi gerekce vermedi.",
            "judge": judge,
        }

    if verdict in ("CONTRADICTION", "UNSUPPORTED"):
        status = "REJECTED"
    else:
        status = "REVIEW_REQUIRED"

    return {
        "status": status,
        "reason": (
            f"Modelin anlam kontrolu: {verdict}. "
            f"Gerekce: {reason}"
        ),
        "judge": judge,
    }


def main():
    print("PERSONAL AI - CANLI ANLAM KONTROLU")
    print("=" * 45)

    title, knowledge_id, sentences = get_source()

    print(f"Kaynak ID: {SOURCE_ID}")
    print(f"Baslik: {title}")
    print(f"Bilgi kaydi ID: {knowledge_id}")
    print(f"Cumle sayisi: {len(sentences)}")
    print(f"Model: {MODEL}")

    print("\n1/2 - Aciklama uretiliyor...")
    generated = generate_explanation(
        title, sentences
    )

    print("\nURETILEN ACIKLAMA")
    print(
        json.dumps(
            generated,
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n2/2 - Kanit ve anlam kontrolu...")
    evaluation = evaluate(
        generated, sentences
    )

    print("\nANLAM DENETLEYICISI")
    print("-" * 45)
    print(
        json.dumps(
            evaluation["judge"],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\nNIHAI KAPI")
    print("-" * 45)
    print(f"Durum: {evaluation['status']}")
    print(f"Gerekce: {evaluation['reason']}")

    print("\nVeritabanina yazilmadi.")
    print("Strateji olusturulmadi veya degistirilmedi.")
    print("Alim-satim islemi tetiklenmedi.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nDURDURULDU: {error}")
        print("Veritabanina yazilmadi.")
        print("Alim-satim islemi tetiklenmedi.")