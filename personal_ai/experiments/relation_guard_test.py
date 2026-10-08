# relation_guard_test.py
# Bagimsiz kavram-iliski kontrolu.
# Veritabani, Ollama, strateji ve alim-satim baglantisi YOK.

from dataclasses import dataclass


@dataclass(frozen=True)
class Relation:
    subject: str
    action: str
    mechanism: str


# Kaynak 14'teki yazar ozetinin 3. ve 5. cumlelerinden
# elle cikarilmis iliskiler.
SOURCE_RELATIONS = {
    3: Relation(
        subject="arbitraj_firsatlarinda_azalma",
        action="esas_olarak_iliskili",
        mechanism="likidite_alma",
    ),
    5: Relation(
        subject="getiri_otokorelasyonunda_azalma",
        action="daha_cok_kaynaklanir",
        mechanism="likidite_saglama",
    ),
}


def check_relation(claim: Relation):
    """
    CONSISTENT: Ayni konu, iliski ve mekanizma kaynakta var.
    CONTRADICTION: Ayni konu ve iliski var, mekanizma ters.
    REVIEW: Bu dar kural seti karar vermeye yeterli degil.
    """
    matching = [
        (sentence_id, source)
        for sentence_id, source in SOURCE_RELATIONS.items()
        if source.subject == claim.subject
        and source.action == claim.action
    ]

    if not matching:
        return "REVIEW", None

    for sentence_id, source in matching:
        if source.mechanism == claim.mechanism:
            return "CONSISTENT", sentence_id

    # Bu deneyde likidite alma/saglama birbirinin
    # yerine gecmeyen iki farkli mekanizma.
    mechanisms = {source.mechanism for _, source in matching}

    if (
        claim.mechanism in {"likidite_alma", "likidite_saglama"}
        and mechanisms <= {"likidite_alma", "likidite_saglama"}
    ):
        return "CONTRADICTION", matching[0][0]

    return "REVIEW", None


TESTS = [
    (
        "Arbitraj - likidite alma",
        Relation(
            "arbitraj_firsatlarinda_azalma",
            "esas_olarak_iliskili",
            "likidite_alma",
        ),
        "CONSISTENT",
        3,
    ),
    (
        "Arbitraj - likidite saglama karisikligi",
        Relation(
            "arbitraj_firsatlarinda_azalma",
            "esas_olarak_iliskili",
            "likidite_saglama",
        ),
        "CONTRADICTION",
        3,
    ),
    (
        "Otokorelasyon - likidite saglama",
        Relation(
            "getiri_otokorelasyonunda_azalma",
            "daha_cok_kaynaklanir",
            "likidite_saglama",
        ),
        "CONSISTENT",
        5,
    ),
    (
        "Otokorelasyon - likidite alma karisikligi",
        Relation(
            "getiri_otokorelasyonunda_azalma",
            "daha_cok_kaynaklanir",
            "likidite_alma",
        ),
        "CONTRADICTION",
        5,
    ),
    (
        "Kaynakta olmayan Bitcoin tavsiyesi",
        Relation(
            "bitcoin",
            "satin_alma_tavsiyesi",
            "bugun",
        ),
        "REVIEW",
        None,
    ),
]


def main():
    print("PERSONAL AI - BAGIMSIZ ILISKI KONTROLU")
    print("=" * 55)
    print("Veritabani: kullanilmiyor | Strateji ve islem: kapali")
    print("Iliskiler bu deney icin elle tanimlandi.\n")

    passed = 0

    for number, (name, claim, expected, expected_id) in enumerate(
        TESTS, start=1
    ):
        verdict, sentence_id = check_relation(claim)
        ok = verdict == expected and sentence_id == expected_id
        passed += int(ok)

        print(f"TEST {number}: {name}")
        print(f"Beklenen: {expected} | cumle={expected_id}")
        print(f"Gelen:    {verdict} | cumle={sentence_id}")
        print("SONUC:", "GECTI" if ok else "KALDI")
        print("-" * 55)

    print(f"GENEL SONUC: {passed}/{len(TESTS)} kontrol gecti.")
    print("Bu test, modelin iliskileri dogru cikardigini kanitlamaz.")
    print("Veritabanina yazilmadi; alim-satim tetiklenmedi.")


if __name__ == "__main__":
    main()