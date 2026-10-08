import json

import out_of_scope_test as previous
import three_stage_relation_test as three


# Önceki deneyin kullandığı istemleri değiştirmemek için
# mevcut çıkarım fonksiyonlarını aynen çağırıyoruz.
#
# ask_ollama fonksiyonunu yalnızca bu dosyanın çalışması
# sırasında geçici olarak sarıyoruz. Böylece ham JSON'u
# görebiliyoruz. Eski Python dosyaları değiştirilmez.

original_ask_ollama = three.base.ask_ollama

call_number = 0


def diagnostic_ask_ollama(system_prompt, text):
    global call_number

    call_number += 1

    stages = {
        1: "HEDEF DEGISKEN",
        2: "ACIKLAYICI DEGISKEN",
        0: "ILISKI TURU VE YON",
    }

    stage = stages[call_number % 3]

    print(f"\n  ASAMA {call_number % 3 or 3}: {stage}")

    try:
        raw = original_ask_ollama(system_prompt, text)
    except Exception as error:
        print("  MODEL / JSON HATASI:", repr(error))
        raise

    print(
        "  HAM MODEL YANITI:",
        json.dumps(raw, ensure_ascii=False, sort_keys=True),
    )

    return raw


def diagnose_result(result):
    if result is None:
        print(
            "  SONUC: null. Yukaridaki asamalardan biri "
            "gecersiz cikti uretmis olabilir."
        )
        return

    unknown_fields = [
        name
        for name, value in result.items()
        if value == "UNKNOWN"
    ]

    if unknown_fields:
        print(
            "  SONUC: Belirsiz alanlar:",
            ", ".join(unknown_fields),
        )
    else:
        print(
            "  UYARI: Tum alanlar dolu. "
            "Bu, etiketlerin dogru oldugu anlamina gelmez."
        )


def main():
    # Eski deneydeki kaynak kaydini salt okunur kontrol eder.
    title = previous.load_source()

    print("PERSONAL AI - KAPSAM DISI HATA TESHISI")
    print("=" * 60)
    print("Kaynak:", title)
    print("Model:", three.base.MODEL)
    print("Mevcut istemler: degistirilmedi")
    print("Veritabani: sadece okuma")
    print("Strateji ve alim-satim: kapali")

    # Geçici sarmalayıcı: yalnızca bu Python sürecinde geçerli.
    three.base.ask_ollama = diagnostic_ask_ollama

    for index, (name, text) in enumerate(
        previous.TESTS,
        start=1,
    ):
        global call_number
        call_number = 0

        print("\n" + "-" * 60)
        print(f"TEST {index}: {name}")
        print("Metin:", text)

        try:
            result = three.extract_three_stage(text)
        except Exception as error:
            print("  CIKARIM DURDU:", repr(error))
            result = None

        print(
            "\n  BIRLESIK CIKTI:",
            json.dumps(result, ensure_ascii=False),
        )

        diagnose_result(result)

        # Bu dosya ilişki kararı üretmez.
        print("  KARAR: URETILMEDI - SADECE TESHIS")

    print("\n" + "=" * 60)
    print("Teshis tamamlandi.")
    print("Bu calisma model basarisi puanlamasi degildir.")
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()