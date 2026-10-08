import holdout_pair_guard_test as holdout
import scope_gate_adversarial_test as shape
import text_evidence_gate_test as text_gate
import direction_evidence_gate_test as direction_gate
import relation_evidence_gate_test as relation_gate
import multi_relation_guard_test as multi
import pair_binding_refinement_test as refined


def show_result(name, result):
    print(f"{name}: {result['status']}")
    print("  Gerekceler:", result.get("reasons", []))


def main():
    print("PERSONAL AI - HOLDOUT HATA TANISI")
    print("=" * 60)
    print("Model cagrisi: YOK")
    print("Veritabani islemi: YOK")
    print("Strateji ve alim-satim: KAPALI")

    raw = holdout.RAW
    extraction = {
        "target": raw[0]["target"],
        "variable": raw[1]["variable"],
        "relation": raw[2]["relation"],
        "direction": raw[2]["direction"],
    }

    for number in (9, 10):
        case = holdout.CASES[number - 1]
        text = case["text"]

        print("\n" + "-" * 60)
        print(f"TEST {number}: {case['name']}")
        print("Metin:", text)
        print("Beklenen:", case["expected"])

        show_result(
            "1. Bicim",
            shape.check_raw_responses(raw),
        )
        show_result(
            "2. Hedef ve degisken dayanagi",
            text_gate.evidence_gate(text, extraction),
        )
        show_result(
            "3. Yon dayanagi",
            direction_gate.direction_gate(text, extraction),
        )
        show_result(
            "4. Iliski turu dayanagi",
            relation_gate.relation_gate(text, extraction),
        )
        show_result(
            "5. Coklu iliski korumasi",
            multi.guarded_check(text, raw),
        )
        show_result(
            "6. Iyilestirilmis cift baglama",
            refined.refined_check(text, raw),
        )

    print("\n" + "=" * 60)
    print("Bu dosya yalnizca mevcut kapilari tani amaciyla calistirir.")
    print("Veritabanina yazilmadi.")
    print("Strateji degistirilmedi; alim-satim yapilmadi.")


if __name__ == "__main__":
    main()