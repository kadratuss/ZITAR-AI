import json

import out_of_scope_test as outside
import three_stage_relation_test as three


base = three.base

# Modelin uc asamada kullanmasina izin verilen etiketler.
SCHEMA = {
    "target": base.TARGETS,
    "variable": three.VARIABLES,
    "relation": three.RELATIONS,
    "direction": three.DIRECTIONS,
}


def show(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


def check_field(field, value):
    """Tek bir alani kontrol et; hatayi gizleme."""

    if value is None:
        return f"EKSIK_ALAN:{field}"

    if not isinstance(value, str):
        return f"GECERSIZ_TIP:{field}"

    if value not in SCHEMA[field]:
        return f"IZINSIZ_ETIKET:{field}={value}"

    if value == "UNKNOWN":
        return f"BELIRSIZ_ALAN:{field}"

    return None


def extract_with_gate(text):
    """
    Uc asamanin ham cevaplarini ayri ayri kontrol eder.
    Bir asama basarisizsa digerlerini de kaydeder;
    ancak otomatik onaya izin vermez.
    """

    stages = [
        (
            "HEDEF",
            {"target"},
            """Identify only the TARGET variable in the text.

Return ONLY JSON:
{"target": "..."}

Allowed values:
LONG_TERM_BTC_VOL
BITCOIN_PRICE
UNKNOWN

Volatility and price are different quantities.
Use UNKNOWN if the target is unclear.
Do not evaluate the claim or provide trading advice.""",
        ),
        (
            "ACIKLAYICI_DEGISKEN",
            {"variable"},
            """Identify ONLY the explanatory variable in the text.

Return ONLY JSON with exactly one field:
{"variable": "..."}

Allowed values:
SP500_REALIZED_VOL
SP500_VOL_RISK_PREMIUM
BALTIC_DRY_INDEX
BITCOIN_PRICE
UNKNOWN

The explanatory variable is the factor described
as affecting or being related to another quantity.

Distinguish it from the target variable.
Use UNKNOWN when unclear.
Do not judge whether the claim is true.""",
        ),
        (
            "ILISKI_VE_YON",
            {"relation", "direction"},
            """Extract ONLY the relation type and direction
from the supplied text.

Return ONLY JSON with exactly these fields:
{
  "relation": "...",
  "direction": "..."
}

Allowed relation values:
EFFECT
ASSOCIATION
UNKNOWN

Allowed direction values:
POSITIVE
NEGATIVE
UNKNOWN

Distinguish an effect from an association.
Do not infer causation from association.
Use UNKNOWN if a field is unclear.
Do not judge whether the claim is true.""",
        ),
    ]

    combined = {}
    reasons = []

    for stage_name, expected_keys, prompt in stages:
        try:
            raw = base.ask_ollama(prompt.strip(), text)
        except Exception as error:
            print(f"  {stage_name} HATASI: {repr(error)}")
            reasons.append(f"MODEL_HATASI:{stage_name}")
            continue

        print(f"  {stage_name} HAM: {show(raw)}")

        if not isinstance(raw, dict):
            reasons.append(f"GECERSIZ_JSON_YAPISI:{stage_name}")
            continue

        if set(raw) != expected_keys:
            reasons.append(f"EKSIK_VEYA_FAZLA_ANAHTAR:{stage_name}")
            continue

        for field in expected_keys:
            value = raw[field]
            combined[field] = value

            problem = check_field(field, value)

            if problem is not None:
                reasons.append(problem)

    if set(combined) != set(SCHEMA):
        reasons.append("TAMAMLANMAMIS_CIKARIM")

    if reasons:
        return {
            "status": "REVIEW",
            "reasons": reasons,
            "extraction": combined,
        }

    return {
        "status": "READY",
        "reasons": [],
        "extraction": combined,
    }


def compare(source_result, claim_result):
    """Kapsam kapisindan gecmeyen veriyi karsilastirma."""

    if source_result["status"] != "READY":
        return "REVIEW", "KAYNAK_KAPSAM_KAPISINDAN_GECMEDI"

    if claim_result["status"] != "READY":
        return "REVIEW", "IDDIA_KAPSAM_KAPISINDAN_GECMEDI"

    verdict = base.decide(
        source_result["extraction"],
        claim_result["extraction"],
    )

    return verdict, "KARSILASTIRMA_YAPILDI"


def main():
    print("PERSONAL AI - GERCEK KAPSAM KAPISI")
    print("=" * 60)
    print("Model:", base.MODEL)
    print("Veritabani: sadece okuma")
    print("Strateji ve alim-satim: kapali")

    # Onceki deneyde elle kontrol edilmis kaynak
    # cumlesini yeniden okuyoruz.
    sentences = base.load_sentences()
    source_text = sentences[2]

    print("\n" + "=" * 60)
    print("KONTROL 1: KAPSAM ICI KAYNAK")
    print(source_text)

    source_result = extract_with_gate(source_text)
    print("Kapi sonucu:", show(source_result))

    # Kaynak cikarimi onceki sabit cevapla
    # uyusmuyorsa karsilastirmaya izin verme.
    if (
        source_result["status"] == "READY"
        and source_result["extraction"] != base.SOURCE_GOLD[3]
    ):
        source_result = {
            "status": "REVIEW",
            "reasons": ["KAYNAK_CEVAP_ANAHTARIYLA_UYUSMUYOR"],
            "extraction": source_result["extraction"],
        }
        print("Kaynak kontrolu:", show(source_result))

    print("\n" + "=" * 60)
    print("KONTROL 2: KAPSAM ICI IDDIA")

    claim_text = base.TESTS[0][1]
    print(claim_text)

    claim_result = extract_with_gate(claim_text)
    print("Kapi sonucu:", show(claim_result))

    verdict, reason = compare(source_result, claim_result)

    print("Python karari:", verdict)
    print("Karar gerekcesi:", reason)

    print("\n" + "=" * 60)
    print("KONTROL 3: KAPSAM DISI METINLER")

    # Kaynak 15'in kaydi salt okunur kontrol edilir.
    title = outside.load_source()
    print("Kaynak:", title)

    review_count = 0
    ready_count = 0

    for index, (name, text) in enumerate(
        outside.TESTS,
        start=1,
    ):
        print("\n" + "-" * 60)
        print(f"TEST {index}: {name}")
        print("Metin:", text)

        result = extract_with_gate(text)

        print("Kapi sonucu:", result["status"])
        print("Gerekceler:", show(result["reasons"]))

        if result["status"] == "REVIEW":
            review_count += 1
        else:
            ready_count += 1
            print(
                "UYARI: Kapsam disi metin tam etiketlerle "
                "kapidan gecti. Bu bir guvenlik bulgusudur."
            )

        # Bu bolumde karsilastirilacak onayli bir
        # kaynak iliskisi bulunmadigi icin karar uretilmez.
        print("Iliski karari: URETILMEDI")

    print("\n" + "=" * 60)
    print("SONUCLAR")
    print("Kapsam disi REVIEW:", f"{review_count}/5")
    print("Kapsam disi READY:", ready_count)
    print(
        "NOT: Bu testte kapsam disi metinler icin "
        "otomatik CONSISTENT uretilmedi."
    )
    print(
        "READY, dogruluk kaniti degildir; yalnizca "
        "etiketlerin semaya uygun oldugunu gosterir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print("DURDURULDU:", error)