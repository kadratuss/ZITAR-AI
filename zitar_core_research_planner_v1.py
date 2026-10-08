from __future__ import annotations
import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
GAPS = BASE / "zitar_core_knowledge_gap_v1.jsonl"
OUT = BASE / "zitar_core_research_plans_v1.jsonl"
TEST = BASE / "zitar_core_research_planner_test_v1.json"

def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def sha(x):
    return hashlib.sha256(canonical(x).encode("utf-8")).hexdigest()

def load_jsonl(path):
    if not path.exists():
        raise FileNotFoundError(path)
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def plan_for(gap):
    domain = gap["domain"]
    desired = gap.get("desired_evidence") or []

    if domain == "MODEL_TRAIN":
        strategy = [
            {"step": 1, "action": "SEARCH_LOCAL_PROJECT_MEMORY",
             "purpose": "Retrieve existing MODEL_TRAIN facts before using external research."},
            {"step": 2, "action": "SEARCH_LOCAL_TEST_HISTORY",
             "purpose": "Find versioned before/after tests and engineering observations."},
            {"step": 3, "action": "IDENTIFY_UNSUPPORTED_SUBCLAIMS",
             "purpose": "Separate what is remembered from what is actually learned/tested."},
            {"step": 4, "action": "EXTERNAL_RESEARCH_IF_NEEDED",
             "purpose": "Use authoritative technical sources only for remaining external knowledge gaps."},
            {"step": 5, "action": "CROSS_CHECK",
             "purpose": "Require corroboration for externally sourced technical claims."},
            {"step": 6, "action": "PROPOSE_LEARNING_RECORD",
             "purpose": "Prepare evidence-backed learning candidate; do not auto-write memory."},
        ]
    else:
        strategy = [
            {"step": 1, "action": "DEFINE_QUESTION",
             "purpose": "Turn the gap into a bounded research question."},
            {"step": 2, "action": "PRIMARY_SOURCE_SEARCH",
             "purpose": "Prefer authoritative or first-party evidence."},
            {"step": 3, "action": "INDEPENDENT_CORROBORATION",
             "purpose": "Seek independent supporting or conflicting evidence."},
            {"step": 4, "action": "DATE_AND_SCOPE_CHECK",
             "purpose": "Verify freshness, population, scope and applicability."},
            {"step": 5, "action": "CONFLICT_ANALYSIS",
             "purpose": "Preserve unresolved disagreements instead of forcing consensus."},
            {"step": 6, "action": "PROPOSE_LEARNING_RECORD",
             "purpose": "Produce a reviewable candidate, not automatic learned memory."},
        ]

    identity_body = {
        "gap_identity_sha256": gap["identity_sha256"],
        "domain": domain,
        "question": gap["question"],
        "strategy": strategy,
        "desired_evidence": desired,
    }

    return {
        "schema": "ZITAR_CORE_RESEARCH_PLAN_V1",
        "plan_sha256": sha(identity_body),
        "gap_identity_sha256": gap["identity_sha256"],
        "domain": domain,
        "question": gap["question"],
        "desired_evidence": desired,
        "strategy": strategy,
        "completion_rule": "Evidence requirements satisfied and conflicts explicitly represented.",
        "failure_rule": "If evidence is insufficient, return INSUFFICIENT_EVIDENCE; do not fabricate closure.",
        "source_policy": {
            "primary_sources_preferred": True,
            "independent_corroboration": True,
            "source_dates_required_when_relevant": True,
            "conflicts_preserved": True,
        },
        "authorities": {
            "web_research": True,
            "local_read": True,
            "real_order": False,
            "automatic_memory_write": False,
            "silent_code_rewrite": False,
        },
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }

def main():
    gaps = load_jsonl(GAPS)
    open_gaps = [g for g in gaps if g.get("status") == "OPEN"]
    plans = [plan_for(g) for g in open_gaps]

    with OUT.open("w", encoding="utf-8") as f:
        for p in plans:
            f.write(json.dumps(p, ensure_ascii=False, separators=(",", ":")) + "\n")

    tests = {
        "one_plan_per_open_gap": len(plans) == len(open_gaps),
        "all_have_steps": all(len(p["strategy"]) >= 5 for p in plans),
        "all_prefer_evidence": all(p["source_policy"]["primary_sources_preferred"] for p in plans),
        "all_require_corroboration": all(p["source_policy"]["independent_corroboration"] for p in plans),
        "all_preserve_conflicts": all(p["source_policy"]["conflicts_preserved"] for p in plans),
        "insufficient_evidence_is_valid_outcome": all("INSUFFICIENT_EVIDENCE" in p["failure_rule"] for p in plans),
        "web_research_allowed": all(p["authorities"]["web_research"] for p in plans),
        "no_real_order": all(not p["authorities"]["real_order"] for p in plans),
        "no_auto_memory_write": all(not p["authorities"]["automatic_memory_write"] for p in plans),
        "no_silent_code_rewrite": all(not p["authorities"]["silent_code_rewrite"] for p in plans),
    }

    passed = sum(int(v) for v in tests.values())
    payload = {
        "schema": "ZITAR_CORE_RESEARCH_PLANNER_TEST_V1",
        "open_gaps": len(open_gaps),
        "plans": len(plans),
        "tests": [{"name": k, "pass": bool(v)} for k, v in tests.items()],
        "passed": passed,
        "total": len(tests),
    }
    TEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZİTAR CORE RESEARCH PLANNER V1")
    print("GAP -> PLAN • EVIDENCE FIRST • NO ORDER • NO AUTO MEMORY WRITE")
    print("open gaps:", len(open_gaps))
    print("plans:", len(plans))
    for p in plans:
        print(f"  {p['domain']:<18} steps={len(p['strategy'])} question={p['question']}")
    print(f"validation: {passed}/{len(tests)}")
    print("plans file:", OUT)
    print("output:", TEST)
    print("STATUS:", "PASS" if passed == len(tests) else "FAIL")

if __name__ == "__main__":
    main()
