import json
import sqlite3
from pathlib import Path

import three_stage_relation_test as three


DB = Path(__file__).resolve().parents[2] / "research.db"

# Bu ifadeler, daha once paylastiginiz 15 numarali
# kaynagin yazar ozetinden alinmistir.
TESTS = [
    (
        "Algoritmik islem ve fiyat farki",
        "For large stocks in particular, AT narrows spreads.",
    ),
    (
        "Algoritmik islem ve ters secim",
        "For large stocks in particular, AT reduces adverse selection.",
    ),
    (
        "Algoritmik islem ve likidite",
        "The findings indicate that AT improves liquidity.",
    ),
    (
        "Turkce iddia: fiyat farki",
        "Algoritmik islemler buyuk hisselerde alis-satis "
        "fiyat farkini daraltiyor.",
    ),
    (
        "Turkce iddia: likidite",
        "Algoritmik islemler likiditeyi iyilestiriyor.",
    ),
]


def load_source():
    connection = sqlite3.connect(
        DB.resolve().as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        row = connection.execute(
            """
            SELECT s.title, k.content
            FROM sources s
            JOIN knowledge k ON k.source_id = s.id
            WHERE s.id = 15 AND k.id = 4
            """
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise RuntimeError("Kaynak 15 / bilgi 4 bulunamadi.")

    title, content = row

    required = [
        "AT narrows spreads",
        "reduces adverse selection",
        "AT improves liquidity",
    ]

    if not all(phrase in content for phrase in required):
        raise RuntimeError(
            "Kaynak metni beklenen ozetle uyusmuyor."
        )

    return title


def main():
    title = load_source()

    print("PERSONAL AI - KAPSAM DISI KAYNAK TESTI")
    print("=" * 60)
    print("Kaynak:", title)
    print("Model:", three.base.MODEL)
    print("Uc asamali istemler: degistirilmedi")
    print("Veritabani: sadece okuma")
    print("Strateji ve alim-satim: kapali")

    unsupported_labels = 0
    incomplete_outputs = 0

    for index, (name, text) in enumerate(TESTS, start=1):
        print("\n" + "-" * 60)
        print(f"TEST {index}: {name}")
        print("Metin:", text)

        try:
            extracted = three.extract_three_stage(text)
        except Exception as error:
            print("Model hatasi:", error)
            extracted = None

        print(
            "Model cikarimi:",
            json.dumps(extracted, ensure_ascii=False),
        )

        if extracted is None or "UNKNOWN" in extracted.values():
            incomplete_outputs += 1
            print("GOZLEM: Eksik veya belirsiz alan var.")
        else:
            unsupported_labels += 1
            print(
                "UYARI: Model kapsam disi metne mevcut "
                "etiketlerden tam bir dörtlü atadi."
            )

        # Yeni kaynagin degiskenleri mevcut semada yok.
        # Bu nedenle bu deneyde hicbir iddia onaylanmaz.
        print("Uygulama karari: REVIEW")

    print("\n" + "=" * 60)
    print("SONUCLAR")
    print("Toplam metin:", len(TESTS))
    print("Eksik/belirsiz cikarim:", incomplete_outputs)
    print(
        "Kapsam disi metne tam etiket atama:",
        unsupported_labels,
    )
    print("Otomatik onay: 0")
    print(
        "\nNOT: Otomatik onayin sifir olmasi, "
        "modelin yeni kaynagi anladigini kanitlamaz."
    )
    print(
        "Bu test kapsam disi davranisi gozlemler; "
        "yeni kaynak icin iliski dogrulama testi degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, sqlite3.Error) as error:
        print("DURDURULDU:", error)