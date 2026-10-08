from __future__ import annotations
import json, hashlib, uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_core_knowledge_gap_v1.jsonl"
TEST = BASE / "zitar_core_knowledge_gap_test_v1.json"

def canon(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha(x):
    return hashlib.sha256(canon(x).encode("utf-8")).hexdigest()

def make_gap(domain, question, reason, desired_evidence, priority="NORMAL"):
    identity = sha({
        "domain": domain,
        "question": question,
        "reason": reason,
        "desired_evidence": desired_evidence,
    })
    return {
        "schema": "ZITAR_CORE_KNOWLEDGE_GAP_V1",
        "gap_id": str(uuid.uuid4()),
        "identity_sha256": identity,
        "domain": domain,
        "question": question,
        "reason": reason,
        "desired_evidence": desired_evidence,
        "priority": priority,
        "status": "OPEN",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "research_authority": True,
        "execution_authority": False,
        "memory_write_authority": False,
    }

def detect_gap(*, domain, question, supported_answer_exists, reason, desired_evidence):
    if supported_answer_exists:
        return None
    return make_gap(domain, question, reason, desired_evidence)

def main():
    tests = [
        {
            "name": "model_train_learning_gap",
            "gap": detect_gap(
                domain="MODEL_TRAIN",
                question="Peki bundan ne öğrendin?",
                supported_answer_exists=False,
                reason="Domain-aware Learning Journal recall returned NO_DOMAIN_LEARNING.",
                desired_evidence=[
                    "MODEL_TRAIN project-memory records",
                    "versioned MODEL_TRAIN test/results",
                    "explicit before/after engineering observations",
                ],
            ),
            "expect_gap": True,
        },
        {
            "name": "zitar_core_no_gap",
            "gap": detect_gap(
                domain="ZITAR_CORE",
                question="Bundan ne öğrendin?",
                supported_answer_exists=True,
                reason="Learning Journal contains supported ZITAR_CORE records.",
                desired_evidence=["existing learning journal"],
            ),
            "expect_gap": False,
        },
        {
            "name": "unknown_research_gap",
            "gap": detect_gap(
                domain="GENERAL_RESEARCH",
                question="Bilmediğim bu konu için kanıt toplamam gerekiyor mu?",
                supported_answer_exists=False,
                reason="No supported local evidence exists.",
                desired_evidence=[
                    "authoritative primary sources",
                    "independent corroborating sources",
                    "dated source metadata",
                ],
            ),
            "expect_gap": True,
        },
    ]

    gaps = []
    passed = 0
    results = []
    seen = set()

    for t in tests:
        gap = t["gap"]
        ok = (gap is not None) == t["expect_gap"]
        if gap:
            ok = ok and gap["status"] == "OPEN"
            ok = ok and gap["research_authority"] is True
            ok = ok and gap["execution_authority"] is False
            ok = ok and gap["memory_write_authority"] is False
            if gap["identity_sha256"] not in seen:
                gaps.append(gap)
                seen.add(gap["identity_sha256"])
        passed += int(ok)
        results.append({"name": t["name"], "gap_created": gap is not None, "pass": ok})

    with OUT.open("w", encoding="utf-8") as f:
        for g in gaps:
            f.write(json.dumps(g, ensure_ascii=False, separators=(",", ":")) + "\n")

    payload = {
        "schema": "ZITAR_CORE_KNOWLEDGE_GAP_TEST_V1",
        "gaps": len(gaps),
        "tests": results,
        "passed": passed,
        "total": len(tests),
        "rules": {
            "absence_of_evidence_can_open_gap": True,
            "gap_is_not_a_claim": True,
            "gap_is_not_learned_memory": True,
            "research_does_not_grant_execution": True,
        },
    }
    TEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZİTAR CORE KNOWLEDGE GAP V1")
    print("CURIOSITY SEED • GAP != CLAIM • GAP != MEMORY • NO ORDER")
    for r in results:
        print(f"{'PASS' if r['pass'] else 'FAIL':4} | gap={str(r['gap_created']):5} | {r['name']}")
    print("open gaps:", len(gaps))
    print(f"RESULT: {passed}/{len(tests)} PASS")
    print("gaps:", OUT)
    print("output:", TEST)
    print("STATUS:", "PASS" if passed == len(tests) else "FAIL")

if __name__ == "__main__":
    main()
