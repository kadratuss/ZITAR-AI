import real_model_v2_bridge_test as bridge
import bridge_v4_test as v4


TEXT = (
    "Researchers found that long-term Bitcoin volatility "
    "is negatively affected by S&P 500 realized volatility."
)

REPEATS = 5


def main():
    print("PERSONAL AI - TEK CUMLE / 5 GERCEK OLLAMA TEKRARI")
    print("=" * 60)
    print("Metin:", TEXT)
    print("Beklenen karar: READY")
    print("V4 kodunda degisiklik: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    ready_count = 0
    review_count = 0
    relation_counts = {}

    for number in range(1, REPEATS + 1):
        print("\n" + "-" * 60)
        print(f"TEKRAR {number}/{REPEATS}")

        # Her turda gercek Ollama yeniden cagrilir.
        model_result = bridge.e2e.extract_real_model(TEXT)
        result = v4.check_v4(TEXT, model_result)

        extraction = model_result.get("extraction") or {}
        relation = extraction.get("relation", "YOK")
        relation_counts[relation] = relation_counts.get(relation, 0) + 1

        if result["status"] == "READY":
            ready_count += 1
        else:
            review_count += 1

        print("Model iliski etiketi:", relation)
        print("Ham model cevaplari:", model_result["raw"])
        print("Ilk dort kapi:", model_result["status"])
        print("Ilk kapi gerekceleri:", model_result["reasons"])
        print("V4 son karar:", result["status"])
        print("Karar asamasi:", result["stage"])
        print("Son gerekceler:", result["reasons"])

    print("\n" + "=" * 60)
    print("TEKRAR SAYISI:", REPEATS)
    print("Iliski etiketi dagilimi:", relation_counts)
    print("READY:", ready_count)
    print("REVIEW:", review_count)
    print(
        "NOT: Tek cumlenin tekrari bagimsiz dogrulama "
        "veya genel hata orani olcumu degildir."
    )
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()