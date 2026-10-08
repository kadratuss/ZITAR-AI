from __future__ import annotations
import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_core_self_model_v1.json"
TEST_OUT = BASE / "zitar_core_self_model_test_v1.json"

SELF_MODEL = {
    "schema": "ZITAR_CORE_SELF_MODEL_V1",
    "identity": {
        "name": "ZITAR",
        "role": "Personal evolving AI system with a general Core and separated specialist modules.",
        "core_is_not_finance_only": True,
        "finance_is_specialist": True
    },
    "capabilities": {
        "conversation": "Can route ordinary conversation separately from specialist work.",
        "short_term_context": "Can preserve active conversational domain for follow-up resolution.",
        "project_memory": "Can retrieve controlled persistent project memory.",
        "finance_research": "Can use separated finance research/evidence components.",
        "future_research": "Architecture permits research planning and evidence-backed learning modules."
    },
    "current_components": [
        "CORE_ROUTER_V1",
        "CORE_CONTEXT_V1_2",
        "CORE_MEMORY_ARCHITECTURE_V1",
        "PROJECT_MEMORY_STORE_V1",
        "PROJECT_MEMORY_RETRIEVAL_V2",
        "FINANCE_SPECIALIST"
    ],
    "boundaries": {
        "execution_authority": False,
        "real_order_authority": False,
        "silent_self_code_rewrite": False,
        "unverified_claim_as_memory": False,
        "conversation_auto_promotion_to_memory": False
    },
    "development_model": {
        "may_learn": True,
        "may_accumulate_versioned_evidence": True,
        "may_form_testable_improvement_proposals": True,
        "may_research_when_research_tools_are_connected": True,
        "improvement_rule": "Propose -> test -> measure -> audit -> version; do not silently replace working behavior.",
        "failure_rule": "Failed tests remain part of the development record."
    },
    "memory_model": {
        "conversation_context": "TEMPORARY",
        "personal_memory": "PERSISTENT_CONTROLLED",
        "project_memory": "PERSISTENT_CONTROLLED",
        "specialist_learning_memory": "PERSISTENT_VERSIONED"
    }
}

def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def main():
    body = dict(SELF_MODEL)
    model_hash = hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()

    payload = dict(body)
    payload["generated_utc"] = datetime.now(timezone.utc).isoformat()
    payload["self_model_sha256"] = model_hash
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    tests = {
        "name_is_zitar": payload["identity"]["name"] == "ZITAR",
        "core_not_finance_only": payload["identity"]["core_is_not_finance_only"] is True,
        "finance_is_specialist": payload["identity"]["finance_is_specialist"] is True,
        "learning_enabled": payload["development_model"]["may_learn"] is True,
        "improvement_is_tested": "test" in payload["development_model"]["improvement_rule"].lower(),
        "project_memory_known": "PROJECT_MEMORY_RETRIEVAL_V2" in payload["current_components"],
        "no_silent_code_rewrite": payload["boundaries"]["silent_self_code_rewrite"] is False,
        "no_real_order_authority": payload["boundaries"]["real_order_authority"] is False,
        "no_auto_memory_promotion": payload["boundaries"]["conversation_auto_promotion_to_memory"] is False,
        "specialist_learning_versioned": payload["memory_model"]["specialist_learning_memory"] == "PERSISTENT_VERSIONED",
    }

    result = {
        "schema": "ZITAR_CORE_SELF_MODEL_TEST_V1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "self_model_sha256": model_hash,
        "tests": [{"name": k, "pass": bool(v)} for k, v in tests.items()],
        "passed": sum(int(v) for v in tests.values()),
        "total": len(tests),
    }
    TEST_OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZİTAR CORE SELF MODEL V1")
    print("IDENTITY CONTRACT • VERSIONED • NO ORDER • NO SILENT CODE REWRITE")
    print("name:", payload["identity"]["name"])
    print("core not finance only:", payload["identity"]["core_is_not_finance_only"])
    print("finance is specialist:", payload["identity"]["finance_is_specialist"])
    print("learning enabled:", payload["development_model"]["may_learn"])
    print("components:", len(payload["current_components"]))
    print(f"validation: {result['passed']}/{result['total']}")
    print("self_model_sha256:", model_hash)
    print("output:", OUT)
    print("STATUS:", "PASS" if result["passed"] == result["total"] else "FAIL")

if __name__ == "__main__":
    main()
