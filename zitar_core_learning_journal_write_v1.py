from __future__ import annotations
import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
CANDIDATE = BASE / "zitar_core_learning_candidate_v1.json"
JOURNAL = BASE / "zitar_core_learning_journal_v1.jsonl"
OUT = BASE / "zitar_core_learning_journal_write_test_v1.json"

def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha(x):
    return hashlib.sha256(canonical(x).encode("utf-8")).hexdigest()

def load_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def verify_chain(rows):
    errors = []
    prev = None
    for i, r in enumerate(rows):
        if r.get("previous_record_sha256") != prev:
            errors.append(f"ROW_{i+1}:PREVIOUS_HASH_MISMATCH")
        body = dict(r)
        claimed = body.pop("record_sha256", None)
        actual = sha(body)
        if claimed != actual:
            errors.append(f"ROW_{i+1}:RECORD_HASH_MISMATCH")
        prev = claimed
    return errors

def main():
    if not CANDIDATE.exists():
        raise FileNotFoundError(CANDIDATE)

    candidate = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    rows = load_jsonl(JOURNAL)
    before = len(rows)

    pre_chain_errors = verify_chain(rows)

    eligible = (
        candidate.get("status") == "VALIDATED_CANDIDATE"
        and candidate.get("next_required_stage") == "CONTROLLED_LEARNING_JOURNAL_WRITE"
        and bool(candidate.get("candidate_sha256"))
        and len(candidate.get("claims") or []) > 0
        and len(candidate.get("source_provenance") or []) >= 2
    )

    duplicate = any(
        r.get("candidate_sha256") == candidate.get("candidate_sha256")
        for r in rows
    )

    added = 0
    if eligible and not duplicate and not pre_chain_errors:
        previous = rows[-1].get("record_sha256") if rows else None
        record = {
            "schema": "ZITAR_CORE_LEARNING_JOURNAL_RECORD_V2",
            "domain": candidate.get("domain"),
            "lesson_type": "EXTERNAL_RESEARCH_LEARNING",
            "topic": candidate.get("topic"),
            "observation": candidate.get("question"),
            "claims": candidate.get("claims"),
            "source_provenance": candidate.get("source_provenance"),
            "evidence_bundle_sha256": candidate.get("evidence_bundle_sha256"),
            "candidate_sha256": candidate.get("candidate_sha256"),
            "outcome": "LEARNED_FROM_CORROBORATED_EXTERNAL_RESEARCH",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "previous_record_sha256": previous,
            "execution_authority": False,
            "silent_code_rewrite_authority": False,
        }
        record["record_sha256"] = sha(record)
        with JOURNAL.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        added = 1

    after_rows = load_jsonl(JOURNAL)
    post_chain_errors = verify_chain(after_rows)

    matching = [
        r for r in after_rows
        if r.get("candidate_sha256") == candidate.get("candidate_sha256")
    ]

    tests = {
        "candidate_eligible": eligible,
        "preexisting_chain_valid": len(pre_chain_errors) == 0,
        "exactly_one_candidate_record": len(matching) == 1,
        "idempotent_write": (added == 1 and not duplicate) or (added == 0 and duplicate),
        "post_write_chain_valid": len(post_chain_errors) == 0,
        "evidence_hash_preserved": bool(matching) and matching[0].get("evidence_bundle_sha256") == candidate.get("evidence_bundle_sha256"),
        "provenance_preserved": bool(matching) and len(matching[0].get("source_provenance") or []) >= 2,
        "no_execution_authority": bool(matching) and matching[0].get("execution_authority") is False,
        "no_silent_code_rewrite": bool(matching) and matching[0].get("silent_code_rewrite_authority") is False,
    }

    passed = sum(int(v) for v in tests.values())
    OUT.write_text(json.dumps({
        "schema": "ZITAR_CORE_LEARNING_JOURNAL_WRITE_TEST_V1",
        "before_records": before,
        "after_records": len(after_rows),
        "added": added,
        "duplicate": duplicate,
        "pre_chain_errors": pre_chain_errors,
        "post_chain_errors": post_chain_errors,
        "tests": [{"name": k, "pass": bool(v)} for k, v in tests.items()],
        "passed": passed,
        "total": len(tests),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZITAR CORE CONTROLLED LEARNING JOURNAL WRITE V1")
    print("VALIDATED CANDIDATE -> PERSISTENT LEARNING • APPEND ONLY • HASH CHAINED")
    print("candidate eligible:", eligible)
    print("duplicate:", duplicate)
    print("records before:", before)
    print("added:", added)
    print("records after:", len(after_rows))
    print("pre-chain errors:", len(pre_chain_errors))
    print("post-chain errors:", len(post_chain_errors))
    print(f"validation: {passed}/{len(tests)}")
    print("journal:", JOURNAL)
    print("output:", OUT)
    print("STATUS:", "PASS" if passed == len(tests) else "FAIL")

if __name__ == "__main__":
    main()
