
import json
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

SOURCE_ID = 9
MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Bu dosya:
# - Veritabanindan yalnizca okur.
# - Ollama'dan aciklama ister.
# - Veritabanina yazmaz.
# - Strateji veya alim-satim islemi baslatmaz.


def find_database():
    backend = Path(__file__).resolve().parents[2]
    database = backend / "research.db"

    if not database.is_file():
        raise RuntimeError(
            f"research.db bulunamadi: {database}"
        )

    return database


def read_author_abstract(database):
    connection = sqlite3.connect(
        f"file:{database.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        source = connection.execute(
            "SELECT id, title FROM sources WHERE id = ?",
            (SOURCE_ID,),
        ).fetchone()

        if source is None:
            raise RuntimeError(
                f"Kaynak ID {SOURCE_ID} bulunamadi."
            )

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

    # Birden fazla metin varsa yanlislikla baska bir
    # notu makalenin ozeti diye kullanmamak icin dur.
    if len(rows) != 1:
        raise RuntimeError(
            f"Kaynak {SOURCE_ID} icin {len(rows)} bilgi kaydi "
            "bulundu. Tam olarak bir kayit gerekli. "
            "Kaynak secimi belirsiz oldugu icin durduruldu."
        )

    knowledge_id, topic, content = rows[0]

    topic_lower = (topic or "").lower()
    if not any(
        word in topic_lower
        for word in ("özet", "ozet", "abstract")
    ):
        raise RuntimeError(
            f"Bilgi kaydi {knowledge_id} yazar ozeti "
            f"olarak etiketlenmemis: {topic!r}"
        )

    return {
        "source_id": source[0],
        "title": source[1],
        "knowledge_id": knowledge_id,
        "topic": topic,
        "text": content.strip(),
    }


def split_sentences(text):
    # Bu denemede kaynak cumlelerini biz numaralandiriyoruz.
    # Noktali kisaltmalar iceren baska metinlerde daha
    # gelismis bir cumle ayirici gerekebilir.
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if part.strip()
    ]

    if not sentences:
        raise RuntimeError("Kaynak metni cumlelere ayrilamadi.")

    return sentences


def ask_ollama(source, sentences):
    numbered = "\n".join(
        f"{index}. {sentence}"
        for index, sentence in enumerate(sentences, start=1)
    )

    prompt = f"""
Asagidaki metin bir makalenin YAZAR OZETIDIR.
Makalenin tam metnine erisimin yok.

Yalnizca bu ozetten tek bir dar kapsamli bilgi cikar.
Borsa veya kripto para icin alim-satim tavsiyesi verme.
Basari yuzdesi, yayin yili veya baska bir sayi uydurma.
Kaynakta bulunmayan bir deney veya sonuc ekleme.

Yalnizca su JSON nesnesini dondur:
{{
  "sentence_id": 1,
  "quote": "Kaynak cumlesinin eksiksiz ve birebir kopyasi",
  "explanation_tr": "Bu cumlenin Turkce, dar kapsamli aciklamasi",
  "limitations_tr": "Yalnizca ozete dayanmanin siniri"
}}

Kurallar:
- sentence_id secilen cumlenin numarasi olmali.
- quote, o cumlenin TAMAMI olmali; yeniden yazma.
- Aciklamada kaynak cumlesinin disina cikma.
- Makalenin bilimsel sonucunun bagimsiz
  olarak dogrulandigini iddia etme.

Kaynak basligi:
{source["title"]}

Numaralandirilmis yazar ozeti:
{numbered}
""".strip()

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
        },
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
    except urllib.error.URLError as error:
        raise RuntimeError(
            "Ollama'ya ulasilamadi. Ollama'nin "
            f"calistigini kontrol et: {error}"
        ) from error

    raw_response = envelope.get("response")
    if not isinstance(raw_response, str):
        raise RuntimeError(
            "Ollama beklenen metin yanitini dondurmedi."
        )

    try:
        result = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Ollama gecerli JSON dondurmedi. "
            f"Ham yanit: {raw_response[:500]}"
        ) from error

    if not isinstance(result, dict):
        raise RuntimeError(
            "Ollama yaniti JSON nesnesi degil."
        )

    return result


def evidence_gate(result, sentences):
    required = (
        "sentence_id",
        "quote",
        "explanation_tr",
        "limitations_tr",
    )

    missing = [
        field for field in required
        if field not in result
    ]
    if missing:
        return "REJECTED", (
            "JSON alanlari eksik: " + ", ".join(missing)
        )

    sentence_id = result["sentence_id"]
    quote = result["quote"]
    explanation = result["explanation_tr"]
    limitations = result["limitations_tr"]

    if type(sentence_id) is not int:
        return "REJECTED", "Cumle numarasi tam sayi degil."

    if not 1 <= sentence_id <= len(sentences):
        return "REJECTED", "Cumle numarasi kaynakta yok."

    if not all(
        isinstance(value, str) and value.strip()
        for value in (quote, explanation, limitations)
    ):
        return "REJECTED", (
            "Alinti, aciklama veya sinirlar bos."
        )

    original = sentences[sentence_id - 1]

    if quote != original:
        return "REJECTED", (
            "Alinti, secilen kaynak cumlesiyle "
            "birebir ayni degil."
        )

    # Bu kontrol sadece bariz islem yonlendirmelerini
    # yakalamaya yardimci olur; anlamsal guvence degildir.
    forbidden = (
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

    combined = (
        explanation + " " + limitations
    ).casefold()

    if any(phrase in combined for phrase in forbidden):
        return "REJECTED", (
            "Aciklamada kaynak disi islem "
            "yonlendirmesi tespit edildi."
        )

    return "REVIEW_REQUIRED", (
        "Cumle numarasi ve birebir alinti eslesti. "
        "Aciklamanin anlami ve bilimsel iddialar "
        "henüz bagimsiz dogrulanmadi."
    )


def main():
    print("PERSONAL AI - CANLI KANIT KAPISI")
    print("=" * 45)

    database = find_database()
    source = read_author_abstract(database)
    sentences = split_sentences(source["text"])

    print(f"Kaynak ID: {source['source_id']}")
    print(f"Baslik: {source['title']}")
    print(f"Bilgi kaydi ID: {source['knowledge_id']}")
    print(f"Konu: {source['topic']}")
    print(f"Cumle sayisi: {len(sentences)}")
    print(f"Model: {MODEL}")

    print("\nOllama yaniti bekleniyor...")
    result = ask_ollama(source, sentences)

    print("\nMODEL CIKTISI")
    print("-" * 45)
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    status, reason = evidence_gate(
        result, sentences
    )

    print("\nKANIT KAPISI")
    print("-" * 45)
    print(f"Durum: {status}")
    print(f"Gerekce: {reason}")

    sentence_id = result.get("sentence_id")
    if type(sentence_id) is int and (
        1 <= sentence_id <= len(sentences)
    ):
        print(
            "Kaynak cumlesi: "
            + sentences[sentence_id - 1]
        )

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