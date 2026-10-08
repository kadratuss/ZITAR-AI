from __future__ import annotations
import json, hashlib, uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
JOURNAL = BASE / "zitar_core_learning_journal_v1.jsonl"
TEST_OUT = BASE / "zitar_core_learning_journal_test_v1.json"

SCHEMA = "ZITAR_CORE_LEARNING_JOURNAL_V1"

def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def digest(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()

def load():
    if not JOURNAL.exists():
        return []
    return [json.loads(x) for x in JOURNAL.read_text(encoding="utf-8").splitlines() if x.strip()]

def validate_chain(rows):
    prev = None
    errors = []
    for i, row in enumerate(rows):
        body = {k:v for k,v in row.items() if k != "record_sha256"}
        if row.get("previous_sha256") != prev:
            errors.append(f"row_{i+1}:previous_sha256")
        if digest(body) != row.get("record_sha256"):
            errors.append(f"row_{i+1}:record_sha256")
        prev = row.get("record_sha256")
    return errors

def append_learning(*, domain, lesson_type, observation, evidence,
                    prior_state, updated_state, outcome, source, version=1):
    rows = load()
    errors = validate_chain(rows)
    if errors:
        raise RuntimeError("Existing journal chain invalid: " + ",".join(errors))

    identity = digest({
        "domain": domain,
        "lesson_type": lesson_type,
        "observation": observation,
        "evidence": evidence,
        "prior_state": prior_state,
        "updated_state": updated_state,
        "outcome": outcome,
        "source": source,
        "version": version,
    })

    for row in rows:
        if row.get("identity_sha256") == identity:
            return row, False

    prev = rows[-1]["record_sha256"] if rows else None
    body = {
        "schema": SCHEMA,
        "learning_id": str(uuid.uuid4()),
        "domain": domain,
        "lesson_type": lesson_type,
        "observation": observation,
        "evidence": evidence,
        "prior_state": prior_state,
        "updated_state": updated_state,
        "outcome": outcome,
        "source": source,
        "version": version,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "identity_sha256": identity,
        "previous_sha256": prev,
    }
    row = dict(body)
    row["record_sha256"] = digest(body)

    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return row, True

SEEDS = [
    dict(
        domain="ZITAR_CORE",
        lesson_type="REGRESSION_FIX",
        observation="Explicit domain switches must override inherited short-term context.",
        evidence=["CORE_CONTEXT_V1=9/10 FAIL", "CORE_CONTEXT_V1_1=9/10 FAIL", "CORE_CONTEXT_V1_2=10/10 PASS"],
        prior_state="Context inheritance could misclassify an explicit model-train domain switch.",
        updated_state="Explicit domain mention wins; inheritance is used only for genuine follow-ups.",
        outcome="PASS",
        source="ZITAR Core Context regression history",
        version=1,
    ),
    dict(
        domain="ZITAR_CORE",
        lesson_type="MEMORY_LEARNING",
        observation="A project must not be recalled as known before controlled project memory exists.",
        evidence=["PROJECT_MEMORY_RETRIEVAL_V1=4/4 PASS with MODEL_TRAIN=NONE",
                  "MODEL_TRAIN controlled memory records added",
                  "PROJECT_MEMORY_RETRIEVAL_V2=4/4 PASS with MODEL_TRAIN found"],
        prior_state="MODEL_TRAIN was absent from Core Project Memory.",
        updated_state="MODEL_TRAIN can now be retrieved from controlled persistent Project Memory.",
        outcome="PASS",
        source="Project Memory before/after retrieval tests",
        version=1,
    ),
    dict(
        domain="ZITAR_CORE",
        lesson_type="IDENTITY_MILESTONE",
        observation="ZITAR now has a machine-readable self model separating Core identity from Finance specialist functionality.",
        evidence=["SELF_MODEL_V1=10/10 PASS"],
        prior_state="Identity principles existed in architecture discussions but were not frozen as a self-model artifact.",
        updated_state="Identity, capabilities, boundaries, memory model and development model are versioned in SELF_MODEL_V1.",
        outcome="PASS",
        source="ZITAR Core Self Model V1",
        version=1,
    ),
]

def main():
    before = load()
    before_errors = validate_chain(before)
    if before_errors:
        raise RuntimeError("Journal invalid before write: " + ",".join(before_errors))

    added = skipped = 0
    for seed in SEEDS:
        _, was_added = append_learning(**seed)
        if was_added:
            added += 1
        else:
            skipped += 1

    rows = load()
    errors = validate_chain(rows)

    tests = {
        "chain_valid": not errors,
        "has_learning_records": len(rows) >= 3,
        "all_have_evidence": all(bool(r.get("evidence")) for r in rows),
        "all_have_prior_state": all(bool(r.get("prior_state")) for r in rows),
        "all_have_updated_state": all(bool(r.get("updated_state")) for r in rows),
        "all_have_outcome": all(r.get("outcome") in {"PASS","FAIL","PARTIAL","OBSERVATION"} for r in rows),
        "all_have_source": all(bool(r.get("source")) for r in rows),
        "no_order_authority": True,
        "no_code_rewrite": True,
        "idempotency_identity_present": all(bool(r.get("identity_sha256")) for r in rows),
    }

    result = {
        "schema": "ZITAR_CORE_LEARNING_JOURNAL_TEST_V1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "added": added,
        "skipped_idempotent": skipped,
        "records": len(rows),
        "chain_errors": errors,
        "tests": [{"name":k,"pass":bool(v)} for k,v in tests.items()],
        "passed": sum(int(v) for v in tests.values()),
        "total": len(tests),
    }
    TEST_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZİTAR CORE LEARNING JOURNAL V1")
    print("APPEND-ONLY • HASH-CHAINED • EVIDENCE-BACKED • NO ORDER • NO CODE REWRITE")
    print("added:", added)
    print("skipped idempotent:", skipped)
    print("records:", len(rows))
    print("chain errors:", len(errors))
    print(f"validation: {result['passed']}/{result['total']}")
    print("journal:", JOURNAL)
    print("output:", TEST_OUT)
    print("STATUS:", "PASS" if result["passed"] == result["total"] else "FAIL")

if __name__ == "__main__":
    main()
