from pathlib import Path
import json

BASE = Path(__file__).resolve().parent
JOURNAL = BASE / "zitar_core_learning_journal_v1.jsonl"
OUT = BASE / "zitar_core_learning_journal_compatibility_test_v1.json"

V1 = "ZITAR_CORE_LEARNING_JOURNAL_V1"
V2 = "ZITAR_CORE_LEARNING_JOURNAL_V2"


def load():
    if not JOURNAL.exists():
        return []
    return [
        json.loads(line)
        for line in JOURNAL.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def verify_chain(rows):
    errors = []
    prev = None

    for i, r in enumerate(rows, 1):
        schema = r.get("schema")

        if schema == V1:
            link = r.get("previous_sha256")

        elif schema == V2:
            link = r.get("previous_record_sha256")

        else:
            errors.append(f"ROW_{i}:UNEXPECTED_SCHEMA")
            continue

        if link != prev:
            errors.append(f"ROW_{i}:PREVIOUS_SHA256_MISMATCH")

        current = r.get("record_sha256")

        if not current:
            errors.append(f"ROW_{i}:MISSING_RECORD_SHA256")
            continue

        prev = current

    return errors


def main():
    rows = load()
    errors = verify_chain(rows)

    schemas = [r.get("schema") for r in rows]

    tests = {
        "journal_exists": JOURNAL.exists(),
        "three_or_more_records": len(rows) >= 3,
        "supported_schemas_only": all(s in {V1, V2} for s in schemas),
        "mixed_chain_valid": len(errors) == 0,
        "schema_specific_previous_field_valid": all(
            (
                r.get("schema") == V1
                and "previous_sha256" in r
            )
            or
            (
                r.get("schema") == V2
                and "previous_record_sha256" in r
            )
            for r in rows
        ),
    }

    passed = sum(int(v) for v in tests.values())

    OUT.write_text(
        json.dumps(
            {
                "schema": "ZITAR_CORE_LEARNING_JOURNAL_COMPATIBILITY_TEST_V1_1",
                "records": len(rows),
                "v1_records": schemas.count(V1),
                "v2_records": schemas.count(V2),
                "errors": errors,
                "tests": [
                    {"name": k, "pass": bool(v)}
                    for k, v in tests.items()
                ],
                "passed": passed,
                "total": len(tests),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("ZITAR LEARNING JOURNAL MIXED COMPATIBILITY V1.1")
    print("READ ONLY • V1 + V2 • HASH CHAIN AWARE • NO MEMORY WRITE")
    print("records:", len(rows))
    print("V1:", schemas.count(V1))
    print("V2:", schemas.count(V2))
    print("errors:", len(errors))

    for e in errors:
        print(" ", e)

    print(f"validation: {passed}/{len(tests)}")
    print("output:", OUT)
    print("STATUS:", "PASS" if passed == len(tests) else "FAIL")


if __name__ == "__main__":
    main()
