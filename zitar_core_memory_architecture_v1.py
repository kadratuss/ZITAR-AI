from __future__ import annotations
import json, hashlib
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / "zitar_core_memory_architecture_v1.json"

ARCH = {
    "schema": "ZITAR_CORE_MEMORY_ARCHITECTURE_V1",
    "principles": [
        "Conversation context is temporary and is not long-term memory.",
        "Personal memory, project memory, and specialist learning memory are separate stores.",
        "No conversation is automatically promoted to persistent memory.",
        "Persistent writes require an explicit write policy and provenance.",
        "Finance learning cannot silently modify personal memory.",
        "Personal/project memory cannot silently become trading evidence.",
        "Failures, superseded beliefs, and version history must remain auditable."
    ],
    "stores": {
        "CONVERSATION_CONTEXT": {
            "persistence": "TEMPORARY",
            "purpose": "Current dialogue continuity and active-domain tracking.",
            "examples": ["active domain", "recent referent", "follow-up resolution"],
            "finance_evidence": False
        },
        "PERSONAL_MEMORY": {
            "persistence": "PERSISTENT_CONTROLLED",
            "purpose": "User preferences and durable user-specific context.",
            "examples": ["preferred workflow", "explicitly retained preferences"],
            "finance_evidence": False
        },
        "PROJECT_MEMORY": {
            "persistence": "PERSISTENT_CONTROLLED",
            "purpose": "Project decisions, architecture, milestones and unresolved work.",
            "examples": ["model train architecture", "ZITAR Core milestones"],
            "finance_evidence": False
        },
        "SPECIALIST_LEARNING_MEMORY": {
            "persistence": "PERSISTENT_VERSIONED",
            "purpose": "Domain-specific evidence, hypotheses, tests, failures and measured learning.",
            "examples": ["finance research memory", "future specialist learning"],
            "finance_evidence": "ONLY_WHEN_PROVENANCE_ALLOWS"
        }
    },
    "promotion_contract": {
        "automatic_persistent_write": False,
        "required_fields": [
            "memory_type", "content", "source", "created_utc",
            "provenance_category", "reason_for_persistence", "version"
        ],
        "allowed_targets": [
            "PERSONAL_MEMORY", "PROJECT_MEMORY", "SPECIALIST_LEARNING_MEMORY"
        ],
        "forbidden": [
            "CONVERSATION_CONTEXT_TO_PERSISTENT_WITHOUT_POLICY",
            "PERSONAL_MEMORY_TO_TRADING_EVIDENCE",
            "PROJECT_MEMORY_TO_TRADING_EVIDENCE",
            "SPECIALIST_LEARNING_TO_PERSONAL_MEMORY_SILENTLY"
        ]
    },
    "execution_authority": False
}

TESTS = [
    ("conversation_is_temporary",
     ARCH["stores"]["CONVERSATION_CONTEXT"]["persistence"] == "TEMPORARY"),
    ("no_auto_persistent_write",
     ARCH["promotion_contract"]["automatic_persistent_write"] is False),
    ("personal_separate_from_finance",
     ARCH["stores"]["PERSONAL_MEMORY"]["finance_evidence"] is False),
    ("project_separate_from_finance",
     ARCH["stores"]["PROJECT_MEMORY"]["finance_evidence"] is False),
    ("specialist_is_versioned",
     ARCH["stores"]["SPECIALIST_LEARNING_MEMORY"]["persistence"] == "PERSISTENT_VERSIONED"),
    ("promotion_has_provenance",
     "provenance_category" in ARCH["promotion_contract"]["required_fields"]),
    ("promotion_has_reason",
     "reason_for_persistence" in ARCH["promotion_contract"]["required_fields"]),
    ("no_execution_authority",
     ARCH["execution_authority"] is False),
]

def main():
    canonical = json.dumps(ARCH, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload = dict(ARCH)
    payload["generated_utc"] = datetime.now(timezone.utc).isoformat()
    payload["architecture_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    payload["validation"] = [
        {"test": name, "pass": bool(ok)} for name, ok in TESTS
    ]
    payload["validation_passed"] = sum(int(ok) for _, ok in TESTS)
    payload["validation_total"] = len(TESTS)

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("ZİTAR CORE MEMORY ARCHITECTURE V1")
    print("DESIGN CONTRACT • NO MEMORY WRITE • NO ORDER • NO V3 WRITE")
    print("stores:", len(ARCH["stores"]))
    for name, spec in ARCH["stores"].items():
        print(f"{name:28} persistence={spec['persistence']}")
    print(f"validation: {payload['validation_passed']}/{payload['validation_total']}")
    print("architecture_sha256:", payload["architecture_sha256"])
    print("output:", OUT)
    print("STATUS:", "PASS" if payload["validation_passed"] == payload["validation_total"] else "FAIL")

if __name__ == "__main__":
    main()
