from __future__ import annotations
import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
EVIDENCE = BASE / "zitar_core_real_research_evidence_v1.json"
OUT = BASE / "zitar_core_learning_candidate_v1.json"
TEST = BASE / "zitar_core_learning_candidate_validator_test_v1.json"

def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha(x):
    return hashlib.sha256(canonical(x).encode("utf-8")).hexdigest()

def main():
    if not EVIDENCE.exists():
        raise FileNotFoundError(EVIDENCE)

    ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    claims = ev.get("candidate_claims") or []
    sources = ev.get("sources") or []

    primary_sources = [s for s in sources if s.get("role") == "PRIMARY" and not s.get("error")]
    independent_sources = [s for s in sources if s.get("role") == "INDEPENDENT" and not s.get("error")]

    checks = {
        "evidence_says_candidate_ready": ev.get("learning_candidate_ready") is True,
        "corroborated": ev.get("corroborated") is True,
        "primary_source_present": len(primary_sources) >= 1,
        "independent_source_present": len(independent_sources) >= 1,
        "claims_exist": len(claims) >= 1,
        "all_claims_primary_supported": all(c.get("supported_by_primary") is True for c in claims),
        "no_execution_authority": ev.get("authorities", {}).get("real_order") is False,
        "no_memory_write_in_research_stage": ev.get("authorities", {}).get("memory_write") is False,
    }

    eligible = all(checks.values())

    candidate = {
        "schema": "ZITAR_CORE_LEARNING_CANDIDATE_V1",
        "domain": "GENERAL_RESEARCH",
        "topic": "Raspberry Pi 5",
        "question": ev.get("question"),
        "status": "VALIDATED_CANDIDATE" if eligible else "REJECTED",
        "claims": claims if eligible else [],
        "evidence_bundle_sha256": ev.get("bundle_sha256"),
        "source_provenance": [
            {
                "role": s.get("role"),
                "provider": s.get("provider"),
                "url": s.get("url"),
                "content_sha256": s.get("content_sha256"),
            }
            for s in sources if not s.get("error")
        ],
        "validation_checks": checks,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "authorities": {
            "candidate_creation": True,
            "persistent_memory_write": False,
            "real_order": False,
            "silent_code_rewrite": False,
        },
        "next_required_stage": "CONTROLLED_LEARNING_JOURNAL_WRITE" if eligible else "MORE_RESEARCH",
    }
    candidate["candidate_sha256"] = sha(candidate)
    OUT.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")

    tests = {
        "candidate_validated": candidate["status"] == "VALIDATED_CANDIDATE",
        "candidate_has_claims": len(candidate["claims"]) >= 1,
        "provenance_preserved": len(candidate["source_provenance"]) >= 2,
        "evidence_hash_linked": bool(candidate["evidence_bundle_sha256"]),
        "candidate_hashed": bool(candidate["candidate_sha256"]),
        "not_written_to_persistent_memory": not candidate["authorities"]["persistent_memory_write"],
        "no_real_order": not candidate["authorities"]["real_order"],
        "no_silent_code_rewrite": not candidate["authorities"]["silent_code_rewrite"],
    }

    passed = sum(int(v) for v in tests.values())
    TEST.write_text(json.dumps({
        "schema": "ZITAR_CORE_LEARNING_CANDIDATE_VALIDATOR_TEST_V1",
        "tests": [{"name": k, "pass": bool(v)} for k, v in tests.items()],
        "passed": passed,
        "total": len(tests),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZITAR CORE LEARNING CANDIDATE VALIDATOR V1")
    print("EVIDENCE -> VALIDATED CANDIDATE • NO PERSISTENT MEMORY WRITE • NO ORDER")
    print("evidence ready:", ev.get("learning_candidate_ready"))
    print("corroborated:", ev.get("corroborated"))
    print("primary sources:", len(primary_sources))
    print("independent sources:", len(independent_sources))
    print("claims:", len(candidate["claims"]))
    print("candidate status:", candidate["status"])
    print("next stage:", candidate["next_required_stage"])
    print(f"validation: {passed}/{len(tests)}")
    print("candidate:", OUT)
    print("output:", TEST)
    print("STATUS:", "PASS" if passed == len(tests) else "FAIL")

if __name__ == "__main__":
    main()
